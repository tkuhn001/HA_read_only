# Changelog

## 0.4.2 – 30. Mai 2026
- Performance: Area-Lookup in `_is_entity_allowed` von O(n\*m) auf O(1) optimiert
- Versionsnummern vereinheitlicht: `const.py` ist Single Source of Truth
- `admin.html`: hartcodierte Versionen durch `{VERSION}`-Platzhalter ersetzt (Backend ersetzt beim Ausliefern)
- Startup-Validierung: Warnt bei Abweichung zwischen `const.py` und `manifest.json`
- `bump_version.ps1`: Script für konsistentes Versions-Bumping

## 0.4.1 – 28. Mai 2026
- Umfassende Testsuite mit 227 Unit- und Integrationstests
- Interactive Token-Test-Feature im Admin-Panel
- Type Hints für `config_flow.py` und `__init__.py` hinzugefügt
- Tote Konstanten (`CONF_BLOCKED_ENTITIES`, `CONF_PROVIDE_ENTITIES_LIST`, `CONF_RETURN_ONLY_IDS`) entfernt
- Icons auf 256×256 PNG verkleinert für HACS-Kompatibilität
- README aktualisiert

## 0.4.0 – 25. Mai 2026
- Token-Hashing für sicheres Speichern der Token
- Per-Token Rate Limiting mit konfigurierbaren Zeitfenstern
- Token-Karten-Redesign: kompaktes Layout mit reichhaltiger Datenanzeige
- Services: Token-Erstellung, -Abruf und -Widerruf über HA-Services
- Screenshots in README hinzugefügt

## 0.3.9 – 20. Mai 2026
- Zugänge können individuelle Farben zugewiesen werden (Color-Picker im Create/Edit-Modal)
- Token-Karten zeigen farbigen linken Rahmen und Farb-Badge beim Namen
- Pie Chart verwendet zugewiesene Token-Farben (Fallback auf Standard-Palette)
- Balkendiagramm segmentiert nach Token-Farben (Anteile pro Farbe pro Stunde)
- Tabelle "Letzte Anfragen" mit sortierbaren Spalten (Klick auf Header)
- "Mehr anzeigen"-Button für inkrementelles Nachladen der Log-Einträge
- Neue Einstellung für Standard-Zeilenanzahl der Log-Tabelle
- Chart-Icons farbig hervorgehoben

## 0.3.8 – 18. Mai 2026
- Statistikspeicherung mit globalen Limits und Token-Limits
- Pie-Chart für Token-Verteilungsanalyse
- Lade-Animationen (Spinner, Skeleton Loader) für besseres UX
- Dynamisches HTML-Serving aus Python-Backend
- Umfassendes UI-Overhaul: modale Dialoge, verbesserte Navigation

## 0.3.7 – 17. Mai 2026
- Admin-API-Endpoints mit HA-Authentifizierung geschützt (Security Fix)
- Light Mode Support hinzugefügt
- Toasts und Confirm-Dialogs für bessere Benutzerführung
- Modal-UX verbessert (Datepicker, Area-Registry-Crash gefixt)
- HACS-Kompatibilität optimiert (manifest.json, hacs.json)
- README mit neuen Features und Sicherheitsinfos aktualisiert

## 0.3.6 – 16. Mai 2026
- Token-Farben im Dashboard (Vorbereitung für 0.3.9)
- Sortierbare Log-Tabelle mit Spalten-Header-Klick
- Inkrementelles Nachladen der Log-Einträge
- UI-Verbesserungen: Dynamisches HTML, Wording-Überarbeitung
- Loading-Animationen eingeführt

## 0.3.5 – 15. Mai 2026
- Versionsnummer aus Python-Headern entfernt
- HACS-Branding (brand/ Ordner)
- Chart-Optimierung: Achsenbeschriftung, Tooltip, breitere Darstellung
- `/help`-Endpoint trackt jetzt Token mit

## 0.3.4 – 15. Mai 2026
- Icon, Version 0.3.3, i18n-Fix

## 0.3.3 – 15. Mai 2026
- Integration-Icon (icon.png) hinzugefügt
- JSON-Syntaxfehler in translations behoben

## 0.3.2 – 15. Mai 2026
- HACS-Kompatibilität (hacs.json, translations)
- CHANGELOG.md hinzugefügt
- Lizenz-Header und Copyright-Footer

## 0.3.1 – 15. Mai 2026
- MIT-Lizenz und Haftungsausschluss hinzugefügt
- Copyright-Footer im Admin-Panel
- Lizenz-Header in allen Python-Dateien

## 0.3.0 – Mai 2026
- Token-Ablaufdatum (optional)
- Area-basiertes Filtering
- IP-Whitelist pro Token (Einzel-IP + CIDR)
- Webhook-Benachrichtigungen (API-Anfragen + Token-Erstellung)
- Entity-Suche im Dashboard mit Chips
- Token-Nutzungslog mit SVG-Balkendiagramm (24h)
- Persistenter Rate-Limit-Cache
- API-Hilfe-Endpunkt (`/help`)
- Admin-Panel mit Tabs: Tokens, Nutzung, Einstellungen, Anleitung, Lizenz

## 0.2.0 – Mai 2026
- Neues Admin-Dashboard (Glassmorphism Design)
- Rate-Limiting (pro IP und Token)
- Usage-Tracking mit Statistiken
- Granulare Berechtigungen (Domains, Areas, Entitäten, Patterns, Blocklisten)
- Config-Flow mit 6 Schritten
- Sidebar-Panel-Integration

## 0.1.0 – Mai 2026
- Erste Beta-Version
- Read-Only API (`/states`, `/entities`)
- Token-basierte Authentifizierung
- Einfache Berechtigungsfilter (Domains, Entitäten, Patterns)
