# 🚀 Verbesserungsvorschläge: HA Read-Only API → Community Plugin

## Aktueller Stand

Das Plugin funktioniert grundsätzlich gut: Token-Verwaltung per Sidebar-Dashboard, drei öffentliche API-Endpunkte, Rate-Limiting, Usage-Tracking. Die Basis steht – aber für ein **Community-taugliches Plugin** fehlen einige wichtige Dinge.

---

## 🔴 Priorität 1: Sicherheit (kritisch)

### 1.1 Admin-Endpunkte absichern
Aktuell haben **alle** Admin-Endpoints `requires_auth = False`. Jeder im Netzwerk kann Tokens erstellen/löschen.

**Lösung:** Admin-Endpoints auf `requires_auth = True` setzen und die Auth-Tokens im Dashboard-Frontend per `Authorization: Bearer`-Header mitsenden. Das Dashboard kann den HA-Auth-Token aus dem übergeordneten Fenster beziehen:
```javascript
// Im iframe den HA-Auth-Token holen
const hassToken = window.parent?.hassConnection?.auth?.accessToken;
```

> [!CAUTION]
> Das ist der **wichtigste Fix** bevor das Plugin veröffentlicht wird. Ohne diesen kann jeder im Netzwerk die gesamte API kontrollieren.

### 1.2 Tokens hashen statt im Klartext speichern
Aktuell werden Tokens im Klartext in `.storage/ha_read_only.storage` gespeichert. Wenn jemand Zugriff auf das Dateisystem hat, hat er alle Tokens.

**Lösung:**
- Beim Erstellen: Token einmal im Klartext zeigen, dann nur den SHA-256-Hash speichern
- Bei API-Anfragen: eingehenden Token hashen und gegen gespeicherten Hash vergleichen
- Aufwand: ~30 Minuten

### 1.3 CORS-Header setzen
Aktuell kann jede beliebige Website im Browser API-Anfragen an deine HA-Instanz senden.

**Lösung:** Explizite `Access-Control-Allow-Origin`-Header auf den API-Endpunkten setzen.

---

## 🟠 Priorität 2: HACS & Community-Kompatibilität

### 2.1 HACS-Manifest hinzufügen
Damit das Plugin über HACS installierbar ist, fehlt eine `hacs.json`:

```json
{
  "name": "HA Read-Only API",
  "render_readme": true,
  "homeassistant": "2023.5.0"
}
```

### 2.2 Übersetzungsdateien (i18n)
Aktuell ist das Dashboard hardcoded auf Deutsch. Für die Community braucht es:
- `translations/en.json` (Englisch als Basis)
- `translations/de.json` (Deutsch)
- Dashboard-Texte über eine JS-Variable steuerbar machen, die je nach HA-Sprache geladen wird

### 2.3 `strings.json` auf Deutsch ergänzen
Die Config-Flow-Texte sind aktuell auf Englisch – das passt nicht zum deutschen Dashboard.

### 2.4 Versionierung & Changelog
- `CHANGELOG.md` erstellen
- Semantic Versioning konsequent nutzen
- GitHub Releases mit Tags

### 2.5 Screenshots im README
Community-Plugins leben von guten Screenshots. Mindestens:
- Dashboard-Übersicht mit Token-Liste
- Token-Erstellen-Modal mit Domain-Auswahl
- Usage-Statistiken
- Anleitung-Tab

---

## 🟡 Priorität 3: Fehlende Features

### 3.1 Token-Ablaufdatum
Tokens laufen aktuell nie ab. Für sicherheitsbewusste Nutzer wäre ein optionales Ablaufdatum wichtig.

```python
# Im Token-Objekt:
"expires_at": 1699999999.0  # Unix-Timestamp oder None
```

### 3.2 Area-basiertes Filtering
Die README erwähnt "Areas" als Feature, aber es ist nicht implementiert. HA kennt Areas über die Entity Registry:
```python
from homeassistant.helpers.area_registry import async_get as async_get_area_registry
```

### 3.3 IP-Whitelist pro Token
Bestimmte Tokens nur von bestimmten IPs aus erlauben:
```json
{
  "allowed_ips": ["192.168.1.100", "10.0.0.0/24"]
}
```

### 3.4 Webhook-Benachrichtigung
Optional: Bei Token-Nutzung oder -Erstellung einen Webhook auslösen (für Monitoring).

### 3.5 Entity-Suche im Dashboard
Bei Systemen mit 500+ Entitäten braucht das Domain-Grid einen Suchfilter:
- Textfeld zum Filtern der Domain-Liste
- Eventuell auch einzelne Entitäten auswählbar (mit Suchfeld)

### 3.6 Token-Nutzungslog im Dashboard
Aktuell zeigt "Nutzung" nur Gesamtzahlen. Besser wäre:
- Letzte 50 Anfragen mit Timestamp, IP, Endpoint, Status
- Grafische Darstellung (z.B. Anfragen pro Stunde, einfacher SVG-Chart)

### 3.7 Persistenter Rate-Limit-Cache
`_RATE_LIMIT_CACHE` ist aktuell ein Dict im Speicher – geht bei Neustart verloren. Für die meisten Fälle OK, aber erwähnenswert.

---

## 🔵 Priorität 4: Code-Qualität

### 4.1 Tests schreiben
Aktuell gibt es **keine Tests**. Für ein Community-Plugin sind mindestens nötig:
- Unit-Tests für `_is_entity_allowed()` (verschiedene Filter-Kombinationen)
- Unit-Tests für `_rate_limit()`
- Integration-Tests für die API-Endpunkte
- Pytest + `pytest-homeassistant-custom-component`

### 4.2 Type Hints vervollständigen
Einige Funktionen haben unvollständige Type Hints. Für die Community:
```python
async def get(self, request: web.Request) -> web.Response:
```

### 4.3 Tote Konstanten aufräumen
In `const.py` sind Konstanten definiert, die nirgends verwendet werden:
- `CONF_ALLOWED_AREAS`, `CONF_ALLOWED_ENTITIES`, `CONF_BLOCKED_ENTITIES`
- `CONF_PROVIDE_ENTITIES_LIST`, `CONF_RETURN_ONLY_IDS`
- `CONF_LOG_LEVEL`

Entweder implementieren oder entfernen.

### 4.4 Services implementieren oder entfernen
`services.yaml` existiert, aber die Services (`regenerate_token`, `list_tokens`, etc.) sind im aktuellen Code nicht registriert. Das verwirrt Nutzer.

### 4.5 `panel/panel.js` aufräumen
Der Ordner `panel/` mit `panel.js` wird nicht mehr verwendet (wir nutzen jetzt den Built-in Iframe). Sollte entfernt werden.

---

## 🟢 Priorität 5: UX-Verbesserungen

### 5.1 Toast-Benachrichtigungen statt `alert()`
`alert()` blockiert den UI-Thread und ist nicht kopierbar. Besser:
- Eigene Toast-Komponente (animierte Meldung am oberen Rand)
- Bereits beim "Einstellungen gespeichert" verwendet

### 5.2 Responsive Design
Das Dashboard funktioniert auf dem Desktop, aber auf Mobilgeräten (z.B. HA-App) fehlt Responsive-Optimierung:
- Burger-Menü für die Navigation
- Stacked Layout für Token-Cards
- Touch-freundliche Buttons

### 5.3 Dark/Light Mode
HA unterstützt beide Themes. Das Dashboard ist hardcoded dunkel. Besser:
```css
@media (prefers-color-scheme: light) {
  :root { --bg: #f8fafc; --card: white; --t: #1e293b; }
}
```

### 5.4 Ladeanimationen
Aktuell "springt" die Oberfläche wenn Daten geladen werden. Skeleton-Loader oder Spinner wären professioneller.

### 5.5 Bestätigungsdialoge verschönern
`confirm()` durch eigene modale Dialoge ersetzen (wie beim Token-Erfolg).

---

## 📋 Empfohlene Reihenfolge

| # | Aufgabe | Aufwand | Impact |
|---|---------|---------|--------|
| 1 | Admin-Auth absichern | 2-3h | 🔴 Kritisch |
| 2 | Token-Hashing | 1h | 🔴 Sicherheit |
| 3 | Tests schreiben | 3-4h | 🟠 Qualität |
| 4 | HACS-Manifest + Screenshots | 30min | 🟠 Sichtbarkeit |
| 5 | Übersetzung (i18n) | 2h | 🟠 Community |
| 6 | Tote Konstanten/Services aufräumen | 30min | 🔵 Sauberkeit |
| 7 | `panel/` Ordner entfernen | 5min | 🔵 Sauberkeit |
| 8 | Token-Ablaufdatum | 1-2h | 🟡 Feature |
| 9 | Area-Filter | 2h | 🟡 Feature |
| 10 | Toast statt alert() | 1h | 🟢 UX |
| 11 | Responsive Design | 2h | 🟢 UX |
| 12 | Entity-Suche im Modal | 1h | 🟡 Feature |

---

## Zusammenfassung

**Das Plugin hat eine solide Basis.** Die größten Hürden für ein Community-Release sind:

1. **Sicherheit** – Admin-Endpoints müssen abgesichert werden
2. **HACS** – Manifest + Screenshots sind Pflicht
3. **Tests** – Ohne Tests akzeptieren viele Community-Reviewer kein Plugin
4. **i18n** – Deutsch als einzige Sprache schließt 80% der HA-Community aus

Wenn du mit **Punkt 1-4** anfängst, hast du ein veröffentlichungsfähiges Plugin. Der Rest sind Verbesserungen, die über Zeit kommen können.
