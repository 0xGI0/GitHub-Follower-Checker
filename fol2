import requests
import time

# 🔑 Zugangsdaten eintragen
username = "DEIN_GITHUB_USERNAME"
token = "DEIN_PERSONAL_ACCESS_TOKEN"

headers = {"Authorization": f"token {token}"}

def get_all_users(url):
    """Holt alle User von der GitHub API (mit Pagination)."""
    users = []
    page = 1
    while True:
        response = requests.get(url, headers=headers, params={"per_page": 100, "page": page})
        if response.status_code != 200:
            print(f"⚠️ Fehler beim Abrufen: {response.status_code}")
            break
        data = response.json()
        if not data:
            break
        users.extend([user["login"] for user in data])
        page += 1
    return users

# 📥 Followers und Following abrufen
followers = get_all_users(f"https://api.github.com/users/{username}/followers")
following = get_all_users(f"https://api.github.com/users/{username}/following")

# 📊 Wer folgt dir nicht zurück?
not_following_back = [user for user in following if user not in followers]

print("🚫 Diese Nutzer folgen dir nicht zurück:")
if not not_following_back:
    print("✅ Alle folgen dir zurück!")
else:
    for user in not_following_back:
        print(f" - {user}")

# 🛑 Sicherheit: Bestätigung abfragen
if not_following_back:
    confirm = input("\n❗ Soll wirklich entfolgt werden? (ja/nein): ")

    if confirm.lower() == "ja":
        for user in not_following_back:
            url = f"https://api.github.com/user/following/{user}"
            response = requests.delete(url, headers=headers)
            if response.status_code == 204:
                print(f"✅ Erfolgreich entfolgt: {user}")
            else:
                print(f"⚠️ Fehler bei {user}: {response.status_code}")
            time.sleep(1)  # kleine Pause, um API-Limits zu schonen
    else:
        print("❌ Abgebrochen – keine Änderungen vorgenommen.")
