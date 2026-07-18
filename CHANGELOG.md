# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier dokumentiert.
Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/),
die Versionierung an [SemVer](https://semver.org/lang/de/).

## [2.0.0] – 2026-07-18

### Geändert
- **Komplett neue Oberfläche:** GUI von CustomTkinter auf Flet umgestellt –
  GitHub-Look (Dark/Light), Stat-Karten, Tab-Pills, Nutzerliste mit Avataren
  und ⋯-Aktionsmenü, Verlauf als Timeline.
- Kernlogik in `gfc_core.py` und `gfc_controller.py` ausgelagert; CLI
  unverändert nutzbar.
- „Token anzeigen“ ist jetzt das Augen-Symbol im Token-Feld; das
  Rechtsklick-Menü wurde durch das ⋯-Menü pro Zeile ersetzt.
- Pause zwischen Folgen/Entfolgen-Requests von 1 s auf 2 s erhöht –
  konservativer gegenüber GitHubs Sekundär-Rate-Limits.

### Entfernt
- Abhängigkeiten `customtkinter` und `pillow` (ersetzt durch `flet`).

### Hinweise
- Einstellungen, Verlauf und Keyring-Token bleiben erhalten (gleiche Pfade).
- Python ≥ 3.10 erforderlich.

## [1.2.0] – 2026-07-18

### Hinzugefügt

- **Zweisprachige Oberfläche (Deutsch/Englisch):** folgt der Systemsprache,
  umstellbar über das neue Sprachmenü unten links (Auto/DE/EN) –
  gilt für GUI und CLI
- **PyPI-Workflow** (`publish-pypi.yml`, manuell auslösbar über
  GitHub Actions mit Trusted Publishing)
- Englischer Screenshot in der englischen README

### Behoben

- CI: mypy-Konfiguration an aktuelle mypy-Versionen angepasst
  (`python_version 3.9` entfernt, `keyring`-Fallback typisiert)

## [1.1.0] – 2026-07-18

### Hinzugefügt

- **Gezieltes Entfolgen:** Mehrfachauswahl in der Tabelle (Strg/Shift-Klick)
  und Button „Auswahl entfolgen“ – funktioniert in jeder Ansicht
- **Fans-Ansicht** (folgen dir, du folgst ihnen nicht) inkl. Sidebar-Statistik
- **Verlauf:** Jede Analyse wird lokal gespeichert (nur Nutzernamen);
  die Sidebar zeigt das Follower-Delta seit dem letzten Lauf, ein
  Mini-Diagramm den Follower-Trend, und der neue Tab „Verlauf“ listet,
  wer wann gefolgt/entfolgt ist
- **Whitelist:** Nutzer per Rechtsklick schützen (🛡) –
  „Alle Nicht-Folgenden“ überspringt sie
- **Rückgängig:** „↩ Rückgängig“ folgt dem zuletzt entfolgten Schwung wieder
- **Rechtsklick-Menü** (Profil öffnen, Folgen, Entfolgen, Schützen) und
  **Doppelklick** öffnet das GitHub-Profil
- **Suchfeld** zum Filtern der Tabelle; CSV-Export exportiert die gefilterte Ansicht
- **Profil-Panel:** Bei Auswahl eines einzelnen Nutzers erscheinen Avatar,
  Name, Bio und Follower-Zahlen unter der Tabelle
- **Token merken (opt-in):** Speicherung im System-Schlüsselbund (`keyring`)
- **API-Limit-Anzeige** in der Sidebar
- **Neue CLI** `GitHubFollowerCheckerCLI.py` mit `--token`/`GITHUB_TOKEN`,
  `--unfollow`, `--yes`, `--json`, `--quiet`, `--version` –
  ersetzt das alte Skript mit hartcodierten Zugangsdaten
- **Projekt-Infrastruktur:** `pyproject.toml`, GitHub-Actions-CI
  (ruff, mypy, pytest unter Xvfb), Release-Workflow mit
  PyInstaller-Binaries (Windows/Linux), Dependabot, Testsuite, App-Icon,
  englische README

### Geändert

- Fenstergeometrie wird gemerkt und nach dem Start erneut durchgesetzt
  (Workaround für Window-Manager, die das Fenster auf Mindestgröße stauchen)
- Status-Spalte in allen Ansichten sichtbar; „Du folgst“ aktualisiert sich
  sofort nach dem Entfolgen/Folgen

### Entfernt

- `GitHubUnfollowerToollong.py` (Username/Token standen als Konstanten im
  Code – ersetzt durch die neue CLI)

## [1.0.0] – 2026-07-14

- Neue CustomTkinter-Oberfläche mit sortierbarer Tabelle, drei Ansichten,
  CSV-Export, sicherer Token-Eingabe, Rate-Limit-Erkennung und
  Entfolgen-Funktion mit Sicherheitsabfrage
