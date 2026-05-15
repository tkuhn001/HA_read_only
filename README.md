# 🛡️ HA Read-Only API

[![Version](https://img.shields.io/badge/version-b0512.002-blue.svg)](https://github.com/tkuhn001/HA_read_only)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)

Eine leistungsstarke Home-Assistant-Integration zum Bereitstellen einer sicheren, **schreibgeschützten** HTTP-API für externe Systeme. Mit integriertem Admin-Panel zur Token-Verwaltung, Live-Statistiken und granularen Berechtigungen.

Anders als der HA-Langzeit-Token (der Vollzugriff gewährt) erlaubt dieses Plugin die **präzise Steuerung**, welche Entitäten, Domains oder Bereiche ein externes System sehen darf – und das **ohne jegliche Schreibrechte**.

---

## ✨ Highlights

- **🚀 Modernes Admin-Panel** – Professionelle Management-Oberfläche direkt in der HA-Seitenleiste (Glassmorphism Design).
- **📊 Live-Statistiken** – Behalte den Überblick über API-Aufrufe, Fehlerraten und den letzten Zugriff pro Token.
- **🛡️ Granulare Berechtigungen**:
  - Whitelisting von Domains (`light`, `sensor`, …)
  - **Areas** – nur Entitäten in ausgewählten HA-Bereichen
  - Einzelne Entitäten explizit erlauben
  - Glob-Muster/Wildcards (`light.kueche_*`, `sensor.*_temp`)
  - Dedizierte Block-Liste (Blacklist) mit höchster Priorität
  - **IP-Whitelist** pro Token (inkl. CIDR, z. B. `10.0.0.0/24`)
  - **Token-Ablaufdatum** optional
- **⏱️ Globales Rate-Limiting** – Schütze dein System durch konfigurierbare Limits pro IP und Token.
- **📑 Integrierte Anleitung** – Schnelleinstieg und API-Beispiele direkt im Dashboard.
- **🔌 Read-Only by Design** – Keine riskanten POST/PUT-Endpoints für Zustandsänderungen.

---

## 🖥️ Admin Dashboard

Die Integration fügt einen neuen Eintrag **"HA Read-Only"** zu deiner Home Assistant Seitenleiste hinzu. Das Dashboard ist in vier Bereiche unterteilt:

### 1. Tokens
Verwalte deine API-Zugänge. Erstelle neue Tokens, bearbeite bestehende Berechtigungen oder generiere Tokens neu, falls sie kompromittiert wurden.
- **Hinweis:** Neue Tokens werden aus Sicherheitsgründen nur einmalig angezeigt.

### 2. Nutzung (Statistics)
Echtzeit-Metriken über deine API:
- Gesamtzahl der Anfragen & Fehler.
- **Anfragen-Chart** (letzte 24 Stunden).
- **Request-Log** – die letzten 50 Anfragen mit Zeit, IP, Endpunkt und Status.
- Detaillierte Tabelle pro Token: Anfragen-Count, Fehlerrate, Letzter genutzter Endpunkt und Zeitstempel.

### 3. Einstellungen
Konfiguriere das globale Verhalten der API:
- **Max. Anfragen pro IP:** Schützt vor Brute-Force oder fehlerhaften Clients.
- **Max. Anfragen pro Token:** Kontrolliert die Last einzelner Integrationen.
- **Zeitfenster:** Definiere den Zeitraum (in Sekunden) für das Rate-Limiting.
- **Webhook (optional):** Benachrichtigung bei API-Anfragen oder Token-Erstellung.

### 4. Anleitung
Eine interaktive Hilfe direkt in Home Assistant mit Code-Beispielen für `cURL`, `JavaScript (fetch)` und `Python`.

---

## 📦 Installation

### Via HACS (Empfohlen)
1. HACS öffnen → **Integrationen**.
2. Oben rechts auf das Drei-Punkte-Menü → **Benutzerdefinierte Repositories**.
3. URL: `https://github.com/tkuhn001/HA_read_only` | Kategorie: **Integration**.
4. Suchen nach „HA Read-Only API“ und installieren.
5. Home Assistant neu starten.

### Manuell
1. Lade das Repository herunter.
2. Kopiere den Ordner `custom_components/ha_read_only/` in dein HA-`config/custom_components/` Verzeichnis.
3. Home Assistant neu starten.

---

## ⚙️ Konfiguration

Nach dem Neustart:
1. Gehe zu **Einstellungen → Geräte & Dienste → Integration hinzufügen**.
2. Suche nach **"HA Read-Only API"**.
3. Folge dem Setup-Wizard (dieser erstellt lediglich die Grund-Instanz).
4. Nutze fortan das **Dashboard in der Seitenleiste** für alle weiteren Konfigurationen.

---

## 📡 API-Referenz

Alle Anfragen müssen den folgenden HTTP-Header enthalten:
`X-HA-READONLY-TOKEN: <dein_token>`

### Endpunkte

| Methode | Endpunkt | Beschreibung |
|:--- |:--- |:--- |
| `GET` | `/api/ha_read_only/help` | Kurzübersicht aller Endpunkte (kein Token nötig). |
| `GET` | `/api/ha_read_only/states` | Gibt alle erlaubten Zustände zurück. |
| `GET` | `/api/ha_read_only/states/<entity_id>` | Gibt den Zustand einer spezifischen Entität zurück. |
| `GET` | `/api/ha_read_only/entities` | Listet alle erlaubten Entity-IDs auf. |

### Beispiel (cURL)
```bash
curl -H "X-HA-READONLY-TOKEN: abc123..." \
  http://homeassistant.local:8123/api/ha_read_only/states
```

### HTTP Status-Codes
- `200`: Erfolg.
- `401`: Token fehlt oder ist ungültig.
- `403`: Zugriff auf diese Entität verweigert.
- `429`: Rate-Limit überschritten.
- `500`: Interner Serverfehler.

---

## 🧠 Berechtigungs-Logik

Die Sichtbarkeit einer Entität wird nach folgendem Flow geprüft:

1. **Block-Liste (Blacklist):** Wenn die Entity-ID auf ein Muster in der Block-Liste passt → **Verweigert**.
2. **Whitelist-Check** (mindestens einer muss zutreffen, sofern Filter gesetzt):
   - Wenn **keine** Domains, **keine** Muster, **keine** Areas und **keine** einzelnen Entitäten definiert sind → **Erlaubt**.
   - Domain, Glob-Muster, HA-Area oder explizite Entity-ID passt → **Erlaubt**.
3. **Default:** Wenn nichts zutrifft → **Verweigert**.

**Token-Ebene (vor Entitätsfilter):**
- Abgelaufene Tokens werden abgewiesen (`401 Token expired`).
- IP-Whitelist: Nur konfigurierte IPs/CIDR-Bereiche dürfen den Token nutzen (`403`).

### Muster-Beispiele
- `light.*`: Alle Lichter.
- `*.temperature`: Alle Entitäten, die auf "temperature" enden.
- `sensor.kueche_*`: Alle Sensoren, die mit "kueche_" beginnen.

---

## 🔒 Sicherheitshinweise

- **Keine Standard-Auth:** Die API nutzt ausschließlich den Custom-Token. Halte diesen geheim.
- **Admin-Schutz:** Das Dashboard in der Seitenleiste ist durch die Home Assistant Benutzerverwaltung geschützt (nur Admins).
- **Reverse Proxy:** Bei Zugriff von außerhalb des Netzwerks wird dringend die Nutzung eines Reverse-Proxys (Nginx, Cloudflare Tunnel) empfohlen.
- **Regenerierung:** Nutze die "Neu generieren" Funktion im Dashboard regelmäßig für kritische Tokens.

---

## 🛠️ Entwicklung

Entwickelt mit Python 3.11+ und dem Home Assistant Integration Framework.

```bash
# Validierung der Python-Files
python -m py_compile custom_components/ha_read_only/*.py
```

## 📄 Lizenz

Dieses Projekt ist unter der **MIT-Lizenz** lizenziert. Siehe [LICENSE](LICENSE) für Details.
