# 🚀 Verbesserungsvorschläge: HA Read-Only API → Community Plugin

## Aktueller Stand

Das Plugin funktioniert gut: Token-Verwaltung per Sidebar-Dashboard, öffentliche Read-Only-API (`/states`, `/entities`, `/help`), Rate-Limiting, Usage-Log mit Chart, Areas/IP-Whitelist/Ablaufdatum pro Token, Webhooks. **Priorität 3 ist umgesetzt.** Für ein **Community-Release** fehlen vor allem Sicherheit (Priorität 1), HACS/i18n (Priorität 2) und Tests.

---

## 🔴 Priorität 1: Sicherheit (kritisch)

### 1.1 Admin-Endpunkte absichern ✅ (umgesetzt v0.3.6)
- [x] Admin-API-Endpoints auf `requires_auth = True` gesetzt
- [x] Frontend sendet `Authorization: Bearer` Token aus Parent-Fenster
- [x] `require_admin=True` im Sidebar-Panel gesetzt

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

### 2.5 Screenshots im README
- [ ] Dashboard-Übersicht mit Token-Liste
- [ ] Token-Erstellen-Modal mit Domain-Auswahl
- [ ] Usage-Statistiken
- [ ] Anleitung-Tab

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
|---|---------|---------|--------|
| 1 | Admin-Auth absichern | 2-3h | 🔴 Kritisch |
| 2 | Token-Hashing | 1h | 🔴 Sicherheit |
| 3 | Tests schreiben | 3-4h | 🟠 Qualität |
| 4 | HACS-Manifest | 10min | ✅ erledigt |
| 5 | Übersetzung (i18n) | 2h | ✅ erledigt |
| 6 | Tote Konstanten/Services aufräumen | 30min | 🔵 Sauberkeit |
| 7 | `panel/` Ordner entfernen | 5min | ✅ erledigt |
| 8 | Token-Ablaufdatum | 1-2h | ✅ erledigt |
| 9 | Area-Filter | 2h | ✅ erledigt |
| 10 | Toast statt alert() | 1h | 🟢 UX |
| 11 | Responsive Design | 2h | 🟢 UX |
| 12 | Entity-Suche im Modal | 1h | ✅ erledigt |
| 13 | `/help`-Endpunkt | 15min | ✅ erledigt |
| 14 | Versionierung & Changelog | 30min | ✅ erledigt |
| 15 | Screenshots im README | 1h | 🟠 Sichtbarkeit |

---

## Zusammenfassung

**Das Plugin hat eine solide Basis.** Die größten Hürden für ein Community-Release sind:

1. **Sicherheit** – Admin-Endpoints müssen abgesichert werden
2. **Tests** – Ohne Tests akzeptieren viele Community-Reviewer kein Plugin
3. **Screenshots** – Für die HACS-Übersicht

HACS-Integration, i18n, Versionierung und Changelog sind bereits umgesetzt. Der Rest sind Verbesserungen, die über Zeit kommen können.
