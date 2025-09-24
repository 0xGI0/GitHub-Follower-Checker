# 🐙 GitHub Follower Checker

Ein einfaches Python-Script, das deine **GitHub-Follower und Following** analysiert.  
Es zeigt:

- ✅ **Gegenseitige Follower** (folgt sich gegenseitig)  
- ❌ **Leute, denen du folgst, die dir nicht zurück folgen**  
- ⚠️ **Leute, die dir folgen, denen du nicht zurück folgst**  

## ✨ Features

- 🚀 Läuft ohne externe Module  
- 📈 Unterstützt beliebig viele Follower/Following  
- 🖥️ Übersichtliche Konsolen-Ausgabe  

## 🛠️ Verwendung

1. **Python 3 installieren**  
2. **PAT (Personal Access Token) erstellen**  
   - Gehe auf [GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)](https://github.com/settings/tokens)  
   - Klicke auf **Generate new token → Tokens (classic)**  
   - Gib dem Token einen Namen (z.B. „Follower Checker“)  
   - Wähle nur die Berechtigung: `read:user`  
   - Klicke auf **Generate token**  
3. **Token in das Script einfügen**  
4. **GitHub-Benutzernamen in das Script einfügen**  
5. Script ausführen:

```bash
python fol.py
