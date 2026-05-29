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

### 4.1 Tests schreiben ✅ (umgesetzt v0.4.1)
- [x] Test-Infrastruktur (pytest, conftest.py, fixtures)
- [x] Unit-Tests für alle Helper-Funktionen (_hash, _verify, _mask, _rate_limit, _ip_matches, etc.)
- [x] Integration-Tests für öffentliche API und Admin-API
- [x] Storage- und Service-Tests
- [x] CI via GitHub Actions

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

### 4.2 Type Hints vervollständigen ✅ (umgesetzt v0.4.1)
- [x] API-Views in `api.py` mit `web.Request` / `web.Response`
- [x] `config_flow.py` – alle Methoden typisiert
- [x] `__init__.py` – alle Funktionen und Methoden typisiert

### 4.3 Tote Konstanten aufräumen ✅ (umgesetzt v0.4.1)
- [x] `CONF_ALLOWED_AREAS`, `CONF_ALLOWED_ENTITIES` – Features nutzen diese Konzepte (Keys: `areas`, `allowed_entities`)
- [x] `CONF_BLOCKED_ENTITIES`, `CONF_PROVIDE_ENTITIES_LIST`, `CONF_RETURN_ONLY_IDS` – entfernt (ungennutzte Konstanten aus `const.py` gelöscht)

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

## 🔴 Priorität 6: Admin-Sicherheit

### 6.1 Admin-Endpunkte authentifizieren
Aktuell haben **alle 16 Admin-Views** `requires_auth = False`. Obwohl sie nur im HA-Iframe eingebettet sind, sind die Endpunkte ohne HA-Authentifizierung erreichbar, wenn die URL bekannt ist. Ein Gerät im LAN (z. B. IoT) könnte Tokens erstellen/löschen/ändern, Konfiguration auslesen und die Webhook-URL manipulieren.

**Abwägung:** Für ein reines Heimnetzwerk vertretbar, für den Einsatz hinter einem Reverse Proxy oder aus dem Internet ein kritisches Sicherheitsrisiko.

**Lösung:** `requires_auth = True` setzen und sicherstellen, dass der Iframe den HA-Auth-Token korrekt mitsendet.

### 6.2 Rate-Limiting für Admin-Endpunkte
Admin-Endpunkte haben keinerlei Rate-Limiting. Ein Skript im LAN könnte CRUD-Operationen ohne Drosselung ausführen.

### 6.3 Validierung von Konfigurations-Updates
`AdminApiConfigView.put()` akzeptiert jedes beliebige JSON-Payload ohne Validierung. Werte wie `webhook_url` könnten auf eine bösartige URL gesetzt werden.

### 6.4 Input-Validierung für Token-CRUD
- Token-Felder werden nicht auf Länge, Typ oder Format validiert
- `int()`-Cast ohne Fehlerbehandlung bei `rate_limit_max_requests`
- `allowed_ips` wird nicht auf Gültigkeit geprüft (erst bei Nutzung)
- Token-Update/Löschen/Regenerieren liefert still `{"success": True}` auch bei nicht-existenter ID

### 6.5 Schutz vor Brute-Force
Wiederholte Fehlversuche (401) werden nicht speziell behandelt. Kein exponentielles Backoff oder Account-Lockout bei häufigen Fehlern.

---

## 🟠 Priorität 7: Code-Qualität & Bugs

### 7.1 Toter Code nach Return-Statement 🐛
In `AdminApiStatsCleanupView.post()` (`api.py` ~Zeile 776-780) befinden sich **2 identische Zeilen nach einem Return-Statement**, die nie ausgeführt werden können. Vermutlich Copy-Paste-Fehler.

### 7.2 Massives Frontend-Code-Duplikat
`loadStats()` und `loadStatsForToken()` in `admin.html` sind nahezu identisch (~40 Zeilen, unterscheiden sich nur durch `?token_id=`). Refactoring in eine gemeinsame Funktion nötig.

### 7.3 Leere OptionsFlow
`HaReadOnlyOptionsFlow` zeigt ein Formular mit **null Feldern**. Es gibt keine Möglichkeit, die Integration über die Standard-HA-Oberfläche zu konfigurieren.

### 7.4 Stub `async_update_entry`
Die Funktion besteht nur aus `pass`. Wenn Config-Entry-Optionen gespeichert würden, würden sie nie angewendet.

### 7.5 Unused Constants in `const.py`
**8 Konstanten** sind definiert, aber nirgends in Verwendung – die tatsächlichen Data-Keys (`"domains"`, `"areas"`, `"patterns"` etc.) werden als Literale verwendet:
- `CONF_TOKEN_NAME`, `CONF_ALLOWED_DOMAINS`, `CONF_ALLOWED_AREAS`, `CONF_ALLOWED_ENTITIES`, `CONF_ALLOWED_PATTERNS`, `CONF_BLOCKED_PATTERNS`, `CONF_INCLUDE_ATTRIBUTES`, `CONF_STATS_MAX_REQUESTS`

### 7.6 Ineffizientes `list.insert(0)` im Usage-Log
`usage_log.insert(0, log_entry)` ist O(n) pro Operation. Besser `append` + Reverse beim Lesen.

### 7.7 Inline-JavaScript ohne Strict Mode
Das komplette `<script>`-Block in `admin.html` läuft im globalen Scope ohne `"use strict"`. Variablen wie `tokens`, `curId` sind global, was zu Kollisionen mit anderen HA-Panels führen kann.

---


## 🟡 Priorität 8: Performance

### 8.1 `_is_entity_allowed()` in O(n*m)-Schleife ✅ (umgesetzt v0.4.1)
- [x] Registry-Lookup einmalig vorab via `_build_area_map(hass)`
- [x] Area-Zuordnung per Dict-Lookup statt 1000 Registry-Zugriffen
- [x] Nur gebaut wenn Token Areas nutzt – kein Overhead für Tokens ohne Area-Filter
- [x] `_get_entity_area()` entfernt (ersatzlos gestrichen)

### 8.2 `_cleanup_stats()` bei jedem Speichern
`async_save()` wird bei jedem API-Request aufgerufen und iteriert das gesamte Usage-Log. Sollte nur bei Bedarf oder zeitgesteuert laufen.

### 8.3 Chart-Berechnungen iterieren 3x das Usage-Log
`_compute_hourly_chart()`, `_compute_hourly_chart_by_color()` und `_compute_daily_usage()` werden nacheinander aufgerufen, jede durchläuft das gesamte Log. Ein Single-Pass wäre effizienter.

### 8.4 Keine `aiohttp.ClientSession`-Wiederverwendung
`_fire_webhook()` erzeugt bei jedem Webhook eine neue HTTP-Session. Sollte wiederverwendet werden (Connection-Pooling).

### 8.5 Redundante API-Calls im Frontend
`saveCfg()` → PUT Config → `loadTokens()`. Settings-Tab → `loadCfg()` → bedingt `loadTokens()`. Diese Roundtrips addieren Latenz.

### 8.6 Hard Limit von 150 bei Entity-Suche
Die Admin-Entity-Suche schneidet bei 150 Ergebnissen ab, ohne Paginierung oder "mehr Ergebnisse"-Hinweis.

---

## 🔵 Priorität 9: Fehlende HA-Standard-Features

### 9.1 Diagnostics-Endpunkt
Moderne HA-Integrationen implementieren einen `/api/diagnostics`-Endpunkt fürs Debugging. Fehlt komplett.

### 9.2 `async_reload_entry`
Es gibt keine Möglichkeit, die Integration ohne HA-Neustart neu zu laden. Änderungen an Config-Entry-Optionen würden erst nach Restart wirken.

### 9.3 Kein System-Health-Support
Kein `system_health`-Provider → Status nicht im HA-System-Dashboard sichtbar.

### 9.4 Token-Ablauf-Benachrichtigungen
Keine Benachrichtigung (Persistent Notification, Sensor) bei bald ablaufenden Tokens.

### 9.5 Kein Audit-Trail
Admin-Aktionen (Token-Erstellung, -Löschung, Config-Änderungen) werden nicht geloggt. Keine Rückverfolgbarkeit.

### 9.6 Token-Konfiguration exportieren/importieren
Keine Möglichkeit, Token-Konfigurationen zwischen HA-Instanzen zu sichern oder zu übertragen.

---

## 🟢 Priorität 10: UX & Dokumentation

### 10.1 Versionsnummer inkonsistent
Version weicht ab zwischen `const.py` (0.4.1), `admin.html`-Footer (0.3.9) und `CHANGELOG.md` (endet bei 0.3.9).

### 10.2 Changelog-Lücken
Versionen 0.3.6, 0.3.7, 0.3.8, 0.4.0 und 0.4.1 fehlen im Changelog.

### 10.3 Admin-API nicht dokumentiert
Der `/help`-Endpoint listet nur die öffentliche API. Die 15+ Admin-Endpunkte sind weder in der API-Hilfe noch im README dokumentiert.

### 10.4 Fehlende Docstrings
Viele kritische Funktionen in `api.py` haben keine Docstrings, insbesondere: `_is_entity_allowed()`, `_rate_limit()`, `_hash_token()`, `_verify_token()`, `_get_client_ip()`.

### 10.5 Keine Contribution-Guide
Kein `CONTRIBUTING.md`, keine Entwickler-Setup-Anleitung, keine Test-Anleitung.

### 10.6 CDN-Abhängigkeit nicht dokumentiert
`admin.html` lädt Material Design Icons von `cdn.jsdelivr.net`. Bei CDN-Ausfall brechen alle Icons weg. Kein Fallback.

### 10.7 Log-Eintrag löschen ohne Bestätigung
Im Gegensatz zum Token-Löschen gibt es bei Log-Einträgen **keinen Confirm-Dialog**. Ein Klick löscht sofort.

### 10.8 Einstellungen in `localStorage`
Benutzereinstellungen (Log-Anzeige) werden im Browser-LocalStorage gespeichert → pro Browser, nicht geräteübergreifend.

### 10.7 Field-Keys inkonsistent
`const.py` definiert `CONF_ALLOWED_DOMAINS = "allowed_domains"`, aber der tatsächliche Data-Key ist `"domains"`. Gleiches für Areas, Patterns etc.

### 10.8 Silent Success bei nicht-existenter Token-ID
PUT/DELETE/Regenerieren liefern `{"success": True}` auch wenn die Token-ID nicht existiert. Sollte 404 mit Fehlermeldung zurückgeben.

### 10.9 Keine JSON-Body-Validierung
`await request.json()` in mehreren Views ohne try/except. Bei kaputtem JSON → 500 ohne Fehlermeldung.

### 10.10 Keine Längen-/Wertebereichs-Validierung
Token-Felder, Patterns, IP-Listen und Retention-Werte akzeptieren unbegrenzte Eingaben. Ein Milliarden-Zeichen-Pattern könnte Speicherprobleme verursachen.

### 10.11 `ValueError` still in Log-Deletion
`int(index)` wird bei ungültigem Index mit `except ValueError: pass` geschluckt. Der Aufrufer bekommt trotzdem `{"success": True}`.

---

## 📋 Empfohlene Reihenfolge

| # | Aufgabe | Aufwand | Impact |
|--|---------|---------|--------|
| 1 | Admin-Auth absichern | 2-3h | 🔴 Kritisch |
| 2 | Token-Hashing | 1h | ✅ erledigt |
| 3 | CORS-Header setzen (6.2) | 30min | 🟠 Sicherheit |
| 4 | Toter Code in StatsCleanupView entfernen (7.1) | 5min | 🐛 Bug |
| 5 | Input-Validierung für Token-CRUD (6.5) | 2h | 🟠 Sicherheit |
| 6 | Config-Update validieren (6.4) | 1h | 🟠 Sicherheit |
| 7 | Textbaustein-OptionsFlow füllen (7.3) | 1h | 🔵 Qualität |
| 8 | Frontend-Duplikat refactoren (7.2) | 1h | 🔵 Wartbarkeit |
| 9 | Performance: cleanup nicht bei jedem Request (8.2) | 1h | 🟡 Performance |
| 10 | Performance: Single-Pass für Charts (8.3) | 1h | 🟡 Performance |
| 11 | Unused Constants aufräumen (7.5) | 15min | 🔵 Sauberkeit |
| 12 | async_reload_entry implementieren (9.2) | 30min | 🟢 HA-Konformität |
| 13 | Diagnostics-Endpunkt (9.1) | 30min | 🟢 HA-Konformität |
| 14 | Audit-Trail für Admin-Aktionen (9.6) | 2h | 🔵 Sicherheit |
| 15 | Token-Ablauf-Benachrichtigungen (9.5) | 1h | 🟢 UX |
| 16 | Token-Ablauf-Benachrichtigungen (9.4) | 1h | 🟢 UX |
| 17 | Silent-Success-Bugs beheben (10.8) | 1h | 🐛 Bug |
| 18 | Versionsnummern vereinheitlichen (10.1) | 15min | 📋 Doku |
| 19 | Changelog befüllen (10.2) | 15min | 📋 Doku |
| 20 | JSON-Body-Validierung (10.9) | 1h | 🟠 Sicherheit |
| 21 | Responsive Design (5.2) | 2h | 🟢 UX |
| 22 | Field-Keys konsolidieren (10.7) | 30min | 🔵 Sauberkeit |
| 23 | CDN-Fallback für Icons (10.6) | 30min | 🟢 Zuverlässigkeit |

---

## Zusammenfassung

**Das Plugin hat eine solide Basis.** Die größten Hürden für ein Community-Release sind:

1. **Admin-Auth** – Alle Admin-Endpunkte haben `requires_auth = False` und sind ohne Authentifizierung erreichbar.
2. **Input-Validierung** – Token-CRUD, Config-Updates und IP-Listen werden nicht validiert.
3. **Toter Code** – Copy-Paste-Fehler mit Code nach Return-Statement in `AdminApiStatsCleanupView`.
4. **Performance** – Log-Cleanup bei jedem Request, O(n*m) Entity-Filter, 3x-Usage-Log-Iteration für Charts.

Sicherheit (Token-Hashing, Admin-Auth), HACS-Integration, i18n, Versionierung, Tests, Changelog, Type Hints und Screenshots sind bereits umgesetzt. Der Rest sind Verbesserungen, die über Zeit kommen können.
