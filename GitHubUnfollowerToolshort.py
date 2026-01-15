import requests
import time

# 🔑 Zugangsdaten
USERNAME = "DEIN_GITHUB_USERNAME"
TOKEN = "DEIN_PERSONAL_ACCESS_TOKEN"
HEADERS = {"Authorization": f"token {TOKEN}"}

def get_all_users(endpoint):
    """Holt alle User mit Pagination."""
    users, page = set(), 1
    while True:
        r = requests.get(f"https://api.github.com/{endpoint}", 
                        headers=HEADERS, params={"per_page": 100, "page": page})
        data = r.json() if r.status_code == 200 else []
        if not data: break
        users.update(u["login"] for u in data)
        page += 1
        time.sleep(0.1)  # Kleine Pause zwischen Seiten
    return users

# User abrufen
followers = get_all_users(f"users/{USERNAME}/followers")
following = get_all_users(f"users/{USERNAME}/following")
not_following = sorted(following - followers)

# Ergebnisse
print(f"\n🚫 {len(not_following)} Nutzer folgen nicht zurück:")
print("✅ Alle folgen zurück!" if not not_following else "\n".join(f" - {u}" for u in not_following))

# Entfolgen
if not_following and input(f"\n❗ {len(not_following)} entfolgen? (ja/nein): ").lower() == "ja":
    for user in not_following:
        r = requests.delete(f"https://api.github.com/user/following/{user}", headers=HEADERS)
        print(f"{'✅' if r.status_code == 204 else '⚠️'} {user}")
        time.sleep(1)
else:
    print("❌ Abgebrochen.")
