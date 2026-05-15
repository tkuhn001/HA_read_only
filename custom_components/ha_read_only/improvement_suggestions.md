# 🚀 Verbesserungsvorschläge: HA Read-Only API → Community Plugin

## Aktueller Stand

Das Plugin funktioniert gut: Token-Verwaltung per Sidebar-Dashboard, öffentliche Read-Only-API (`/states`, `/entities`, `/help`), Rate-Limiting, Usage-Log mit Chart, Areas/IP-Whitelist/Ablaufdatum pro Token, Webhooks. **Priorität 3 ist umgesetzt.** Für ein **Community-Release** fehlen vor allem Sicherheit (Priorität 1), HACS/i18n (Priorität 2) und Tests.

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
Aktuell gibt es **keine Tests**. Für ein Community-Plugin sind mindestens nötig:
- Unit-Tests für `_is_entity_allowed()` (verschiedene Filter-Kombinationen)
- Unit-Tests für `_rate_limit()`
- Integration-Tests für die API-Endpunkte
- Pytest + `pytest-homeassistant-custom-component`

### 4.2 Type Hints vervollständigen 🟡 (teilweise)
- [x] API-Views in `api.py` mit `web.Request` / `web.Response`
- [ ] Restliche Module (`config_flow.py`, `__init__.py`) vervollständigen

### 4.3 Tote Konstanten aufräumen 🟡 (teilweise)
- [x] `CONF_ALLOWED_AREAS`, `CONF_ALLOWED_ENTITIES` – Features nutzen diese Konzepte (Keys: `areas`, `allowed_entities`)
- [ ] Noch ungenutzt: `CONF_BLOCKED_ENTITIES`, `CONF_PROVIDE_ENTITIES_LIST`, `CONF_RETURN_ONLY_IDS` – entfernen oder implementieren

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
| 8 | Token-Ablaufdatum | 1-2h | ✅ erledigt |
| 9 | Area-Filter | 2h | ✅ erledigt |
| 10 | Toast statt alert() | 1h | 🟢 UX |
| 11 | Responsive Design | 2h | 🟢 UX |
| 12 | Entity-Suche im Modal | 1h | ✅ erledigt |
| 13 | `/help`-Endpunkt | 15min | ✅ erledigt |

---

## Zusammenfassung

**Das Plugin hat eine solide Basis.** Die größten Hürden für ein Community-Release sind:

1. **Sicherheit** – Admin-Endpoints müssen abgesichert werden
2. **HACS** – Manifest + Screenshots sind Pflicht
3. **Tests** – Ohne Tests akzeptieren viele Community-Reviewer kein Plugin
4. **i18n** – Deutsch als einzige Sprache schließt 80% der HA-Community aus

Wenn du mit **Punkt 1-4** anfängst, hast du ein veröffentlichungsfähiges Plugin. Der Rest sind Verbesserungen, die über Zeit kommen können.
