# Design: GUI-Neuaufbau mit Flet im GitHub-Look

**Datum:** 2026-07-18
**Status:** Vom Nutzer genehmigt
**Anlass:** Die CustomTkinter-Oberfläche wirkt altbacken; der Gesamteindruck soll modern werden. Entscheidung: Framework-Wechsel zu Flet, volle Feature-Parität, Optik an github.com angelehnt.

## Ziele

- Moderne, an GitHub angelehnte Optik (Dark & Light).
- Volle Feature-Parität mit der bestehenden GUI – kein Funktionsverlust.
- Nutzerdaten (Settings, Verlauf, Keyring) überleben den Umbau unverändert.
- CLI und Kernlogik-Tests laufen mit minimalen Anpassungen weiter.

## Nicht-Ziele

- Keine neuen Features über den Bestand hinaus.
- Keine Änderung am CLI-Verhalten oder an der GitHub-API-Nutzung.
- Kein Web-Deployment; die App bleibt eine lokale Desktop-Anwendung.

## Architektur

### Neues Modul `gfc_core.py`

Aus `GitHubFollowerCheckerGUI.py` wird die UI-freie Kernlogik extrahiert:

- `GitHubClient` (inkl. Rate-Limit-Tracking), `RateLimitError`, `AuthError`
- Übersetzungen: `tr`, `_detect_language`, `_EN`-Tabelle
- Settings-/History-Helfer: `_load_settings`, `_save_settings`, `_load_history`,
  `_save_history`, `_normalize_history_entries`, Pfad-Konstanten
- `compute_follower_delta`, `ACTION_DELAY`, `BASE_URL`, `KEYRING_SERVICE`,
  `HISTORY_LIMIT`

Die CLI (`GitHubFollowerCheckerCLI.py`) importiert künftig aus `gfc_core`
statt aus dem GUI-Modul (reine Import-Änderung).

### Neue GUI `GitHubFollowerCheckerGUI.py` (Flet)

- Gleicher Dateiname wie bisher, damit Doppelklick-Start, READMEs und
  Release-Workflow gültig bleiben. Die CustomTkinter-Implementierung entfällt.
- Aufteilung in zwei Schichten:
  - **Controller-Klasse** (z. B. `AppController`): hält Zustand (Follower,
    Following, Rows, Whitelist, Undo-Liste, Sortierung, Filter), berechnet
    Kandidaten, führt Analyse/Folgen/Entfolgen in Hintergrund-Threads aus und
    meldet Änderungen über Callbacks. Keine Flet-Abhängigkeit in der Logik –
    dadurch ohne Fenster testbar.
  - **View-Schicht**: baut die Flet-Controls, übersetzt Controller-Events in
    UI-Updates (`page.update()`), zeigt Dialoge/Snackbars.
- `_ensure_dependencies()` bleibt (installiert fehlende Pakete beim
  Doppelklick-Start), angepasst auf `flet`, `requests`, `keyring`.

### Abhängigkeiten

- Neu: `flet` (Version gepinnt, z. B. `flet>=0.28,<0.29` – exakte Pins bei
  Implementierung anhand der aktuellen Release-Lage festlegen).
- Entfällt: `customtkinter`, `pillow` (Avatare lädt Flet direkt per URL
  `https://github.com/{user}.png?size=96`, kein PIL nötig).
- Bleibt: `requests`, `keyring` (optional wie bisher).

### Datenkompatibilität

- `~/.config/github-follower-checker/settings.json` und `history.json`
  behalten Pfad und Format (Zoom, Theme, Sprache, Fenstergeometrie,
  Whitelist, Snapshots).
- Keyring-Service-Name `github-follower-checker` bleibt – gespeicherte Tokens
  funktionieren weiter.

## UI-Konzept (GitHub-Look)

### Farbwelt

| Rolle | Dark | Light |
|---|---|---|
| Hintergrund | `#0d1117` | `#ffffff` |
| Karten/Flächen | `#161b22` | `#f6f8fa` |
| Border | `#30363d` | `#d0d7de` |
| Text primär | `#e6edf3` | `#1f2328` |
| Text sekundär | `#8b949e` | `#59636e` |
| Akzent Grün (Folgen/Fans) | `#238636` / `#3fb950` | `#1a7f37` |
| Akzent Rot (Entfolgen) | `#da3633` / `#f85149` | `#cf222e` |
| Akzent Blau (Links/Auswahl) | `#58a6ff` | `#0969da` |

Dark/Light/System wie bisher wählbar; System folgt der Plattform-Einstellung.

### Layout

- **Sidebar links** (Struktur bleibt vertraut, wird luftiger):
  - Titel + Untertitel
  - Zugangsdaten-Karte: Username, Token (maskiert, einblendbar),
    „Token merken (Schlüsselbund)", Button „Analyse starten", Fortschritt,
    Statuszeile
  - **2×2 Stat-Karten** mit großen Zahlen: Follower, Following, Fans (grün),
    Folgen nicht zurück (rot)
  - Delta-Karte „Seit letzter Analyse" + Sparkline (Flet-Canvas, ab zwei
    Analysen)
  - Fußzeile: Theme-, Zoom-, Sprach-Auswahl, API-Limit, Version
- **Hauptbereich**:
  - Tab-Pills: Folgen nicht zurück / Fans / Follower / Following / Verlauf
  - Filterfeld (Sofortsuche, Esc leert) und CSV-Export rechts oben
  - **Nutzerliste** statt ttk-Treeview: scrollbare Zeilen mit Avatar,
    Nutzername (🛡-Schild bei Whitelist), Status-Pills „folgt dir" /
    „du folgst", Status-Text (z. B. „✓ Entfolgt"), Aktions-Menü (⋯) pro Zeile
  - Mehrfachauswahl per Checkbox; Kopfzeile mit Sortier-Indikatoren
    (Spalten wie bisher: Username, Folgt dir, Du folgst, Status)
  - **Verlauf-Tab** als Timeline: grüne `+`- und rote `−`-Einträge mit
    Zeitstempel, Sortierung Neuestes zuerst
  - Profil-Detailkarte bei Einzelauswahl (Avatar, Name, Follower/Following,
    „dabei seit", Bio), Daten via `GitHubClient.get_user` mit Cache und
    350-ms-Debounce wie bisher
  - Untere Aktionsleiste: „Auswahl entfolgen", „Alle Nicht-Folgenden (n)"
    (rot, gefüllt), „↩ Rückgängig (n)" nach einem Entfolgen-Lauf, Tipp-Text
    (Wortlaut angepasst: verweist auf Checkboxen und ⋯-Menü statt auf
    Rechtsklick; DE/EN-Texte entsprechend ergänzen)
- **Interaktion**: Doppelklick/Klick auf Avatar öffnet Profil im Browser;
  das bisherige Rechtsklick-Menü wird durch das ⋯-Zeilenmenü plus
  Auswahl-Aktionen ersetzt (Folgen, Entfolgen, Schützen, Schutz aufheben,
  Profile öffnen – Begrenzung auf 5 Browser-Tabs bleibt).

### Dialoge & Rückmeldungen

- Bestätigungen (Entfolgen einzeln/Auswahl/alle, inkl. Whitelist-Hinweis und
  „kann nicht rückgängig gemacht werden") als Flet-AlertDialog mit rotem
  Bestätigen-Button.
- Fehler (Auth, Netzwerk, HTTP), Rate-Limit-Warnung mit Reset-Uhrzeit und
  Statusmeldungen wie bisher; kurze Bestätigungen als Snackbar.

## Feature-Parität (Checkliste)

Analyse mit Fortschritt und Seitenzähler · Entfolgen alle/Auswahl mit
`ACTION_DELAY` 2 s · Folgen · Rückgängig · 🛡-Whitelist (persistiert) ·
Verlauf/Delta mit `HISTORY_LIMIT` 50 · Sparkline · CSV-Export (gleiche
Spalten, lokalisierte Header) · Filter · Keyring-Merken · DE/EN/Auto ·
Dark/Light/System · Zoomstufen 100–200 % (skalierte Schriftgrößen/Abstände)
· Fenstergeometrie speichern · API-Limit-Anzeige · Rate-Limit-/Auth-/
Netzwerk-Fehlerbehandlung · Token nur im Arbeitsspeicher (nie loggen/
speichern außer Keyring-Opt-in).

## Threading & Fehlerbehandlung

- API-Aufrufe (Analyse, Folgen/Entfolgen-Schleifen, Profil-Fetch) laufen in
  Hintergrund-Threads; UI-Updates über die Flet-Page aus dem Thread
  (Flet-Äquivalent zu `self.after(0, …)`).
- Busy-Zustand deaktiviert Analyse-/Export-/Aktions-Buttons wie bisher.
- Rate-Limit bricht Schleifen ab und markiert Rest als „Übersprungen
  (Rate-Limit)"; Semantik unverändert aus der Alt-GUI übernehmen.

## Tests

- Kern-Tests (GitHubClient, Delta, History, i18n) und CLI-Tests: nur
  Import-/Fixture-Anpassung auf `gfc_core`.
- GUI-Tests: gegen die Controller-Klasse mit FakeClient (bestehendes
  Muster), ohne echtes Fenster – Analyse-Durchlauf, Kandidatenberechnung,
  Whitelist-Verhalten, Undo, Statusmeldungen.
- Screenshot-Verifikation: neues Vorgehen für Flet erarbeiten (das
  `import -window`-Rezept gilt für Tk und muss ersetzt werden).

## Begleitarbeiten

- `requirements.txt`, `pyproject.toml` (Abhängigkeiten, Version).
- README.md / README.en.md: neue Screenshots, Installationshinweise.
- CI-Workflow: Tests ohne Tk/Xvfb-Sonderfälle; Release-Packaging auf
  `flet pack` umstellen.
- CHANGELOG-Eintrag; Versionssprung auf 2.0.0 (Breaking: neues UI-Framework).

## Risiken

- **Flet-API-Stabilität**: jünger als Qt/Tk; Version pinnen, Auto-Installer
  installiert die gepinnte Version.
- **Linux-Desktop-Runtime**: Flet bringt eigene Runtime-Anforderungen mit
  (z. B. libmpv auf manchen Distributionen); bei Implementierung prüfen und
  im README dokumentieren.
- **Zoom**: Flet hat kein globales Widget-Scaling wie CTk; Umsetzung über
  eigene Größen-Tokens, die mit dem Zoomfaktor multipliziert werden.
