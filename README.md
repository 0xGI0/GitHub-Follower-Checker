## 🐙 GitHub Follower Checker (DE)

Python-Skripte, mit denen du deine **GitHub-Follower/Following-Beziehungen analysieren** und auf Wunsch Nutzer automatisch **entfolgen** kannst, die dir nicht zurück folgen.

Es gibt eine einfache und eine erweiterte (klassenbasierte) Variante – jeweils als **Analyse-** und **Analyse+Unfollow-Tool**.

---

## ✨ Features

- **Analyse deiner Beziehungen**
  - Wer folgt dir?
  - Wem folgst du?
  - Wer folgt dir nicht zurück?
  - Wem folgst du nicht zurück?
- **Automatisches Entfolgen (optional)**
  - Entfolge allen, die dir nicht zurück folgen – mit Sicherheitsabfrage
  - Schutz vor API-Limits durch kleine Pausen zwischen Requests
- **Stabilere „Long“-Variante**
  - Bessere Fehlerbehandlung (HTTP-Status, Exceptions)
  - Nutzung einer `requests.Session` und Typannotationen

---

## 📂 Überblick über die Skripte

| Script                          | Typ             | Funktion                                                                                                 |
|---------------------------------|-----------------|----------------------------------------------------------------------------------------------------------|
| `fol.py`                        | **einfach**     | Analysiert Follower/Following und zeigt: gegenseitige Follower, „du folgst, sie nicht“, „sie, du nicht“ |
| `fol1.py`                       | **einfach**     | Wie `fol.py`, bietet danach optionales automatisches Entfolgen von Nutzern, die dir nicht zurück folgen |
| `GitHubUnfollowerToolshort.py` | **kompakt**     | Kurze, optimierte Version zum Finden und (optional) Entfolgen von Nutzern, die dir nicht zurück folgen  |
| `GitHubUnfollowerToollong.py`  | **erweitert**   | Klassenbasiertes Tool mit besserer Fehlerbehandlung und Statistiken beim Entfolgen                      |

> **Empfehlung:**  
> Für ernsthafte Nutzung nimm am besten **`GitHubUnfollowerToollong.py`**  
> Für einen schnellen Test reicht **`GitHubUnfollowerToolshort.py`** oder **`fol.py`** (nur Analyse).

---

## 🧩 Technische Voraussetzungen

- **Python 3.x**
- Abhängigkeiten:

```bash
pip install requests
```

Es wird ausschließlich die offizielle **GitHub REST API v3** verwendet.

---

## 🔑 GitHub Personal Access Token (PAT) erstellen

1. Öffne auf GitHub:  
   `Settings` → `Developer settings` → `Personal access tokens` → `Tokens (classic)`
2. Klicke **„Generate new token (classic)”**
3. Vergib einen Namen, z. B. `GitHub Follower Checker`
4. Wähle mindestens diese Scopes:
   - Nur Analyse (`fol.py`): **`read:user`** reicht
   - Mit Entfolgen (`fol1.py`, `GitHubUnfollowerToolshort.py`, `GitHubUnfollowerToollong.py`): **`user:follow`**
5. Token generieren und **sicher speichern** (wird nur einmal vollständig angezeigt).

---

## ⚙️ Konfiguration in den Skripten

In allen Skripten musst du **Benutzername** und **Token** eintragen.

- In `fol.py` / `fol1.py`:

```python
username = "DEIN_GITHUB_USERNAME"
token = "DEIN_PERSONAL_ACCESS_TOKEN"
```

- In `GitHubUnfollowerToolshort.py`:

```python
USERNAME = "DEIN_GITHUB_USERNAME"
TOKEN = "DEIN_PERSONAL_ACCESS_TOKEN"
```

- In `GitHubUnfollowerToollong.py`:

```python
USERNAME = "DEIN_GITHUB_USERNAME"
TOKEN = "DEIN_PERSONAL_ACCESS_TOKEN"
```

> **Wichtig:**  
> Lass die Platzhalter **nicht** so stehen, sonst bricht `GitHubUnfollowerToollong.py` mit einem `ValueError` ab.

---

## ▶️ Ausführung der Skripte

Ausführen jeweils im Projektordner `GitHub-Follower-Checker`:

### Nur Analyse (keine Änderungen an deinem Account)

- **`fol.py`**:

```bash
python fol.py
```

Ausgabe u. a.:
- Gegenseitige Follower
- „Du folgst ihnen, sie folgen dir nicht“
- „Sie folgen dir, du folgst ihnen nicht“

### Analyse + optionales Entfolgen (einfach)

- **`fol1.py`**:

```bash
python fol1.py
```

Das Script zeigt, **wer dir nicht zurück folgt**, und fragt dann:

```text
❗ Soll wirklich entfolgt werden? (ja/nein):
```

Nur bei Eingabe von `ja` wird wirklich entfolgt.

### Analyse + optionales Entfolgen (kompakt)

- **`GitHubUnfollowerToolshort.py`**:

```bash
python GitHubUnfollowerToolshort.py
```

Zeigt dir die Anzahl und Liste der Nutzer, die dir nicht zurück folgen, und fragt dann:

```text
❗ X entfolgen? (ja/nein):
```

Auch hier wird nur bei `ja` entfolgt.

### Analyse + optionales Entfolgen (empfohlen, robust)

- **`GitHubUnfollowerToollong.py`**:

```bash
python GitHubUnfollowerToollong.py
```

Eigenschaften:
- Verwendet die Klasse `GitHubUnfollower`
- Bessere Fehlerbehandlung (HTTP-Status, Timeouts, Exceptions)
- Kurze Pausen zwischen Requests zum Schutz vor Rate-Limits
- Übersichtliche Abschluss-Statistik:
  - Wie viele Entfolgungen erfolgreich waren
  - Wie viele fehlgeschlagen sind

---

## 🔒 Sicherheit & Hinweise

- **Kein Token committen!**  
  Trage dein Token lokal ein, aber lade die Datei **nicht** mit Token zu GitHub hoch.
- Wenn möglich, nutze einen **separaten Token** nur für dieses Tool.
- Achte bei den Skripten mit Entfolgen (`fol1.py`, `GitHubUnfollowerToolshort.py`, `GitHubUnfollowerToollong.py`) genau auf die **Bestätigungsabfrage**.

---

## 🐛 Fehlerbehebung

- **HTTP 401 / 403**  
  - Token falsch, abgelaufen oder Scope fehlt (`user:follow`).
- **Leere Ausgabe / zu wenige Nutzer**  
  - Account ist privat / API-Limit erreicht / Netzwerkprobleme.
- **`ValueError: Bitte trage deine GitHub-Zugangsdaten ein!`**  
  - In `GitHubUnfollowerToollong.py` sind noch die Platzhalter-Werte gesetzt.

---

## 🇬🇧 GitHub Follower Checker (EN)

Python scripts to **analyze your GitHub follower/following relationships** and optionally **auto-unfollow** users who don’t follow you back.

There is a simple and an advanced (class-based) version – each available as a **“analyze only”** and **“analyze + unfollow”** tool.

---

## ✨ Features

- **Analyze your relationships**
  - Who follows you?
  - Who do you follow?
  - Who doesn’t follow you back?
  - Who do you not follow back?
- **Automatic unfollow (optional)**
  - Unfollow everyone who doesn’t follow you back – with a clear confirmation prompt
  - Small delays between requests to avoid hitting API rate limits
- **More robust “long” version**
  - Better error handling (HTTP status codes, exceptions)
  - Uses a `requests.Session` and type hints

---

## 📂 Script overview

| Script                          | Type          | Description                                                                                             |
|---------------------------------|---------------|---------------------------------------------------------------------------------------------------------|
| `fol.py`                        | **simple**    | Analyzes followers/following and shows: mutual followers, “you follow them, they don’t”, “they, you don’t” |
| `fol1.py`                       | **simple**    | Like `fol.py`, then optionally auto-unfollows users who don’t follow you back                          |
| `GitHubUnfollowerToolshort.py` | **compact**   | Short, optimized script to find (and optionally unfollow) users who don’t follow you back              |
| `GitHubUnfollowerToollong.py`  | **advanced**  | Class-based tool with better error handling and a small summary after unfollowing                      |

> **Recommendation:**  
> For real usage, prefer **`GitHubUnfollowerToollong.py`**.  
> For a quick test, use **`GitHubUnfollowerToolshort.py`** or **`fol.py`** (analyze only).

---

## 🧩 Requirements

- **Python 3.x**
- Dependencies:

```bash
pip install requests
```

This project only uses the official **GitHub REST API v3**.

---

## 🔑 Creating a GitHub Personal Access Token (PAT)

1. Go to GitHub:  
   `Settings` → `Developer settings` → `Personal access tokens` → `Tokens (classic)`
2. Click **“Generate new token (classic)”**
3. Choose a name, e.g. `GitHub Follower Checker`
4. Select at least these scopes:
   - Analyze only (`fol.py`): **`read:user`** is enough
   - With unfollow (`fol1.py`, `GitHubUnfollowerToolshort.py`, `GitHubUnfollowerToollong.py`): **`user:follow`**
5. Generate the token and **store it safely** (it is only shown once).

---

## ⚙️ Configuration in the scripts

In all scripts you must set your **username** and **token**.

- In `fol.py` / `fol1.py`:

```python
username = "YOUR_GITHUB_USERNAME"
token = "YOUR_PERSONAL_ACCESS_TOKEN"
```

- In `GitHubUnfollowerToolshort.py`:

```python
USERNAME = "YOUR_GITHUB_USERNAME"
TOKEN = "YOUR_PERSONAL_ACCESS_TOKEN"
```

- In `GitHubUnfollowerToollong.py`:

```python
USERNAME = "YOUR_GITHUB_USERNAME"
TOKEN = "YOUR_PERSONAL_ACCESS_TOKEN"
```

> **Important:**  
> Do **not** leave the placeholder values as they are, otherwise `GitHubUnfollowerToollong.py` will raise a `ValueError`.

---

## ▶️ Running the scripts

Always run them from the `GitHub-Follower-Checker` project directory.

### Analyze only (no changes to your account)

- **`fol.py`**:

```bash
python fol.py
```

Prints for example:
- Mutual followers
- “You follow them, they don’t”
- “They follow you, you don’t”

### Analyze + optional unfollow (simple)

- **`fol1.py`**:

```bash
python fol1.py
```

The script shows **who doesn’t follow you back** and then asks:

```text
❗ Soll wirklich entfolgt werden? (ja/nein):
```

Only if you type `ja` it will actually unfollow (prompt text is in German).

### Analyze + optional unfollow (compact)

- **`GitHubUnfollowerToolshort.py`**:

```bash
python GitHubUnfollowerToolshort.py
```

It prints the number and list of users who don’t follow you back and then asks:

```text
❗ X entfolgen? (ja/nein):
```

Only if you answer `ja` it will unfollow.

### Analyze + optional unfollow (recommended, robust)

- **`GitHubUnfollowerToollong.py`**:

```bash
python GitHubUnfollowerToollong.py
```

Features:
- Uses the `GitHubUnfollower` class
- Better error handling (HTTP status codes, timeouts, exceptions)
- Small delays between requests to protect against rate limits
- Clear final summary:
  - How many unfollows succeeded
  - How many failed

---

## 🔒 Security & notes

- **Never commit your token.**  
  Add it locally in your scripts, but do **not** push it to GitHub.
- If possible, use a **separate token** just for this tool.
- For scripts that unfollow (`fol1.py`, `GitHubUnfollowerToolshort.py`, `GitHubUnfollowerToollong.py`), double-check the **confirmation prompt**.

---

## 🐛 Troubleshooting

- **HTTP 401 / 403**  
  - Wrong token, expired token, or missing scope (`user:follow`).
- **Empty/too small result**  
  - Private account / API limit / network issues.
- **`ValueError: Bitte trage deine GitHub-Zugangsdaten ein!`**  
  - In `GitHubUnfollowerToollong.py` the placeholder values are still present.

In the future you could extend this project with **.env support**, **Docker**, or even a small **GUI/Web UI** if you like.

