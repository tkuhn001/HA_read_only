from __future__ import annotations

import fnmatch
import logging
import secrets
import time

from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .const import (
    API_PREFIX,
    CONF_ALLOWED_DOMAINS,
    CONF_ALLOWED_AREAS,
    CONF_ALLOWED_ENTITIES,
    CONF_ALLOWED_PATTERNS,
    CONF_BLOCKED_ENTITIES,
    CONF_BLOCKED_PATTERNS,
    CONF_INCLUDE_ATTRIBUTES,
    CONF_PROVIDE_ENTITIES_LIST,
    CONF_RETURN_ONLY_IDS,
    CONF_TOKEN,
    DOMAIN,
    HEADER_TOKEN_NAME,
    RATE_LIMIT_MAX_PER_IP,
    RATE_LIMIT_MAX_PER_TOKEN,
    RATE_LIMIT_WINDOW,
)

_LOGGER = logging.getLogger(__name__)

_RATE_LIMITS: dict[tuple[str, str], list[float]] = {}

try:
    from homeassistant.helpers.http import HomeAssistantView
except ImportError:
    HomeAssistantView = None
    _LOGGER.warning(
        "HomeAssistantView not available; read-only API endpoints disabled."
    )


def _rate_limit(key: tuple[str, str]) -> bool:
    """Check and record a request for rate limiting. Returns True if allowed."""
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW
    records = _RATE_LIMITS.get(key, [])
    records = [t for t in records if t > window_start]
    max_limit = RATE_LIMIT_MAX_PER_IP if key[0] == "ip" else RATE_LIMIT_MAX_PER_TOKEN
    if len(records) >= max_limit:
        return False
    records.append(now)
    _RATE_LIMITS[key] = records
    if len(_RATE_LIMITS) > 10000:
        _trim_rate_limits()
    return True


def _trim_rate_limits() -> None:
    """Remove expired entries from rate limit cache."""
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW
    expired = [k for k, v in _RATE_LIMITS.items() if not any(t > cutoff for t in v)]
    for k in expired:
        del _RATE_LIMITS[k]


def _mask_token(token: str) -> str:
    """Mask a token for display, showing first 8 chars."""
    if len(token) <= 8:
        return token
    return token[:8] + "\u2026"


async def async_setup_api(hass: HomeAssistant) -> None:
    """Register the API views."""
    if HomeAssistantView is None:
        _LOGGER.warning("Cannot register API views – HomeAssistantView not available")
        return
    hass.http.register_view(StatesView)
    hass.http.register_view(SingleStateView)
    hass.http.register_view(EntityListView)
    hass.http.register_view(AdminPanelView)
    hass.http.register_view(AdminApiOptionsView)
    hass.http.register_view(AdminApiTokensView)
    hass.http.register_view(AdminApiTokenView)
    hass.http.register_view(AdminApiTokenRegenerateView)
    _LOGGER.info("Read-only API endpoints registered at %s/*", API_PREFIX)


def _get_client_ip(request: web.Request) -> str:
    """Extract client IP from request."""
    if forwarded := request.headers.get("X-Forwarded-For"):
        return forwarded.split(",")[0].strip()
    if peername := request.transport.get_extra_info("peername"):
        return peername[0]
    return "unknown"


def _get_token_name(hass: HomeAssistant, token: str) -> str:
    """Get the friendly name for a token."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(CONF_TOKEN) == token:
            return entry.title or entry.data.get(CONF_TOKEN_NAME, "Unnamed")
    return "Unknown"


def _find_entry_by_token(hass: HomeAssistant, token: str):
    """Find config entry matching the given token."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(CONF_TOKEN) == token:
            return entry
    return None


def _build_response(state_entry, include_attrs: bool) -> dict:
    """Build a state response dict."""
    result = {
        "entity_id": state_entry.entity_id,
        "state": state_entry.state,
    }
    if include_attrs:
        result["attributes"] = dict(state_entry.attributes)
    return result


def _match_patterns(entity_id: str, patterns: list[str]) -> bool:
    """Check if entity_id matches any of the fnmatch patterns."""
    for pattern in patterns:
        if fnmatch.fnmatch(entity_id, pattern):
            return True
    return False


def _get_area_entity_ids(hass: HomeAssistant, area_ids: set[str]) -> set[str]:
    """Resolve area IDs to entity IDs using the entity registry."""
    ent_reg = async_get_entity_registry(hass)
    area_entities = set()
    for entity_entry in ent_reg.entities.values():
        if entity_entry.area_id in area_ids:
            area_entities.add(entity_entry.entity_id)
    return area_entities


def _is_entity_allowed(
    entity_id: str, data: dict, hass: HomeAssistant,
    area_entities_cache: set[str] | None = None,
) -> bool:
    """Check if a single entity is allowed based on token config."""
    allowed_domains = set(data.get(CONF_ALLOWED_DOMAINS, []))
    allowed_entities = set(data.get(CONF_ALLOWED_ENTITIES, []))
    allowed_patterns = [
        p.strip()
        for p in data.get(CONF_ALLOWED_PATTERNS, "").split("\n")
        if p.strip()
    ]
    allowed_areas = set(data.get(CONF_ALLOWED_AREAS, []))

    blocked_entities = set(data.get(CONF_BLOCKED_ENTITIES, []))
    blocked_patterns = [
        p.strip()
        for p in data.get(CONF_BLOCKED_PATTERNS, "").split("\n")
        if p.strip()
    ]

    domain = entity_id.split(".", 1)[0]

    no_allow_restrictions = (
        not allowed_domains
        and not allowed_entities
        and not allowed_patterns
        and not allowed_areas
    )

    allowed = False
    if no_allow_restrictions:
        allowed = True
    else:
        if domain in allowed_domains:
            allowed = True
        if entity_id in allowed_entities:
            allowed = True
        if allowed_areas:
            if area_entities_cache is None:
                area_entities_cache = _get_area_entity_ids(hass, allowed_areas)
            if entity_id in area_entities_cache:
                allowed = True
        if allowed_patterns and _match_patterns(entity_id, allowed_patterns):
            allowed = True

    if not allowed:
        return False

    if entity_id in blocked_entities:
        return False
    if blocked_patterns and _match_patterns(entity_id, blocked_patterns):
        return False

    return True


def _get_allowed_states(hass: HomeAssistant, data: dict) -> list[dict]:
    """Get filtered list of allowed states."""
    include_attrs = data.get(CONF_INCLUDE_ATTRIBUTES, True)
    allowed_areas = set(data.get(CONF_ALLOWED_AREAS, []))
    area_entities_cache = (
        _get_area_entity_ids(hass, allowed_areas) if allowed_areas else None
    )

    result = []
    for state in hass.states.async_all():
        if _is_entity_allowed(
            state.entity_id, data, hass, area_entities_cache,
        ):
            result.append(_build_response(state, include_attrs))

    return result


ADMIN_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HA Read-Only API – Token-Management</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@mdi/font@7/css/materialdesignicons.min.css">
<style>
  :root { --bg: #121212; --surface: #1e1e1e; --primary: #03a9f4; --text: #e0e0e0; --text-secondary: #9e9e9e; --border: #333; --danger: #f44336; --success: #4caf50; --warning: #ff9800; --radius: 8px; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; min-height: 100vh; }
  .container { max-width: 1200px; margin: 0 auto; }
  header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 32px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
  header h1 { font-size: 24px; font-weight: 600; display: flex; align-items: center; gap: 12px; }
  header h1 .mdi { color: var(--primary); font-size: 32px; }
  header p { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }
  .btn { display: inline-flex; align-items: center; gap: 6px; padding: 10px 20px; border: none; border-radius: var(--radius); font-size: 14px; font-weight: 500; cursor: pointer; transition: all .2s; text-decoration: none; }
  .btn-primary { background: var(--primary); color: #fff; }
  .btn-primary:hover { filter: brightness(1.15); }
  .btn-danger { background: var(--danger); color: #fff; }
  .btn-danger:hover { filter: brightness(1.15); }
  .btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
  .btn-outline:hover { border-color: var(--primary); color: var(--primary); }
  .btn-sm { padding: 6px 12px; font-size: 13px; }
  .card { background: var(--surface); border-radius: var(--radius); border: 1px solid var(--border); padding: 20px; margin-bottom: 16px; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 12px 16px; font-size: 12px; text-transform: uppercase; letter-spacing: .5px; color: var(--text-secondary); border-bottom: 2px solid var(--border); }
  td { padding: 14px 16px; border-bottom: 1px solid var(--border); font-size: 14px; }
  tr:hover td { background: rgba(255,255,255,.03); }
  .token-masked { font-family: "SF Mono", Monaco, monospace; font-size: 13px; color: var(--text-secondary); }
  .perms { font-size: 13px; color: var(--text-secondary); max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .actions { display: flex; gap: 4px; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 500; }
  .badge-all { background: rgba(76,175,80,.15); color: var(--success); }
  .badge-limited { background: rgba(3,169,244,.15); color: var(--primary); }
  .empty { text-align: center; padding: 60px 20px; color: var(--text-secondary); }
  .empty .mdi { font-size: 48px; margin-bottom: 12px; }
  .empty p { font-size: 16px; }
  .toast { position: fixed; bottom: 24px; right: 24px; padding: 12px 24px; border-radius: var(--radius); z-index: 9999; font-size: 14px; animation: slideIn .3s ease; max-width: 400px; }
  .toast.success { background: var(--success); color: #fff; }
  .toast.error { background: var(--danger); color: #fff; }
  .toast.info { background: var(--primary); color: #fff; }
  @keyframes slideIn { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
  .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 1000; justify-content: center; align-items: center; }
  .modal-overlay.active { display: flex; }
  .modal { background: var(--surface); border-radius: var(--radius); border: 1px solid var(--border); padding: 24px; width: 90%; max-width: 600px; max-height: 80vh; overflow-y: auto; }
  .modal h2 { font-size: 20px; margin-bottom: 20px; display: flex; align-items: center; gap: 8px; }
  .form-group { margin-bottom: 16px; }
  .form-group label { display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; font-weight: 500; }
  .form-group input, .form-group textarea, .form-group select { width: 100%; padding: 10px 12px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text); font-size: 14px; }
  .form-group input:focus, .form-group textarea:focus, .form-group select:focus { outline: none; border-color: var(--primary); }
  .form-group textarea { min-height: 80px; resize: vertical; font-family: "SF Mono", Monaco, monospace; font-size: 13px; }
  .form-row { display: flex; gap: 12px; }
  .form-row .form-group { flex: 1; }
  .modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }
  .checkbox-group { display: flex; flex-wrap: wrap; gap: 8px; }
  .checkbox-group label { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer; padding: 6px 12px; background: var(--bg); border-radius: 6px; border: 1px solid var(--border); }
  .checkbox-group label.active { border-color: var(--primary); background: rgba(3,169,244,.1); }
  .checkbox-group input[type="checkbox"] { width: auto; accent-color: var(--primary); }
  .token-display { background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 12px; font-family: "SF Mono", Monaco, monospace; font-size: 14px; word-break: break-all; margin: 12px 0; }
  .token-display .label { font-size: 11px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; }
  .token-display .value { color: var(--primary); }
  .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid var(--border); border-top-color: var(--primary); border-radius: 50%; animation: spin .6s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (max-width: 768px) { header { flex-direction: column; align-items: flex-start; gap: 12px; } .form-row { flex-direction: column; } }
</style>
</head>
<body>
<div class="container">
  <header>
    <div>
      <h1><span class="mdi mdi-shield-lock"></span> HA Read-Only API</h1>
      <p>Token-Management – Alle konfigurierten API-Tokens verwalten</p>
    </div>
    <button class="btn btn-primary" onclick="openNewToken()"><span class="mdi mdi-plus"></span> Neuen Token erstellen</button>
  </header>
  <div id="loading" style="text-align:center;padding:60px;"><div class="spinner" style="width:32px;height:32px;border-width:3px;"></div><p style="color:var(--text-secondary);margin-top:12px;">Lade Tokens…</p></div>
  <div class="card" id="tokenTable" style="display:none;">
    <table>
      <thead><tr><th>Name</th><th>Token</th><th>Berechtigungen</th><th style="text-align:right;">Aktionen</th></tr></thead>
      <tbody id="tokenBody"></tbody>
    </table>
  </div>
  <div id="emptyState" class="card empty" style="display:none;">
    <div class="mdi mdi-key-variant"></div>
    <p>Keine Tokens konfiguriert.<br>Erstelle einen neuen Token, um die API zu nutzen.</p>
  </div>
</div>

<div class="modal-overlay" id="tokenModal">
  <div class="modal">
    <h2><span class="mdi mdi-key-plus" id="modalIcon"></span> <span id="modalTitle">Token erstellen</span></h2>
    <div id="modalBody"></div>
  </div>
</div>

<div class="modal-overlay" id="confirmModal">
  <div class="modal" style="max-width:400px;">
    <h2><span class="mdi mdi-alert-circle" style="color:var(--warning);"></span> <span id="confirmTitle">Bestätigen</span></h2>
    <p id="confirmMessage" style="color:var(--text-secondary);margin-bottom:20px;line-height:1.5;"></p>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeConfirm()">Abbrechen</button>
      <button class="btn btn-danger" id="confirmBtn" onclick="confirmAction()">Löschen</button>
    </div>
  </div>
</div>

<div class="modal-overlay" id="regenerateModal">
  <div class="modal" style="max-width:500px;">
    <h2><span class="mdi mdi-autorenew" style="color:var(--primary);"></span> Token neu generiert</h2>
    <p style="color:var(--text-secondary);margin-bottom:12px;">Der neue Token für <strong id="regenerateName"></strong> lautet:</p>
    <div class="token-display"><div class="label">Neuer Token</div><div class="value" id="regenerateToken"></div></div>
    <p style="color:var(--warning);font-size:13px;margin-top:8px;">Kopiere den Token jetzt. Nach Schließen wird er nicht mehr angezeigt.</p>
    <div class="modal-actions">
      <button class="btn btn-primary" onclick="copyToken()"><span class="mdi mdi-content-copy"></span> Kopieren</button>
      <button class="btn btn-outline" onclick="closeRegenerate()">Schließen</button>
    </div>
  </div>
</div>

<script>
let tokens = []; let pendingAction = null; let currentEntryId = null;

function showToast(msg, type) { const t=document.createElement('div'); t.className='toast '+type; t.textContent=msg; document.body.appendChild(t); setTimeout(()=>t.remove(), 3500); }

async function apiFetch(url, opts={}) {
  const r = await fetch(url, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...opts.headers }, ...opts });
  if (!r.ok) { const e = await r.json().catch(()=>({error:r.statusText})); throw new Error(e.error||r.statusText); }
  return r.status===204 ? null : r.json();
}

async function loadTokens() {
  document.getElementById('loading').style.display='block';
  document.getElementById('tokenTable').style.display='none';
  document.getElementById('emptyState').style.display='none';
  try {
    tokens = await apiFetch('/api/ha_read_only/admin/api/tokens');
    renderTokens();
  } catch(e) { showToast('Fehler beim Laden: '+e.message, 'error'); }
  document.getElementById('loading').style.display='none';
}

function renderTokens() {
  const tbody = document.getElementById('tokenBody');
  tbody.innerHTML = '';
  if (!tokens.length) { document.getElementById('tokenTable').style.display='none'; document.getElementById('emptyState').style.display='block'; return; }
  document.getElementById('tokenTable').style.display='block'; document.getElementById('emptyState').style.display='none';
  tokens.forEach(t => {
    const limited = t.allowed_domains?.length || t.allowed_entities?.length || t.allowed_patterns || t.allowed_areas?.length;
    let perms = limited ? [] : 'Alle Entitäten';
    if (t.allowed_domains?.length) perms = t.allowed_domains.join(', ');
    else if (t.allowed_entities?.length) perms = t.allowed_entities.length+' Entität(en)';
    else if (t.allowed_areas?.length) perms = t.allowed_areas.length+' Bereich(e)';
    else if (t.allowed_patterns) perms = 'Patterns';
    const tr = document.createElement('tr');
    tr.innerHTML = '<td><strong>'+esc(t.name)+'</strong></td>'+
      '<td><span class="token-masked">'+esc(t.token_masked)+'</span></td>'+
      '<td><span class="badge '+(limited?'badge-limited':'badge-all')+'">'+esc(typeof perms==='string'?perms:'Gemischt')+'</span></td>'+
      '<td style="text-align:right;"><div class="actions" style="justify-content:flex-end;">'+
      '<button class="btn btn-outline btn-sm" onclick="editToken(\''+t.entry_id+'\')" title="Bearbeiten"><span class="mdi mdi-pencil"></span></button>'+
      '<button class="btn btn-outline btn-sm" onclick="regenerateToken(\''+t.entry_id+'\',\''+esc(t.name)+'\')" title="Neu generieren"><span class="mdi mdi-autorenew"></span></button>'+
      '<button class="btn btn-outline btn-sm" style="color:var(--danger)" onclick="deleteToken(\''+t.entry_id+'\',\''+esc(t.name)+'\')" title="Löschen"><span class="mdi mdi-delete"></span></button></div></td>';
    tbody.appendChild(tr);
  });
}

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

async function openNewToken() {
  currentEntryId = null;
  document.getElementById('modalIcon').className = 'mdi mdi-key-plus';
  document.getElementById('modalTitle').textContent = 'Neuen Token erstellen';
  try {
    const opts = await apiFetch('/api/ha_read_only/admin/api/options');
    const domains = opts.domains||[]; const areas = opts.areas||[]; const entities = opts.entities||[];
    document.getElementById('modalBody').innerHTML = buildTokenForm({name:'',domains:[],areas:[],entities:[],patterns:'',blockedEntities:[],blockedPatterns:'',provideEntitiesList:false,returnOnlyIds:false,includeAttributes:true}, domains, areas, entities);
    document.getElementById('tokenModal').classList.add('active');
  } catch(e) { showToast('Fehler: '+e.message, 'error'); }
}

async function editToken(entryId) {
  currentEntryId = entryId;
  document.getElementById('modalIcon').className = 'mdi mdi-pencil';
  document.getElementById('modalTitle').textContent = 'Token bearbeiten';
  try {
    const [data, opts] = await Promise.all([
      apiFetch('/api/ha_read_only/admin/api/tokens/'+entryId),
      apiFetch('/api/ha_read_only/admin/api/options')
    ]);
    document.getElementById('modalBody').innerHTML = buildTokenForm(data, opts.domains||[], opts.areas||[], opts.entities||[]);
    document.getElementById('tokenModal').classList.add('active');
  } catch(e) { showToast('Fehler: '+e.message, 'error'); }
}

function buildTokenForm(data, domains, areas, entities) {
  return '<div class="form-group"><label>Token-Name</label><input type="text" id="f_name" value="'+esc(data.name||'')+'" placeholder="z.B. Wetterdienst"></div>'+
    '<div class="form-row"><div class="form-group"><label>Erlaubte Domains</label><div class="checkbox-group">'+
    domains.map(d => '<label class="'+(data.domains?.includes(d)?'active':'')+'"><input type="checkbox" value="'+esc(d)+'" '+(data.domains?.includes(d)?'checked':'')+' onchange="this.parentElement.classList.toggle(\'active\')">'+esc(d)+'</label>').join('')+
    '</div></div></div>'+
    '<div class="form-group"><label>Erlaubte Patterns (eine pro Zeile)</label><textarea id="f_patterns" placeholder="light.kueche_*">'+esc(data.patterns||'')+'</textarea></div>'+
    '<div class="form-group"><label>Gesperrte Entit\u00e4ten</label><textarea id="f_blockedEntities" placeholder="sensor.temp_bad">'+(Array.isArray(data.blockedEntities)?data.blockedEntities.join('\\n'):esc(data.blockedEntities||''))+'</textarea></div>'+
    '<div class="form-group"><label>Gesperrte Patterns (eine pro Zeile)</label><textarea id="f_blockedPatterns" placeholder="*_unused">'+esc(data.blockedPatterns||'')+'</textarea></div>'+
    '<div class="form-row"><div class="form-group"><label><input type="checkbox" id="f_entitiesList" '+(data.provideEntitiesList?'checked':'')+'> /entities-Endpoint aktivieren</label></div>'+
    '<div class="form-group"><label><input type="checkbox" id="f_onlyIds" '+(data.returnOnlyIds?'checked':'')+'> Nur IDs zur\u00fcckgeben</label></div></div>'+
    '<div class="form-row"><div class="form-group"><label><input type="checkbox" id="f_includeAttrs" '+(data.includeAttributes!==false?'checked':'')+'> Attribute inkludieren</label></div></div>'+
    '<div class="modal-actions"><button class="btn btn-outline" onclick="closeModal()">Abbrechen</button>'+
    '<button class="btn btn-primary" onclick="saveToken()">Speichern</button></div>';
}

async function saveToken() {
  const payload = {
    name: document.getElementById('f_name').value.trim(),
    domains: Array.from(document.querySelectorAll('#f_name').closest('.modal').querySelectorAll('.checkbox-group input:checked')).map(c=>c.value),
    patterns: document.getElementById('f_patterns').value,
    blockedEntities: document.getElementById('f_blockedEntities').value.split('\\n').map(s=>s.trim()).filter(Boolean),
    blockedPatterns: document.getElementById('f_blockedPatterns').value,
    provideEntitiesList: document.getElementById('f_entitiesList').checked,
    returnOnlyIds: document.getElementById('f_onlyIds').checked,
    includeAttributes: document.getElementById('f_includeAttrs').checked,
  };
  if (!payload.name) { showToast('Bitte einen Token-Namen eingeben.', 'error'); return; }
  try {
    if (currentEntryId) {
      await apiFetch('/api/ha_read_only/admin/api/tokens/'+currentEntryId, { method:'PUT', body:JSON.stringify(payload) });
      showToast('Token aktualisiert.', 'success');
    } else {
      const result = await apiFetch('/api/ha_read_only/admin/api/tokens', { method:'POST', body:JSON.stringify(payload) });
      document.getElementById('tokenModal').classList.remove('active');
      showRegenerateToken(result.name, result.token);
      await loadTokens();
      return;
    }
    closeModal();
    await loadTokens();
  } catch(e) { showToast('Fehler: '+e.message, 'error'); }
}

function regenerateToken(entryId, name) {
  currentEntryId = entryId;
  document.getElementById('confirmTitle').textContent = 'Token neu generieren';
  document.getElementById('confirmMessage').innerHTML = 'Der Token f\u00fcr <strong>'+esc(name)+'</strong> wird neu generiert. Der alte Token ist danach <strong>sofort ung\u00fcltig</strong>. Fortfahren?';
  document.getElementById('confirmBtn').className = 'btn btn-primary';
  document.getElementById('confirmBtn').textContent = 'Neu generieren';
  pendingAction = async () => {
    try {
      const result = await apiFetch('/api/ha_read_only/admin/api/tokens/'+entryId+'/regenerate', { method:'POST' });
      closeConfirm();
      showRegenerateToken(result.name, result.token);
      await loadTokens();
    } catch(e) { showToast('Fehler: '+e.message, 'error'); }
  };
  document.getElementById('confirmModal').classList.add('active');
}

function showRegenerateToken(name, token) {
  document.getElementById('regenerateName').textContent = name;
  document.getElementById('regenerateToken').textContent = token;
  document.getElementById('regenerateModal').classList.add('active');
}

let _currentToken = '';
function copyToken() {
  const t = document.getElementById('regenerateToken').textContent;
  navigator.clipboard.writeText(t).then(()=>showToast('Token kopiert!', 'success')).catch(()=>{});
}

function deleteToken(entryId, name) {
  currentEntryId = entryId;
  document.getElementById('confirmTitle').textContent = 'Token l\u00f6schen';
  document.getElementById('confirmMessage').innerHTML = 'Der Token <strong>'+esc(name)+'</strong> wird dauerhaft gel\u00f6scht. Der Zugriff ist danach <strong>sofort ung\u00fcltig</strong>. Fortfahren?';
  document.getElementById('confirmBtn').className = 'btn btn-danger';
  document.getElementById('confirmBtn').textContent = 'L\u00f6schen';
  pendingAction = async () => {
    try {
      await apiFetch('/api/ha_read_only/admin/api/tokens/'+entryId, { method:'DELETE' });
      showToast('Token gel\u00f6scht.', 'success');
      closeConfirm();
      await loadTokens();
    } catch(e) { showToast('Fehler: '+e.message, 'error'); }
  };
  document.getElementById('confirmModal').classList.add('active');
}

function confirmAction() { if(pendingAction) { pendingAction(); pendingAction=null; } }
function closeConfirm() { document.getElementById('confirmModal').classList.remove('active'); pendingAction=null; }
function closeModal() { document.getElementById('tokenModal').classList.remove('active'); }
function closeRegenerate() { document.getElementById('regenerateModal').classList.remove('active'); }
loadTokens();
</script>
</body>
</html>"""


_AdminView = None
_AdminApiView = None

if HomeAssistantView is not None:

    class AdminPanelView(HomeAssistantView):
        """GET /api/ha_read_only/admin – Admin management panel."""

        url = f"{API_PREFIX}/admin"
        name = f"{DOMAIN}:admin_panel"
        requires_auth = True

        async def get(self, request: web.Request) -> web.Response:
            return web.Response(
                text=ADMIN_HTML, content_type="text/html",
            )

    class AdminApiOptionsView(HomeAssistantView):
        """GET /api/ha_read_only/admin/api/options – Available domains/areas/entities."""

        url = f"{API_PREFIX}/admin/api/options"
        name = f"{DOMAIN}:admin_api_options"
        requires_auth = True

        async def get(self, request: web.Request) -> web.Response:
            hass = request.app["hass"]
            domains = sorted(set(s.domain for s in hass.states.async_all()))
            ent_reg = async_get_entity_registry(hass)
            areas = sorted(set(
                e.area_id for e in ent_reg.entities.values() if e.area_id
            ))
            entities = sorted(
                e.entity_id for e in ent_reg.entities.values()
            )
            return web.json_response({
                "domains": domains,
                "areas": areas,
                "entities": entities,
            })

    class AdminApiTokensView(HomeAssistantView):
        """Admin API for token CRUD."""

        url = f"{API_PREFIX}/admin/api/tokens"
        name = f"{DOMAIN}:admin_api_tokens"
        requires_auth = True

        async def get(self, request: web.Request) -> web.Response:
            hass = request.app["hass"]
            result = []
            for entry in hass.config_entries.async_entries(DOMAIN):
                d = entry.data
                result.append({
                    "entry_id": entry.entry_id,
                    "name": entry.title,
                    "token_masked": _mask_token(d.get(CONF_TOKEN, "")),
                    "allowed_domains": d.get(CONF_ALLOWED_DOMAINS, []),
                    "allowed_areas": d.get(CONF_ALLOWED_AREAS, []),
                    "allowed_entities": d.get(CONF_ALLOWED_ENTITIES, []),
                    "allowed_patterns": d.get(CONF_ALLOWED_PATTERNS, ""),
                    "blocked_entities": d.get(CONF_BLOCKED_ENTITIES, []),
                    "blocked_patterns": d.get(CONF_BLOCKED_PATTERNS, ""),
                    "provide_entities_list": d.get(CONF_PROVIDE_ENTITIES_LIST, False),
                    "return_only_ids": d.get(CONF_RETURN_ONLY_IDS, False),
                    "include_attributes": d.get(CONF_INCLUDE_ATTRIBUTES, True),
                })
            return web.json_response(result)

        async def post(self, request: web.Request) -> web.Response:
            hass = request.app["hass"]
            try:
                data = await request.json()
            except Exception:
                return web.json_response({"error": "Invalid JSON"}, status=400)
            name = data.get("name", "").strip()
            if not name:
                return web.json_response({"error": "Name is required"}, status=400)
            token = secrets.token_urlsafe(32)
            entry_data = {
                CONF_TOKEN_NAME: name,
                CONF_TOKEN: token,
                CONF_ALLOWED_DOMAINS: data.get("domains", []),
                CONF_ALLOWED_AREAS: [],
                CONF_ALLOWED_ENTITIES: [],
                CONF_ALLOWED_PATTERNS: data.get("patterns", ""),
                CONF_BLOCKED_ENTITIES: data.get("blockedEntities", []),
                CONF_BLOCKED_PATTERNS: data.get("blockedPatterns", ""),
                CONF_PROVIDE_ENTITIES_LIST: data.get("provideEntitiesList", False),
                CONF_RETURN_ONLY_IDS: data.get("returnOnlyIds", False),
                CONF_INCLUDE_ATTRIBUTES: data.get("includeAttributes", True),
            }
            from homeassistant.config_entries import SOURCE_USER, ConfigEntry
            new_entry = ConfigEntry(
                version=1,
                domain=DOMAIN,
                title=name,
                data=entry_data,
                source=SOURCE_USER,
            )
            hass.config_entries.async_add(new_entry)
            hass.data.setdefault(DOMAIN, {})[new_entry.entry_id] = entry_data
            _LOGGER.info("Admin: New token '%s' created", name)
            return web.json_response({"name": name, "token": token, "entry_id": new_entry.entry_id}, status=201)

    class AdminApiTokenView(HomeAssistantView):
        """GET/PUT/DELETE a single token."""

        url = f"{API_PREFIX}/admin/api/tokens/{{entry_id}}"
        name = f"{DOMAIN}:admin_api_token"
        requires_auth = True

        async def get(self, request: web.Request, entry_id: str) -> web.Response:
            hass = request.app["hass"]
            entry = hass.config_entries.async_get_entry(entry_id)
            if not entry or entry.domain != DOMAIN:
                return web.json_response({"error": "Not found"}, status=404)
            d = entry.data
            return web.json_response({
                "entry_id": entry.entry_id,
                "name": entry.title,
                "token_masked": _mask_token(d.get(CONF_TOKEN, "")),
                "allowed_domains": d.get(CONF_ALLOWED_DOMAINS, []),
                "allowed_areas": d.get(CONF_ALLOWED_AREAS, []),
                "allowed_entities": d.get(CONF_ALLOWED_ENTITIES, []),
                "allowed_patterns": d.get(CONF_ALLOWED_PATTERNS, ""),
                "blocked_entities": d.get(CONF_BLOCKED_ENTITIES, []),
                "blocked_patterns": d.get(CONF_BLOCKED_PATTERNS, ""),
                "provide_entities_list": d.get(CONF_PROVIDE_ENTITIES_LIST, False),
                "return_only_ids": d.get(CONF_RETURN_ONLY_IDS, False),
                "include_attributes": d.get(CONF_INCLUDE_ATTRIBUTES, True),
            })

        async def put(self, request: web.Request, entry_id: str) -> web.Response:
            hass = request.app["hass"]
            entry = hass.config_entries.async_get_entry(entry_id)
            if not entry or entry.domain != DOMAIN:
                return web.json_response({"error": "Not found"}, status=404)
            try:
                data = await request.json()
            except Exception:
                return web.json_response({"error": "Invalid JSON"}, status=400)
            new_data = dict(entry.data)
            if "name" in data:
                new_data[CONF_TOKEN_NAME] = data["name"].strip()
            if "domains" in data:
                new_data[CONF_ALLOWED_DOMAINS] = data["domains"]
            if "patterns" in data:
                new_data[CONF_ALLOWED_PATTERNS] = data["patterns"]
            if "blockedEntities" in data:
                new_data[CONF_BLOCKED_ENTITIES] = data["blockedEntities"]
            if "blockedPatterns" in data:
                new_data[CONF_BLOCKED_PATTERNS] = data["blockedPatterns"]
            if "provideEntitiesList" in data:
                new_data[CONF_PROVIDE_ENTITIES_LIST] = data["provideEntitiesList"]
            if "returnOnlyIds" in data:
                new_data[CONF_RETURN_ONLY_IDS] = data["returnOnlyIds"]
            if "includeAttributes" in data:
                new_data[CONF_INCLUDE_ATTRIBUTES] = data["includeAttributes"]
            title = new_data.get(CONF_TOKEN_NAME, entry.title)
            hass.config_entries.async_update_entry(entry, title=title, data=new_data)
            hass.data.setdefault(DOMAIN, {})[entry_id] = new_data
            _LOGGER.info("Admin: Token '%s' updated", title)
            return web.json_response({"success": True})

        async def delete(self, request: web.Request, entry_id: str) -> web.Response:
            hass = request.app["hass"]
            entry = hass.config_entries.async_get_entry(entry_id)
            if not entry or entry.domain != DOMAIN:
                return web.json_response({"error": "Not found"}, status=404)
            name = entry.title
            await hass.config_entries.async_remove(entry_id)
            hass.data.get(DOMAIN, {}).pop(entry_id, None)
            _LOGGER.info("Admin: Token '%s' deleted", name)
            return web.json_response({"success": True})

    class AdminApiTokenRegenerateView(HomeAssistantView):
        """POST to regenerate a token."""

        url = f"{API_PREFIX}/admin/api/tokens/{{entry_id}}/regenerate"
        name = f"{DOMAIN}:admin_api_token_regenerate"
        requires_auth = True

        async def post(self, request: web.Request, entry_id: str) -> web.Response:
            hass = request.app["hass"]
            entry = hass.config_entries.async_get_entry(entry_id)
            if not entry or entry.domain != DOMAIN:
                return web.json_response({"error": "Not found"}, status=404)
            new_data = dict(entry.data)
            new_token = secrets.token_urlsafe(32)
            new_data[CONF_TOKEN] = new_token
            hass.config_entries.async_update_entry(entry, data=new_data)
            hass.data.setdefault(DOMAIN, {})[entry_id] = new_data
            _LOGGER.info("Admin: Token '%s' regenerated", entry.title)
            return web.json_response({"name": entry.title, "token": new_token})

    _AdminView = AdminPanelView
    _AdminApiView = AdminApiTokensView

    class StatesView(HomeAssistantView):
        """GET /api/ha_read_only/states – all allowed states."""

        url = f"{API_PREFIX}/states"
        name = f"{DOMAIN}:states"
        requires_auth = False

        async def get(self, request: web.Request) -> web.Response:
            hass = request.app["hass"]
            ip = _get_client_ip(request)
            token = request.headers.get(HEADER_TOKEN_NAME)

            if not _rate_limit(("ip", ip)):
                _LOGGER.warning("Rate limit exceeded for IP %s", ip)
                return web.json_response({"error": "Too many requests"}, status=429)
            if token and not _rate_limit(("token", token)):
                _LOGGER.warning("Rate limit exceeded for token")
                return web.json_response({"error": "Too many requests"}, status=429)

            if not token:
                _LOGGER.warning("Request without token from IP %s", ip)
                return web.json_response({"error": "Token required"}, status=401)

            entry = _find_entry_by_token(hass, token)
            if not entry:
                _LOGGER.warning("Invalid token attempt from IP %s", ip)
                return web.json_response({"error": "Invalid token"}, status=401)

            try:
                states = _get_allowed_states(hass, entry.data)
                token_name = _get_token_name(hass, token)
                _LOGGER.debug(
                    "States request – token: %s, entities: %d",
                    token_name, len(states),
                )
                return web.json_response(states)
            except Exception as err:
                _LOGGER.exception("Error processing states request: %s", err)
                return web.json_response({"error": str(err)}, status=500)

    class SingleStateView(HomeAssistantView):
        """GET /api/ha_read_only/states/<entity_id> – single state."""

        url = f"{API_PREFIX}/states/{{entity_id}}"
        name = f"{DOMAIN}:single_state"
        requires_auth = False

        async def get(self, request: web.Request, entity_id: str) -> web.Response:
            hass = request.app["hass"]
            ip = _get_client_ip(request)
            token = request.headers.get(HEADER_TOKEN_NAME)

            if not _rate_limit(("ip", ip)):
                _LOGGER.warning("Rate limit exceeded for IP %s", ip)
                return web.json_response({"error": "Too many requests"}, status=429)
            if token and not _rate_limit(("token", token)):
                _LOGGER.warning("Rate limit exceeded for token")
                return web.json_response({"error": "Too many requests"}, status=429)

            if not token:
                _LOGGER.warning("Request without token from IP %s", ip)
                return web.json_response({"error": "Token required"}, status=401)

            entry = _find_entry_by_token(hass, token)
            if not entry:
                _LOGGER.warning("Invalid token attempt from IP %s", ip)
                return web.json_response({"error": "Invalid token"}, status=401)

            if not _is_entity_allowed(entity_id, entry.data, hass):
                token_name = _get_token_name(hass, token)
                _LOGGER.info(
                    "Blocked entity %s for token %s", entity_id, token_name,
                )
                return web.json_response({"error": "Entity not allowed"}, status=403)

            state = hass.states.get(entity_id)
            if not state:
                return web.json_response({"error": "Entity not found"}, status=404)

            include_attrs = entry.data.get(CONF_INCLUDE_ATTRIBUTES, True)
            return web.json_response(_build_response(state, include_attrs))

    class EntityListView(HomeAssistantView):
        """GET /api/ha_read_only/entities – list of allowed entities."""

        url = f"{API_PREFIX}/entities"
        name = f"{DOMAIN}:entities"
        requires_auth = False

        async def get(self, request: web.Request) -> web.Response:
            hass = request.app["hass"]
            ip = _get_client_ip(request)
            token = request.headers.get(HEADER_TOKEN_NAME)

            if not _rate_limit(("ip", ip)):
                _LOGGER.warning("Rate limit exceeded for IP %s", ip)
                return web.json_response({"error": "Too many requests"}, status=429)
            if token and not _rate_limit(("token", token)):
                _LOGGER.warning("Rate limit exceeded for token")
                return web.json_response({"error": "Too many requests"}, status=429)

            if not token:
                _LOGGER.warning("Request without token from IP %s", ip)
                return web.json_response({"error": "Token required"}, status=401)

            entry = _find_entry_by_token(hass, token)
            if not entry:
                _LOGGER.warning("Invalid token attempt from IP %s", ip)
                return web.json_response({"error": "Invalid token"}, status=401)

            if not entry.data.get(CONF_PROVIDE_ENTITIES_LIST, False):
                return web.json_response(
                    {"error": "Entity list endpoint is not enabled for this token"},
                    status=403,
                )

            try:
                states = _get_allowed_states(hass, entry.data)
                only_ids = entry.data.get(CONF_RETURN_ONLY_IDS, False)
                token_name = _get_token_name(hass, token)
                _LOGGER.debug(
                    "Entity list request – token: %s, entities: %d",
                    token_name, len(states),
                )
                if only_ids:
                    return web.json_response([s["entity_id"] for s in states])
                return web.json_response(states)
            except Exception as err:
                _LOGGER.exception("Error processing entities request: %s", err)
                return web.json_response({"error": str(err)}, status=500)
