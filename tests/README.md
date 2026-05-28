# Tests für HA Read-Only API

## Voraussetzungen

```
pip install pytest pytest-asyncio aiohttp voluptuous
```

## Ausführung

| Befehl | Beschreibung |
|---|---|
| `python -m pytest tests/` | Alle Tests (verbose, default) |
| `python -m pytest tests/ -q` | Nur Punkte (kurz) |
| `python -m pytest tests/ -x` | Stoppen beim ersten Fehler |
| `python -m pytest tests/ -k "entity_allowed"` | Nur Tests deren Name "entity_allowed" enthält |
| `python -m pytest tests/ --tb=long` | Fehler mit vollständigem Traceback |
| `python -m pytest tests/test_ip_filter.py` | Nur eine bestimmte Datei |
| `python -m pytest tests/ -v --collect-only` | Alle Tests auflisten ohne sie auszuführen |
| `python -m pytest tests/ --co` | Nur fehlgeschlagene Tests anzeigen |
| `python -m pytest tests/ --junitxml=report.xml` | Ergebnis als XML exportieren |
| `python -m pytest tests/ -n auto` | Parallel ausführen (braucht pytest-xdist) |
