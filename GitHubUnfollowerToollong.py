import requests
import time
from typing import List, Set

# 🔑 Konfiguration
USERNAME = "DEIN_GITHUB_USERNAME"
TOKEN = "DEIN_PERSONAL_ACCESS_TOKEN"
BASE_URL = "https://api.github.com"

class GitHubUnfollower:
    def __init__(self, username: str, token: str):
        if username == "DEIN_GITHUB_USERNAME" or token == "DEIN_PERSONAL_ACCESS_TOKEN":
            raise ValueError("❌ Bitte trage deine GitHub-Zugangsdaten ein!")
        
        self.username = username
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        })
    
    def get_all_users(self, endpoint: str) -> Set[str]:
        """Holt alle User mit Pagination und gibt Set für schnellere Suche zurück."""
        users = set()
        page = 1
        
        while True:
            try:
                response = self.session.get(
                    f"{BASE_URL}/{endpoint}",
                    params={"per_page": 100, "page": page},
                    timeout=10
                )
                response.raise_for_status()
                
                data = response.json()
                if not data:
                    break
                
                users.update(user["login"] for user in data)
                page += 1
                time.sleep(0.1)  # Kleine Pause zwischen Requests
                
            except requests.RequestException as e:
                print(f"⚠️ Fehler beim Abrufen (Seite {page}): {e}")
                break
        
        return users
    
    def unfollow_users(self, users: List[str]) -> tuple[int, int]:
        """Entfolgt User und gibt (Erfolge, Fehler) zurück."""
        success, failed = 0, 0
        
        for user in users:
            try:
                response = self.session.delete(
                    f"{BASE_URL}/user/following/{user}",
                    timeout=10
                )
                
                if response.status_code == 204:
                    print(f"✅ Erfolgreich entfolgt: {user}")
                    success += 1
                else:
                    print(f"⚠️ Fehler bei {user}: Status {response.status_code}")
                    failed += 1
                
                time.sleep(1)  # API-Rate-Limit-Schutz
                
            except requests.RequestException as e:
                print(f"⚠️ Fehler bei {user}: {e}")
                failed += 1
        
        return success, failed
    
    def run(self):
        """Hauptlogik des Programms."""
        print("📡 Lade Follower...")
        followers = self.get_all_users(f"users/{self.username}/followers")
        
        print("📡 Lade Following...")
        following = self.get_all_users(f"users/{self.username}/following")
        
        # Effiziente Set-Operation statt List-Comprehension
        not_following_back = sorted(following - followers)
        
        print(f"\n🚫 Diese {len(not_following_back)} Nutzer folgen dir nicht zurück:")
        if not not_following_back:
            print("✅ Alle folgen dir zurück!")
            return
        
        for user in not_following_back:
            print(f" - {user}")
        
        # Sicherheitsabfrage
        confirm = input(f"\n❗ Willst du {len(not_following_back)} Nutzer entfolgen? (ja/nein): ")
        if confirm.lower() != "ja":
            print("❌ Abgebrochen – keine Änderungen.")
            return
        
        # Entfolgen
        success, failed = self.unfollow_users(not_following_back)
        print(f"\n📊 Fertig! Erfolgreich: {success} | Fehlgeschlagen: {failed}")

if __name__ == "__main__":
    try:
        unfollower = GitHubUnfollower(USERNAME, TOKEN)
        unfollower.run()
    except ValueError as e:
        print(e)
    except KeyboardInterrupt:
        print("\n\n❌ Abgebrochen durch Benutzer.")
