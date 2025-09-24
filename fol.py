import requests

username = "DEIN_GITHUB_USERNAME"
token = "DEIN_PERSONAL_ACCESS_TOKEN"

headers = {"Authorization": f"token {token}"}

def get_all_users(url):
    users = []
    page = 1
    while True:
        response = requests.get(url, headers=headers, params={"per_page": 100, "page": page}).json()
        if not response:
            break
        users.extend([user["login"] for user in response])
        page += 1
    return users

# Alle Follower und Following abrufen
followers_list = get_all_users(f"https://api.github.com/users/{username}/followers")
following_list = get_all_users(f"https://api.github.com/users/{username}/following")

# Gegenseitige Follower
mutual = [user for user in followers_list if user in following_list]
not_following_back = [user for user in following_list if user not in followers_list]
not_followed_back = [user for user in followers_list if user not in following_list]

# Ausgabe
print("\n==============================")
print("        Gegenseitige Follower")
print("==============================")
for user in mutual:
    print(f"✔ {user}")

print("\n==============================")
print("  Du folgst ihnen, sie folgen dir nicht")
print("==============================")
for user in not_following_back:
    print(f"✖ {user}")

print("\n==============================")
print("  Sie folgen dir, du folgst ihnen nicht")
print("==============================")
for user in not_followed_back:
    print(f"⚠ {user}")

print("\nFertig!")
