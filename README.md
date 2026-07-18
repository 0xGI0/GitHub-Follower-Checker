<p align="center"><img src="docs/icon.png" width="96" alt="App-Icon"></p>

# 🐙 GitHub Follower Checker

**Deutsch** · [English](README.en.md)

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![CI](https://github.com/0xGI0/GitHub-Follower-Checker/actions/workflows/ci.yml/badge.svg)](https://github.com/0xGI0/GitHub-Follower-Checker/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/0xGI0/GitHub-Follower-Checker?style=flat)](https://github.com/0xGI0/GitHub-Follower-Checker/stargazers)

Desktop-Tool zum Analysieren deiner **GitHub-Follower/Following-Beziehungen** – mit moderner
CustomTkinter-Oberfläche, sortierbarer Ergebnistabelle, CSV-Export und optionalem
**Entfolgen**: alle Nutzer, die dir nicht zurückfolgen, auf einen Klick – oder
gezielt einzelne ausgewählte Nutzer.

---

## 📸 Screenshot

![GitHub Follower Checker GUI](docs/screenshot.png)

---

## ✨ Features

* **Moderne GUI** (CustomTkinter, Dark Mode als Standard, Light Mode umschaltbar)
* **HiDPI-tauglich**: Display-Skalierung wird automatisch erkannt,
  Zoom (100–200 %) per Dropdown einstellbar – Zoom und Theme werden lokal
  gespeichert (`~/.config/github-follower-checker/`, keine Zugangsdaten)
* **Sortierbare Ergebnistabelle** mit fünf Ansichten:
  + Folgen nicht zurück
  + Fans (folgen dir, du folgst ihnen nicht)
  + Follower
  + Following
  + Verlauf (wer dir wann gefolgt/entfolgt ist)
  + Klick auf eine Spaltenüberschrift sortiert auf-/absteigend
* **Suchfeld** zum Filtern der Tabelle nach Nutzernamen
* **CSV-Export** der aktuellen (gefilterten) Ansicht
* **Profil-Panel**: Bei Auswahl eines Nutzers erscheinen Avatar, Name,
  Bio und Follower-Zahlen direkt unter der Tabelle
* **Sichere Token-Eingabe**
  + Maskiertes Eingabefeld (einblendbar per Checkbox)
  + Token wird standardmäßig **nicht gespeichert und nicht geloggt** –
    es bleibt nur im Arbeitsspeicher
  + Optional: **„Token merken"** legt das Token verschlüsselt im
    **System-Schlüsselbund** ab (`keyring`), niemals in einer Datei
* **Reaktionsfähige Oberfläche**
  + Alle API-Abfragen laufen in einem Hintergrund-Thread
  + Ladeindikator und Live-Status während der Analyse
  + Fortschrittsbalken beim Entfolgen
* **Verständliche Fehlermeldungen**
  + GitHub-Rate-Limit wird erkannt und mit Uhrzeit der Freigabe angezeigt
  + Verbleibendes API-Kontingent wird in der Sidebar angezeigt
  + Klare Hinweise bei ungültigem Token oder Netzwerkproblemen
* **Entfolgen mit Sicherheitsabfrage** und Statusanzeige pro Nutzer
  + **„Alle Nicht-Folgenden"**: entfolgt allen Nutzern, die dir nicht zurückfolgen
  + **„Auswahl entfolgen"**: entfolgt nur den in der Tabelle markierten Nutzern –
    in jeder Ansicht, Mehrfachauswahl per Strg-/Shift-Klick
  + **„↩ Rückgängig"**: folgt den gerade entfolgten Nutzern mit einem Klick wieder
* **Whitelist**: Nutzer per Rechtsklick **schützen** (🛡) –
  „Alle Nicht-Folgenden" überspringt sie dann
* **Rechtsklick-Menü & Doppelklick**: Profil im Browser öffnen,
  folgen (z. B. Fans zurückfolgen), entfolgen oder schützen
* **Verlauf**: Die Sidebar zeigt nach jeder Analyse, wer dir seit dem
  letzten Lauf **neu folgt oder entfolgt ist**, plus ein Mini-Diagramm des
  Follower-Trends; der Tab „Verlauf" listet alle Ereignisse
  (lokal gespeichert, nur Nutzernamen)
* **Fenstergröße wird gemerkt** – inklusive Workaround für Window-Manager,
  die das Fenster beim Start auf die Mindestgröße stauchen (HiDPI)

---

## 🧩 Setup

**Am einfachsten:** Fertige Programme (ohne Python) gibt es auf der
[Releases-Seite](https://github.com/0xGI0/GitHub-Follower-Checker/releases) –
einfach herunterladen und starten.

**Aus dem Quellcode** (Python 3.9+):

```bash
git clone https://github.com/0xGI0/GitHub-Follower-Checker.git
cd GitHub-Follower-Checker
pip install -r requirements.txt
```

Es wird ausschließlich die offizielle **GitHub REST API v3** verwendet.

---

## 🔑 GitHub Personal Access Token (PAT) erstellen

1. Öffne auf GitHub:
   `Settings` → `Developer settings` → `Personal access tokens` → `Tokens (classic)`
2. Klicke **„Generate new token (classic)"**
3. Vergib einen Namen, z. B. `GitHub Follower Checker`
4. Wähle mindestens diesen Scope:
   * **`user:follow`** (für Analyse und Entfolgen)
5. Token generieren und **sicher speichern** (wird nur einmal vollständig angezeigt)

---

## ▶️ Ausführung

### 🖥️ GUI-Version (empfohlen)

```bash
python GitHubFollowerCheckerGUI.py
```

Fehlende Pakete installiert das Skript beim ersten Start automatisch –
dadurch funktioniert auch der Start per **Doppelklick** (Windows, Mac, Linux).

**So funktioniert's:**

1. GitHub-Username eintragen
2. Personal Access Token einfügen (maskiert, wird nirgends gespeichert)
3. **„Analyse starten"** klicken – der Fortschritt wird live angezeigt
4. Ergebnisse in der Tabelle prüfen, bei Bedarf sortieren, filtern oder als
   **CSV exportieren** – Rechtsklick auf eine Zeile öffnet das Aktionsmenü,
   Doppelklick öffnet das GitHub-Profil im Browser
5. Optional entfolgen – zwei Wege, jeweils mit Bestätigungsdialog und Status pro Nutzer:
   * **„Alle Nicht-Folgenden"** entfolgt allen Nutzern aus der Ansicht
     „Folgen nicht zurück" (🛡-geschützte Nutzer werden übersprungen)
   * **„Auswahl entfolgen"** entfolgt nur den markierten Nutzern – einfach in
     einer beliebigen Ansicht Zeilen anklicken (Strg-/Shift-Klick für mehrere)
   * Versehentlich entfolgt? **„↩ Rückgängig"** folgt dem letzten Schwung wieder

### 💻 CLI-Version

Für Terminal und Skripte – das Token kommt per `--token`, aus der
Umgebungsvariable `GITHUB_TOKEN` oder wird sicher abgefragt (nie im Code):

```bash
python GitHubFollowerCheckerCLI.py DEIN_USERNAME             # nur analysieren
python GitHubFollowerCheckerCLI.py DEIN_USERNAME --json      # maschinenlesbar
python GitHubFollowerCheckerCLI.py DEIN_USERNAME --unfollow  # entfolgen (mit Rückfrage)
python GitHubFollowerCheckerCLI.py DEIN_USERNAME --unfollow --yes --quiet  # für Skripte
```

Die CLI beachtet die 🛡-Whitelist der GUI, pausiert zwischen Requests und
kennt außerdem `--version` und `--quiet`.

---

## 🔒 Sicherheit & Hinweise

* **Kein Token committen!** Die GUI speichert das Token standardmäßig nicht –
  optional legt „Token merken" es im **System-Schlüsselbund** ab
  (nie in einer Datei); abschalten löscht es wieder.
* Nutze wenn möglich einen **separaten Token** nur für dieses Tool.
* Exportierte CSV-Dateien enthalten Nutzernamen – `.gitignore` schließt `*.csv` bereits aus.
* Der Analyse-Verlauf (`~/.config/github-follower-checker/history.json`) und die
  Whitelist enthalten **nur Nutzernamen**, niemals Token oder andere Zugangsdaten.
* Das Tool respektiert GitHub-Rate-Limits durch Pausen zwischen Requests und
  zeigt bei Erreichen des Limits an, ab wann es weitergeht.

---

## 🐛 Fehlerbehebung

| Problem | Ursache / Lösung |
|---|---|
| „Token ungültig oder abgelaufen" | Token prüfen, ggf. neu erstellen; Scope `user:follow` erforderlich |
| „GitHub-Rate-Limit erreicht" | Warten bis zur angezeigten Uhrzeit, dann erneut versuchen |
| „GitHub-API-Fehler (HTTP 404)" | Username prüfen – existiert der Account? |
| „Keine Verbindung zur GitHub-API" | Internetverbindung / Firewall prüfen |
| GUI startet nicht | `pip install -r requirements.txt` ausführen und im Terminal starten |

---

## 🧪 Entwicklung

```bash
pip install -e ".[dev]"
ruff check .   # Lint
mypy GitHubFollowerCheckerGUI.py GitHubFollowerCheckerCLI.py   # Typen
pytest         # Tests (der GUI-Test benötigt ein Display, CI nutzt Xvfb)
```

Ein Git-Tag `v*` löst den Release-Workflow aus, der Windows- und
Linux-Binaries baut und ans GitHub-Release anhängt. Änderungen stehen im
[CHANGELOG](CHANGELOG.md).

Bei jedem Push laufen Lint, Syntax-Check und Tests automatisch per
**GitHub Actions** (siehe CI-Badge oben).

---

## 📄 Lizenz

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).

---

## ⚠️ Haftungsausschluss

Dieses Tool wird „wie besehen" bereitgestellt. Nutze es auf **eigene Verantwortung**.
Der Autor übernimmt keine Haftung für Verlust von Followern, mögliche Verstöße gegen
GitHubs Terms of Service oder andere unerwünschte Folgen.

**Empfehlung:** Teste das Tool zunächst mit einem Account, der wenige Follower hat.

---

**Erstellt mit ❤️ für die GitHub Community**
