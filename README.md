# 🐙 GitHub Follower Checker

[![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/QG1o/GitHub-Follower-Checker?style=flat)](https://github.com/QG1o/GitHub-Follower-Checker/stargazers)

Python-Skript zum Analysieren deiner **GitHub-Follower/Following-Beziehungen** und zum optionalen automatischen **Entfolgen** von Nutzern, die dir nicht zurück folgen.

---

## ✨ Features

* **Analyse deiner Beziehungen**
  + Wer folgt dir?
  + Wem folgst du?
  + Wer folgt dir nicht zurück?
* **Automatisches Entfolgen (optional)**
  + Entfolge allen, die dir nicht zurück folgen – mit Sicherheitsabfrage
  + Schutz vor API-Limits durch kleine Pausen zwischen Requests
* **Robuste Implementierung**
  + Bessere Fehlerbehandlung (HTTP-Status, Exceptions, Timeouts)
  + Nutzung einer `requests.Session` und Typannotationen
  + Übersichtliche Statistiken nach dem Entfolgen
  + Validierung der Zugangsdaten beim Start
  + KeyboardInterrupt-Handling

---

## 🧩 Voraussetzungen

* **Python 3.x**
* Abhängigkeiten:

```bash
pip install -r requirements.txt
```

Oder manuell:
```bash
pip install requests customtkinter
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

## ⚙️ Konfiguration

### Für die GUI-Version
**Keine Konfiguration nötig!** Du gibst Username und Token direkt in der GUI ein. 🎉

### Für die CLI-Version
Im Skript musst du **Benutzername** und **Token** eintragen.

Öffne `GitHubUnfollowerToollong.py` und trage deine Daten ein:

```python
USERNAME = "DEIN_GITHUB_USERNAME"
TOKEN = "DEIN_PERSONAL_ACCESS_TOKEN"
```

> **Wichtig:**
> Lass die Platzhalter **nicht** so stehen, sonst bricht das Skript mit einem `ValueError` ab.

---

## ▶️ Ausführung

### 🖥️ GUI-Version (Empfohlen)

#### 🚀 Einfacher Start (Doppelklick!)

**Einfach doppelklicken:** `GitHubFollowerCheckerGUI.py`

Die Anwendung erledigt automatisch alles für dich:
- ✅ Prüft ob alle Dependencies installiert sind
- ✅ Installiert fehlende Pakete automatisch
- ✅ Zeigt Fehlermeldungen an (Fenster bleibt offen)
- ✅ Keine zusätzlichen Dateien nötig!

**Funktioniert auf:** Windows, Mac, Linux

#### 💻 Alternativ: Start über Terminal

```bash
python GitHubFollowerCheckerGUI.py
```

Oder:
```bash
python3 GitHubFollowerCheckerGUI.py
```

**Features der GUI:**
* 🎨 Modernes Dark Mode Design mit CustomTkinter
* 🔐 Sichere Token-Eingabe (Passwort-Feld)
* 📊 Live-Log-Anzeige während der Analyse
* 📈 Fortschrittsbalken beim Entfolgen
* ✅ Validierung der Zugangsdaten beim Start
* 🚫 Bestätigungsdialog vor dem Entfolgen
* 🖱️ Einfache Bedienung mit Buttons
* 🌐 Funktioniert auf Windows, Mac und Linux

**So funktioniert's:**
1. Trage deinen GitHub Username ein
2. Füge dein Personal Access Token ein (wird maskiert angezeigt)
3. Klicke auf "📊 Analyse starten"
4. Warte auf die Ergebnisse
5. Klicke auf "🚫 Entfolgen" um Nutzer zu entfolgen (mit Bestätigung)

---

### 💻 CLI-Version

Für die Kommandozeile (ohne GUI):

```bash
python GitHubUnfollowerToollong.py
```

Das Skript zeigt dir die Anzahl und Liste der Nutzer, die dir nicht zurück folgen, und fragt dann:

```
❗ Willst du X Nutzer entfolgen? (ja/nein):
```

Nur bei Eingabe von `ja` wird wirklich entfolgt.

**Eigenschaften:**

* Verwendet die Klasse `GitHubUnfollower`
* Bessere Fehlerbehandlung (HTTP-Status, Timeouts, Exceptions)
* Kurze Pausen zwischen Requests zum Schutz vor Rate-Limits
* Übersichtliche Abschluss-Statistik:
  + Wie viele Entfolgungen erfolgreich waren
  + Wie viele fehlgeschlagen sind
* Validierung der Zugangsdaten beim Start
* Unterstützung für KeyboardInterrupt (Ctrl+C)

---

## 🔒 Sicherheit & Hinweise

* **Kein Token committen!**  
  Trage dein Token lokal ein, aber lade die Datei **nicht** mit Token zu GitHub hoch.
* Wenn möglich, nutze einen **separaten Token** nur für dieses Tool.
* Achte genau auf die **Bestätigungsabfrage** vor dem Entfolgen.
* Das Skript respektiert GitHub's Rate-Limits durch kleine Pausen zwischen Requests.

---

## 🐛 Fehlerbehebung

* **HTTP 401 / 403**
  + Token falsch, abgelaufen oder Scope fehlt (`user:follow`).
* **Leere Ausgabe / zu wenige Nutzer**
  + Account ist privat / API-Limit erreicht / Netzwerkprobleme.
* **`ValueError: Bitte trage deine GitHub-Zugangsdaten ein!`**
  + Im Skript sind noch die Platzhalter-Werte gesetzt.
* **Rate Limit Fehler**
  + Das Skript hat bereits Pausen eingebaut. Bei sehr vielen Followern kann es trotzdem zu Limits kommen. Warte einige Minuten und versuche es erneut.

---

## 💡 Tipps

* Erstelle einen separaten GitHub-Token nur für dieses Tool
* Teste zuerst mit einem Account, der nur wenige Follower hat
* Das Skript zeigt dir immer eine Liste, bevor es entfolgt – nutze diese zur Kontrolle
* Du kannst das Skript jederzeit mit Ctrl+C abbrechen

---

## 📄 Lizenz

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).

Die MIT-Lizenz erlaubt die freie Verwendung, Modifikation und Weitergabe des Codes, solange der Copyright-Hinweis erhalten bleibt.

---

## ⚠️ Haftungsausschluss

Dieses Tool wird "wie besehen" bereitgestellt. Nutze es auf **eigene Verantwortung**. Der Autor übernimmt keine Haftung für:
- Verlust von Followern
- Mögliche Verstöße gegen GitHub's Terms of Service
- API-Rate-Limit-Probleme
- Andere unerwünschte Folgen

**Empfehlung:** Teste das Tool zunächst mit einem Test-Account oder bei wenigen Followern.

---

**Erstellt mit ❤️ für die GitHub Community**
