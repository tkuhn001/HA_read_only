# 🚀 Verbesserungsvorschläge: HA Read-Only API → Community Plugin

## Aktueller Stand

Das Plugin funktioniert gut: Token-Verwaltung per Sidebar-Dashboard, öffentliche Read-Only-API (`/states`, `/entities`, `/help`), Rate-Limiting, Usage-Log mit Chart, Areas/IP-Whitelist/Ablaufdatum pro Token, Webhooks. **Priorität 3 ist umgesetzt.** Für ein **Community-Release** fehlen vor allem Sicherheit (Priorität 1), HACS/i18n (Priorität 2) und Tests.

---

## 🔴 Priorität 1: Sicherheit (kritisch)

### 1.1 Admin-Endpunkte absichern ✅ (umgesetzt v0.3.6)
- [x] Admin-API-Endpoints auf `requires_auth = True` gesetzt
- [x] Frontend sendet `Authorization: Bearer` Token aus Parent-Fenster
- [x] `require_admin=True` im Sidebar-Panel gesetzt

### 1.2 Tokens hashen statt im Klartext speichern ✅ (umgesetzt v0.3.9)
- [x] SHA-256-Hashing für Tokens implementiert
- [x] `_hash_token()` und `_verify_token()` in `api.py`
- [x] `_find_token_data()` prüft `token_hash` mit Fallback auf Plaintext (Migration)
- [x] Token-Erstellung und Regenerierung speichern nur noch Hash
- [x] Alte Tokens im Klartext bleiben funktionell

### 1.3 CORS-Header setzen
Aktuell kann jede beliebige Website im Browser API-Anfragen an deine HA-Instanz senden.

**Lösung:** Explizite `Access-Control-Allow-Origin`-Header auf den API-Endpunkten setzen.

---

## 🟠 Priorität 2: HACS & Community-Kompatibilität ✅ (umgesetzt v0.3.3)

### 2.1 HACS-Manifest hinzufügen ✅
- [x] `hacs.json` erstellt mit `name` und `render_readme`
- [x] GitHub Releases + Tags für HACS-Versionierung

### 2.2 Übersetzungsdateien (i18n) ✅
- [x] `translations/en.json` (Englisch)
- [x] `translations/de.json` (Deutsch)
- [x] `strings.json` auf Deutsch aktualisiert

### 2.3 `strings.json` auf Deutsch ergänzen ✅
- [x] Config-Flow-Texte sind jetzt auf Deutsch

### 2.4 Versionierung & Changelog ✅
- [x] `CHANGELOG.md` erstellt
- [x] Semantic Versioning (aktuell v0.3.3)
- [x] GitHub Releases mit Tags

### 2.5 Screenshots im README ✅ (umgesetzt v0.3.9)
- [x] Dashboard-Übersicht mit Token-Liste
- [x] Token-Erstellen-Modal mit Domain-Auswahl
- [x] Usage-Statistiken
- [x] Einstellungen-Tab

---

## 🟡 Priorität 3: Fehlende Features ✅ (umgesetzt v0.3.0)

### 3.1 Token-Ablaufdatum ✅
- [x] Optionales `expires_at` (Unix-Timestamp) im Token-Objekt und Dashboard
- [x] Abgelaufene Tokens → `401 Token expired`

### 3.2 Area-basiertes Filtering ✅
- [x] Areas über Entity Registry, Auswahl im Dashboard
- [x] Whitelist-Logik: Domain / Muster / Area / einzelne Entität

### 3.3 IP-Whitelist pro Token ✅
- [x] `allowed_ips` mit Einzel-IP und CIDR (z.B. `10.0.0.0/24`)
- [x] Falsche IP → `403 IP not allowed`

### 3.4 Webhook-Benachrichtigung ✅
- [x] Globale Webhook-URL in Einstellungen
- [x] Optional bei API-Anfragen (200) und Token-Erstellung

### 3.5 Entity-Suche im Dashboard ✅
- [x] Suchfilter für Domains und Areas
- [x] Entitäten-Suche mit Auswahl und Chips

### 3.6 Token-Nutzungslog im Dashboard ✅
- [x] Letzte 50 Anfragen (Zeit, IP, Endpunkt, Status)
- [x] SVG-Balkendiagramm (Anfragen pro Stunde, 24h)

### 3.7 Persistenter Rate-Limit-Cache ✅
- [x] Rate-Limits in `handler.data["rate_limit"]` persistiert (überlebt Neustart)

### 3.8 API-Hilfe-Endpunkt ✅
- [x] `GET /api/ha_read_only/help` – Kurzübersicht aller Endpunkte (ohne Token)

---

## 🔵 Priorität 4: Code-Qualität

### 4.1 Tests schreiben
Aktuell gibt es **keine Tests** – weder Testdateien, noch pytest-Konfiguration, noch Test-Dependencies. Für ein Community-Plugin sind umfangreiche Tests nötig.

#### Test-Infrastruktur
- `pytest`, `pytest-asyncio`, `pytest-homeassistant-custom-component` als Dev-Dependencies
- `tests/`-Ordner mit `conftest.py` (HA-Fixtures: `hass`, `hass_client`, `hass_storage`, `create_registries`)
- `pytest.ini` oder `pyproject.toml` mit `asyncio_mode = auto` und Test-Pfad
- CI (GitHub Actions): `pytest` bei jedem Push/PR, ggf. Coverage-Badge

#### Unit-Tests (reine Logik, keine HA-Mocks nötig)

| Funktion | Testfälle |
|---|---|
| `_hash_token()` | Gleicher Input → gleicher Hash; unterschiedliche Inputs → unterschiedliche Hashes |
| `_verify_token()` | Korrekter Token → True; falscher Token → False; leere Strings |
| `_mask_token()` | Langer Token → `"xxxx…..."` (8+3); kurzer Token → unverändert |
| `_rate_limit_key()` | Tuple `("ip","1.2.3.4")` → `"ip\|1.2.3.4"` |
| `_rate_limit()` | Unter Limit → erlaubt; über Limit → blockiert; Fenster läuft ab → wieder erlaubt; per-Token-Limit überschreibt globales |
| `_is_token_valid()` | Kein Ablauf → True; Ablauf in Zukunft → True; Ablauf in Vergangenheit → False |
| `_ip_matches()` | Exakte IP → True; andere IP → False; CIDR `10.0.0.0/24` → True für 10.0.0.x; ungültige IP → False |
| `_is_ip_allowed()` | Leere Liste → True; Client-IP gelistet → True; nicht gelistet → False |
| `_to_pattern_list()` | String mit Newlines → Liste; leere Liste → leere Liste; None → leere Liste; gemischte Liste |
| `_parse_ip_list()` | Komma-getrennt → Liste; Newline-getrennt → Liste; Leerzeichen trimmen |
| `_parse_expires_at()` | Unix-Timestamp (int/float) → float; ISO-String → float; None/"" → None; ungültiger String → None |
| `_is_entity_allowed()` | **Kernlogik**: Alle Domains erlaubt (keine Whitelist) → True; Domain in allowed_domains → True; Pattern matcht → True; Entity in allowed_entities → True; Area-ID matcht → True; blocked_patterns blockiert vor Whitelist; alle Whitelist leer → True; keine Bedingung erfüllt → False; mehrere Domains/Patterns/Areas gleichzeitig |
| `_build_response()` | `include_attrs=True` → inkl. `attributes`; `include_attrs=False` → nur `entity_id`+`state` |
| `_find_token_data()` | Hash-matched → Token gefunden; Plaintext-Fallback; kein Match → None |
| `_get_client_ip()` | `X-Forwarded-For` → erste IP; `peername` → IP; kein Header/Peer → `"unknown"` |
| `_compute_hourly_chart()` | 24 Buckets; Einträge innerhalb 24h → korrekter Bucket; alte Einträge → ignoriert |
| `_compute_hourly_chart_by_color()` | Buckets mit `by_color`-Aufschlüsselung; mehrere Token-Farben |
| `_compute_daily_usage()` | 7 Buckets pro Token; Einträge innerhalb 7 Tage → korrekter Tag |
| `_token_fields_from_request()` | Vollständiges Dict → gefülltes Dict; leeres Dict → Defaults |

#### Integration-Tests (API-Endpunkte mit Mock-HA)

| Endpunkt | Testfälle |
|---|---|
| `GET /help` | Gültiger Token → 200 + Hilfe-JSON; fehlender Token → 401; abgelaufener Token → 401; IP-Whitelist-Verletzung → 403; Rate-Limit → 429 |
| `GET /states` | Token ohne Filter → alle States; Token mit Domain-Filter → gefiltert; Token mit Area-Filter → gefiltert; Token mit Pattern → gefiltert; `include_attributes=false` → keine Attributes |
| `GET /states/{entity_id}` | Erlaubte Entity → 200 + State; nicht erlaubte Entity → 403; nicht existierende Entity → 404 |
| `GET /entities` | Ohne Filter → alle Entity-IDs; mit Filter → gefilterte IDs |
| `GET /admin/api/options` | Liefert Domains + Areas aus Registry |
| `GET /admin/api/entities` | Suchfilter `?q=sensor` → gefiltert; ohne Query → alle; max 150 Ergebnisse |
| `POST /admin/api/tokens` | Token anlegen → 201 + Token-Wert + ID; Felder werden korrekt gespeichert; Webhook wird gefeuert |
| `PUT /admin/api/tokens/{id}` | Existierendes Token updaten → 200; Felder überschreiben |
| `DELETE /admin/api/tokens/{id}` | Token löschen → 200; Token wirklich entfernt |
| `POST /admin/api/tokens/{id}/regenerate` | Token neu generieren → neuer Hash + increment regeneration_count |
| `GET /admin/api/stats` | Usage-Log, hourly/daily-Charts, Pie-Daten; `?token_id=`-Filter |
| `PUT /admin/api/tokens/{id}/stats` | Rate-Limit/Retention-Felder updaten |
| `GET /admin/api/config` | Config-Werte mit Defaults |
| `PUT /admin/api/config` | Config updaten → persistiert |
| `POST /admin/api/stats/cleanup` | Verwaiste Stats/Logs entfernen |

#### Storage- und Service-Tests

| Komponente | Testfälle |
|---|---|
| `ReadOnlyDataHandler` | `async_load()` bei leerem Store → Defaults; `async_save()` → persistiert; `_cleanup_stats()` → Retention angewendet, Log-Limit, 401s nach invalid_log |
| `_track_usage()` | Stats erhöhen; Usage-Log befüllen; Error-Zähler; Globale Limits; Webhook-Feuerung bei 200 |
| `_fire_webhook()` | URL gesetzt + Event enabled → POST; URL leer → nichts; HTTP-Error → log Warning |
| `list_tokens`-Service | Tokens mit maskierten Werten + Count |
| `get_token_info`-Service | Token gefunden → Details; nicht gefunden → `found: false` |

#### Empfohlene Dateistruktur
```
tests/
├── conftest.py              # HA-Fixtures, Mock-Handler, Token-Factory
├── pytest.ini
├── test_api_helpers.py       # Unit-Tests für _hash, _verify, _mask, _rate_limit_key
├── test_entity_allowed.py    # Unit-Tests für _is_entity_allowed (Kernlogik)
├── test_ip_filter.py         # Unit-Tests für _ip_matches, _is_ip_allowed, _parse_ip_list
├── test_rate_limit.py        # Unit-Tests für _rate_limit
├── test_parse_utils.py       # Unit-Tests für _to_pattern_list, _parse_expires_at etc.
├── test_charts.py            # Unit-Tests für _compute_hourly_chart, _compute_daily_usage
├── test_api_endpoints.py     # Integration-Tests für öffentliche API (/states, /entities, /help)
├── test_admin_api.py         # Integration-Tests für Admin-API (Token-CRUD, Stats, Config)
├── test_storage.py           # Tests für ReadOnlyDataHandler
├── test_services.py          # Tests für list_tokens/get_token_info-Services
└── test_config_flow.py       # Tests für ConfigFlow (mehrfach-Config, create_entry)
```

#### Besondere Hinweise
- **`_is_entity_allowed()` ist die komplexeste Funktion** (Domains, Patterns, Blocked-Patterns, Areas, Allowed-Entities, gemischte Kombinationen) – hier liegt der Fokus.
- **`_rate_limit()` hat Token-spezifische Limits** (max_requests + window) die globales Limit überschreiben – Edge Cases testen.
- **`pytest-homeassistant-custom-component`** stellt `hass`, `hass_client`, Entity/Area-Registry-Fixtures bereit – damit entfällt manuelles Mocking für Integration-Tests.
- **Coverage-Ziel:** >80% für `api.py`, >60% für `__init__.py`.
- **Race-Conditions:** `_rate_limit` und `_track_usage` sind nicht thread-safety-gesichert – ggf. Lock einführen.

### 4.2 Type Hints vervollständigen 🟡 (teilweise)
- [x] API-Views in `api.py` mit `web.Request` / `web.Response`
- [ ] Restliche Module (`config_flow.py`, `__init__.py`) vervollständigen

### 4.3 Tote Konstanten aufräumen 🟡 (teilweise)
- [x] `CONF_ALLOWED_AREAS`, `CONF_ALLOWED_ENTITIES` – Features nutzen diese Konzepte (Keys: `areas`, `allowed_entities`)
- [ ] Noch ungenutzt: `CONF_BLOCKED_ENTITIES`, `CONF_PROVIDE_ENTITIES_LIST`, `CONF_RETURN_ONLY_IDS` – entfernen oder implementieren

### 4.4 Services implementieren oder entfernen ✅ (umgesetzt v0.3.9)
- [x] `list_tokens` – Gibt alle Tokens mit maskiertem Wert zurück
- [x] `get_token_info` – Sucht Token nach Namen und liefert Details
- [x] `regenerate_token` und `delete_token` aus `services.yaml` entfernt (bereits über Dashboard verfügbar)

### 4.5 `panel/panel.js` aufräumen ✅
- [x] Ordner `panel/` entfernt (nutzen jetzt den Built-in Iframe)

---

## 🟢 Priorität 5: UX-Verbesserungen

### 5.1 Toast-Benachrichtigungen statt `alert()` ✅ (umgesetzt v0.3.6)
- [x] Toast-Komponente mit Animation (Slide-in/Slide-out) implementiert
- [x] Drei Typen: success (grün), error (rot), info (blau)
- [x] Auto-Close nach 3 Sekunden, Klick zum sofortigen Schließen
- [x] `alert()` durch Toasts ersetzt

### 5.2 Responsive Design
Das Dashboard funktioniert auf dem Desktop, aber auf Mobilgeräten (z.B. HA-App) fehlt Responsive-Optimierung:
- Burger-Menü für die Navigation
- Stacked Layout für Token-Cards
- Touch-freundliche Buttons

### 5.3 Dark/Light Mode ✅ (umgesetzt v0.3.6)
- [x] CSS-Variablen für Light Theme hinzugefügt
- [x] `prefers-color-scheme: light` Media Query implementiert
- [x] Alle UI-Komponenten (Modal, Inputs, Kalender, Navigation) angepasst

### 5.4 Ladeanimationen ✅ (umgesetzt v0.3.7)
- [x] Spinner mit Lade-Text für Token-Liste, Nutzungsstatistiken und Entity-Suche
- [x] CSS Skeleton-Loader Animation
- [x] Loading-States für Domain/Area-Picker im Modal
- [x] Fehlerbehandlung mit visuellem Feedback bei Lade-Fehlern

### 5.5 Bestätigungsdialoge verschönern ✅ (umgesetzt v0.3.6)
- [x] Eigener modaler Confirm-Dialog mit Titel, Nachricht und kontextuellen Buttons
- [x] `confirm()` durch async/await-basierten Dialog ersetzt
- [x] Individuelle Button-Texte je nach Kontext (Löschen, Neu generieren, etc.)

### 5.6 HTML als statische Datei servieren ✅ (umgesetzt v0.3.6)
- [x] `admin.html` als separate Datei ausgelagert
- [x] Via `hass.http.register_static_path` serviert
- [x] Kein HA-Neustart mehr bei HTML-Änderungen nötig

### 5.7 Statistik-Speicherung & Limits ✅ (umgesetzt v0.3.7)
- [x] Globale Limits: Max. Log-Einträge + Aufbewahrungsdauer (an/aus)
- [x] Pro Token: Individuelles Max-Anfragen-Limit
- [x] Statistikseite: Token-Filter-Dropdown + Pie Chart (Verteilung nach Zugang)
- [x] Automatische Bereinigung beim Speichern
- [x] Einstellungen-Seite: Übersicht aller Token-Limits

---

## 📋 Empfohlene Reihenfolge

| # | Aufgabe | Aufwand | Impact |
|--|---------|---------|--------|
| 1 | Admin-Auth absichern | 2-3h | 🔴 Kritisch |
| 2 | Token-Hashing | 1h | ✅ erledigt |
| 3 | CORS-Header setzen | 30min | 🟠 Sicherheit |
| 4 | Tests schreiben (Unit + Integration) | 8-12h | 🟠 Qualität |
| 5 | HACS-Manifest | 10min | ✅ erledigt |
| 6 | Übersetzung (i18n) | 2h | ✅ erledigt |
| 7 | Tote Konstanten/Services aufräumen | 30min | 🔵 Sauberkeit |
| 8 | `panel/` Ordner entfernen | 5min | ✅ erledigt |
| 9 | Token-Ablaufdatum | 1-2h | ✅ erledigt |
| 10 | Area-Filter | 2h | ✅ erledigt |
| 11 | Toast statt alert() | 1h | 🟢 UX |
| 12 | Responsive Design | 2h | 🟢 UX |
| 13 | Entity-Suche im Modal | 1h | ✅ erledigt |
| 14 | `/help`-Endpunkt | 15min | ✅ erledigt |
| 15 | Versionierung & Changelog | 30min | ✅ erledigt |
| 16 | Screenshots im README | 1h | ✅ erledigt |

---

## Zusammenfassung

**Das Plugin hat eine solide Basis.** Die größten Hürden für ein Community-Release sind:

1. **Tests** – Ohne Tests akzeptieren viele Community-Reviewer kein Plugin. Insbesondere Unit-Tests für `_is_entity_allowed()` (Kernlogik) und Integration-Tests für die API-Endpunkte sind kritisch.
2. **CORS-Header** – Für externe Web-Apps empfohlen.

Sicherheit (Token-Hashing, Admin-Auth), HACS-Integration, i18n, Versionierung, Changelog und Screenshots sind bereits umgesetzt. Der Rest sind Verbesserungen, die über Zeit kommen können.
