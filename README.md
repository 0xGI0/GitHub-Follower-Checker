# 🐙 GitHub Follower Checker

Python-Scripte, die deine **GitHub-Follower und Following** analysieren.  
Es gibt zwei Varianten:  

- 📊 `fol.py` → zeigt nur deine Follower-Analyse an  
- 🚫 `fol1.py` → zeigt die Analyse **und entfolgt** optional allen, die dir nicht zurück folgen  

---

## ✨ Features

- ✅ Übersichtliche Konsolen-Ausgabe  
- 📈 Unterstützt beliebig viele Follower/Following (Pagination eingebaut)  
- 🖥️ Zwei Modi:
  - Analyse (sicher, keine Änderungen)  
  - Analyse + automatisches Entfolgen (optional, mit Bestätigung)  

---

## 📂 Scripts im Überblick

| Script         | Funktion                                                                 |
|----------------|--------------------------------------------------------------------------|
| 📊 `fol.py`    | Zeigt dir an, wer dir folgt, wem du folgst und wer dir nicht zurück folgt |
| 🚫 `fol1.py` | Macht die gleiche Analyse wie `fol.py`, fragt dich dann aber, ob du allen entfolgen willst, die dir nicht zurück folgen |

---

## 🛠️ Verwendung

### 1. Voraussetzungen
- **Python 3 installieren**  

### 2. Personal Access Token (PAT) erstellen
1. Gehe auf [GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)](https://github.com/settings/tokens)  
2. Klicke auf **Generate new token → Tokens (classic)**  
3. Gib dem Token einen Namen (z. B. „Follower Checker“)  
4. Wähle die Berechtigungen:  
   - Für `fol.py`: `read:user`  
   - Für `fol1.py`: `user:follow`  
5. Klicke auf **Generate token** und kopiere ihn

### 3. Token und GitHub-Namen ins Script einfügen
Öffne `fol.py` oder `unfollow.py` und trage ein:
```python
username = "DEIN_GITHUB_USERNAME"
token = "DEIN_PERSONAL_ACCESS_TOKEN"
