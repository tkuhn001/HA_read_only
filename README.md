# HA Read-Only API

Eine Home-Assistant-Custom-Integration zum Bereitstellen einer sicheren, **read-only** HTTP-API für externe Systeme mit integriertem Admin-Panel zur Token-Verwaltung.

Anders als der HA-Langzeit-Token (der Vollzugriff gewährt) erlaubt dieses Plugin die **granulare Steuerung**, welche Entitäten, Domains oder Bereiche ein bestimmtes externes System sehen darf – und das **ohne Schreibrechte**.

## Features

- **Sidebar-Admin-Panel** – Professionelle Management-Oberfläche in derHA-Seitenleiste
- **Token-basierte Authentifizierung** – pro externem System ein eigener Token
- **Feingranulare Berechtigungen**:
  - Einzelne Entitäten
  - Ganze Domains (`light`, `sensor`, …)
  - Bereiche (Areas)
  - Wildcard-Patterns (`light.kueche_*`, `sensor.*`)
  - Block-Liste zum expliziten Ausschließen
- **Read-Only** – keine POST/PUT/DELETE-Endpoints (außer Admin-API)
- **Konfigurierbar pro Token**:
  - Ob Attribute mitgeliefert werden
  - Ob der `/entities`-Endpoint aktiviert ist
  - Ob nur IDs zurückgegeben werden
- **Komfortabler Setup-Wizard** (6 Schritte) im HA-Frontend
- **Optionen-Flow** zum späteren Bearbeiten oder Token-Neu-Generieren
- **Rate-Limiting** – 100 Requests/Minute pro IP, 500/Minute pro Token
- **Logging** – Sicherheitsrelevante Ereignisse werden in den HA Core Logs protokolliert
- **Globale Token-Verwaltung** via Services oder Admin-Panel

## Installation

### Via HACS (empfohlen)

1. HACS öffnen → Integrationen → „…” → „Custom Repository”
2. `https://github.com/tkuhn001/HA_read_only` als Repository hinzufügen (Kategorie: Integration)
3. „HA Read-Only API” suchen und installieren
4. Home Assistant neu starten

### Manuell

1. `custom_components/ha_read_only/` in dein HA-`config`-Verzeichnis kopieren
2. Home Assistant neu starten

## Konfiguration

Nach der Installation erscheint ein neuer Eintrag **„HA Read-Only”** in der HA-Seitenleiste. Dort kannst du alle Tokens verwalten:

- **Token erstellen** – Name und Berechtigungen festlegen, Token wird angezeigt
- **Token bearbeiten** – Berechtigungen nachträglich ändern
- **Token neu generieren** – Alter wird sofort ungültig, neuer Token wird angezeigt
- **Token löschen** – Dauerhaft entfernen

Alternativ über den klassischen Weg:

1. Gehe zu **Einstellungen → Geräte & Dienste → Integration hinzufügen**
2. Suche nach **„HA Read-Only API”**
3. Folge dem 6-Schritte-Wizard:
   - **Schritt 1:** Token-Name (z. B. „Wetterdienst”)
   - **Schritt 2:** Domains & Bereiche auswählen
   - **Schritt 3:** Einzelne Entitäten oder Wildcard-Patterns
   - **Schritt 4:** Block-Liste (optional)
   - **Schritt 5:** API-Optionen (Entities-Liste, Attribute, …)
   - **Schritt 6:** Token wird angezeigt → **sofort kopieren!**

### Token bearbeiten

Über **Einstellungen → Geräte & Dienste → HA Read-Only API → Optionen** oder direkt im Admin-Panel (Sidebar) kannst du:
- Berechtigungen bearbeiten
- Token neu generieren (alter wird sofort ungültig)

## API-Endpoints

Alle Endpoints benötigen den Header:

```
X-HA-READONLY-TOKEN: <dein_token>
```

### `GET /api/ha_read_only/states`

Gibt alle erlaubten Zustände zurück.

**Beispiel:**
```bash
curl -H "X-HA-READONLY-TOKEN: abc123..." http://homeassistant.local:8123/api/ha_read_only/states
```

**Antwort:**
```json
[
  {
    "entity_id": "light.kueche",
    "state": "on",
    "attributes": {
      "friendly_name": "Küchenlicht",
      "brightness": 255
    }
  },
  {
    "entity_id": "sensor.temperatur",
    "state": "21.5"
  }
]
```

### `GET /api/ha_read_only/states/<entity_id>`

Gibt einen einzelnen Zustand zurück (nur wenn berechtigt).

```bash
curl -H "X-HA-READONLY-TOKEN: abc123..." \
  http://homeassistant.local:8123/api/ha_read_only/states/light.kueche
```

### `GET /api/ha_read_only/entities`

Gibt die Liste der berechtigten Entitäten zurück.  
Nur verfügbar, wenn pro Token aktiviert.

```bash
curl -H "X-HA-READONLY-TOKEN: abc123..." \
  http://homeassistant.local:8123/api/ha_read_only/entities
```

Mit Option „Nur IDs”:
```json
["light.kueche", "sensor.temperatur"]
```

Ohne diese Option (gleiches Format wie `/states`).

### Status-Codes

| Code | Bedeutung |
|------|-----------|
| 200 | Erfolg |
| 401 | Token fehlt oder ungültig |
| 403 | Entität nicht berechtigt / Endpoint deaktiviert |
| 404 | Entität nicht gefunden |
| 429 | Rate-Limit überschritten |
| 500 | Interner Fehler |

## Admin-API (nur für das integrierte Admin-Panel)

Die folgenden Endpoints sind **nur für HA-Administratoren** zugänglich (Session-Auth, nicht Custom-Token) und werden vom Admin-Panel in der Seitenleiste genutzt:

| Methode | Endpoint | Beschreibung |
|--------|----------|-------------|
| GET | `/api/ha_read_only/admin` | Admin-Panel HTML-Seite |
| GET | `/api/ha_read_only/admin/api/options` | Verfügbare Domains, Areas, Entities |
| GET | `/api/ha_read_only/admin/api/tokens` | Alle Tokens auflisten |
| POST | `/api/ha_read_only/admin/api/tokens` | Neuen Token erstellen |
| GET | `/api/ha_read_only/admin/api/tokens/{entry_id}` | Token-Details abrufen |
| PUT | `/api/ha_read_only/admin/api/tokens/{entry_id}` | Token aktualisieren |
| DELETE | `/api/ha_read_only/admin/api/tokens/{entry_id}` | Token löschen |
| POST | `/api/ha_read_only/admin/api/tokens/{entry_id}/regenerate` | Token neu generieren |

## Services

### `ha_read_only.regenerate_token`

Erzeugt einen neuen Token für einen bestehenden Eintrag.

**Felder:**

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `old_token` | string (optional) | Der aktuelle Token |
| `token_name` | string (optional) | Alternativ: Name des Eintrags |

Eines der beiden Felder muss angegeben werden.

**Beispiel via Developer-Tools → Aktionen:**
```yaml
service: ha_read_only.regenerate_token
data:
  old_token: "abc123..."
```

### `ha_read_only.list_tokens`

Listet alle konfigurierten Tokens mit Namen und maskierten Token-Werten auf. Keine Felder erforderlich.

### `ha_read_only.get_token_info`

Zeigt die vollständige Konfiguration eines Tokens an (Token-Wert maskiert).

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `token_name` | string (erforderlich) | Name des Tokens |

### `ha_read_only.delete_token`

Löscht einen Token-Eintrag dauerhaft. Der Token ist danach sofort ungültig.

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `token_name` | string (erforderlich) | Name des Tokens |

## Rate-Limiting

Die API-Endpoints sind durch ein Rate-Limiting geschützt:

- **100 Requests pro Minute** pro IP-Adresse
- **500 Requests pro Minute** pro Token

Bei Überschreitung wird HTTP 429 zurückgegeben. Die Limits können in `const.py` angepasst werden.

## Logging

- Normale API-Requests: `DEBUG`-Level (nur sichtbar bei aktiviertem Debug-Logging)
- Fehlgeschlagene Authentifizierungen: `WARNING`-Level
- Rate-Limit-Überschreitungen: `WARNING`-Level
- Admin-Aktionen (Token erstellen/bearbeiten/löschen): `INFO`-Level

Die Logs sind in den HA Core Logs einsehbar (**Einstellungen → System → Protokolle**).

## Berechtigungs-Logik

Die Sichtbarkeit einer Entität wird wie folgt bestimmt:

```python
sichtbar = (
    (keine Einschränkungen)
    ODER (domain in allowed_domains)
    ODER (entity_id in allowed_entities)
    ODER (area in allowed_areas)
    ODER (pattern match)
)
UND NICHT (
    (entity_id in blocked_entities)
    ODER (pattern match in blocked_patterns)
)
```

Wenn alle Allow-Listen leer sind, sind alle Entitäten erlaubt (Block-Liste schränkt ein).

### Pattern-Syntax

| Pattern | Bedeutung |
|---------|-----------|
| `light.*` | Alle Entitäten der Domain `light` |
| `sensor.outside_*` | Alle Sensoren mit Prefix `outside_` |
| `*_temperature` | Alle Entitäten, die auf `_temperature` enden |
| `*` | Alle Entitäten |

## Sicherheitshinweise

- Die API-Endpoints sind **nicht** durch die HA-Standard-Authentifizierung geschützt – der Token ist der einzige Schutz
- Das Admin-Panel ist **nur für HA-Administratoren** zugänglich (Session-Auth)
- Verwende die Integration **nur in vertrauenswürdigen Netzwerken** oder schalte einen Reverse-Proxy (z. B. Nginx) mit IP-Restriktion vor
- Ein kompromittierter Token erlaubt das Lesen der für ihn freigegebenen Daten → bei Verdacht einfach neu generieren (im Admin-Panel oder via Service)

## Entwicklung

Built with Python 3.11+ and the Home Assistant Integration Framework.

```bash
# Syntax-Check
python -m py_compile custom_components/ha_read_only/*.py
```

## Lizenz

MIT
