#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Follower Checker - GUI Version
Automatische Dependency-Installation und benutzerfreundliche Fehlerbehandlung
"""

import sys
import subprocess
import time

# Funktion zum Installieren fehlender Pakete
def install_package(package_name):
    """Installiert ein fehlendes Python-Paket."""
    print(f"\n📦 Installiere {package_name}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        print(f"✅ {package_name} erfolgreich installiert!")
        return True
    except subprocess.CalledProcessError:
        print(f"❌ Fehler beim Installieren von {package_name}")
        return False

# Prüfe und installiere customtkinter
try:
    import customtkinter as ctk
except ImportError:
    print("⚠️ customtkinter ist nicht installiert!")
    if install_package("customtkinter"):
        import customtkinter as ctk
    else:
        print("\n❌ Konnte customtkinter nicht installieren!")
        print("Bitte installiere es manuell mit: pip install customtkinter")
        input("\nDrücke Enter zum Beenden...")
        sys.exit(1)

# Prüfe und installiere requests
try:
    import requests
except ImportError:
    print("⚠️ requests ist nicht installiert!")
    if install_package("requests"):
        import requests
    else:
        print("\n❌ Konnte requests nicht installieren!")
        print("Bitte installiere es manuell mit: pip install requests")
        input("\nDrücke Enter zum Beenden...")
        sys.exit(1)

import threading
from typing import List, Set, Callable
from tkinter import messagebox

# 🔑 GitHub API Configuration
BASE_URL = "https://api.github.com"

class GitHubUnfollower:
    def __init__(self, username: str, token: str, log_callback: Callable[[str], None] = None):
        self.username = username
        self.token = token
        self.log_callback = log_callback
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        })

    def log(self, message: str):
        """Logging mit optionalem Callback für GUI."""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)

    def validate_credentials(self) -> bool:
        """Validiert die GitHub-Zugangsdaten."""
        try:
            response = self.session.get(f"{BASE_URL}/user", timeout=10)
            if response.status_code == 200:
                return True
            elif response.status_code == 401:
                self.log("❌ Fehler: Token ungültig oder abgelaufen")
                return False
            else:
                self.log(f"❌ Fehler: HTTP Status {response.status_code}")
                return False
        except requests.RequestException as e:
            self.log(f"❌ Verbindungsfehler: {e}")
            return False

    def get_all_users(self, endpoint: str) -> Set[str]:
        """Holt alle User mit Pagination und gibt Set zurück."""
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
                time.sleep(0.1)

            except requests.RequestException as e:
                self.log(f"⚠️ Fehler beim Abrufen (Seite {page}): {e}")
                break

        return users

    def unfollow_users(self, users: List[str], progress_callback: Callable[[int, int], None] = None) -> tuple[int, int]:
        """Entfolgt User und gibt (Erfolge, Fehler) zurück."""
        success, failed = 0, 0
        total = len(users)

        for idx, user in enumerate(users, 1):
            try:
                response = self.session.delete(
                    f"{BASE_URL}/user/following/{user}",
                    timeout=10
                )

                if response.status_code == 204:
                    self.log(f"✅ Erfolgreich entfolgt: {user}")
                    success += 1
                else:
                    self.log(f"⚠️ Fehler bei {user}: Status {response.status_code}")
                    failed += 1

                if progress_callback:
                    progress_callback(idx, total)

                time.sleep(1)

            except requests.RequestException as e:
                self.log(f"⚠️ Fehler bei {user}: {e}")
                failed += 1

        return success, failed


class GitHubFollowerCheckerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Fenster-Konfiguration
        self.title("🐙 GitHub Follower Checker")
        self.geometry("900x700")

        # Dark Mode als Standard
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.unfollower = None
        self.not_following_back = []

        self.create_widgets()

    def create_widgets(self):
        # Header
        header = ctk.CTkLabel(
            self,
            text="🐙 GitHub Follower Checker",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        header.pack(pady=20)

        # Credentials Frame
        cred_frame = ctk.CTkFrame(self)
        cred_frame.pack(pady=10, padx=20, fill="x")

        ctk.CTkLabel(
            cred_frame,
            text="GitHub Username:",
            font=ctk.CTkFont(size=12)
        ).grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.username_entry = ctk.CTkEntry(
            cred_frame,
            width=300,
            placeholder_text="Dein GitHub Username"
        )
        self.username_entry.grid(row=0, column=1, padx=10, pady=10)

        ctk.CTkLabel(
            cred_frame,
            text="Personal Access Token:",
            font=ctk.CTkFont(size=12)
        ).grid(row=1, column=0, padx=10, pady=10, sticky="w")

        self.token_entry = ctk.CTkEntry(
            cred_frame,
            width=300,
            placeholder_text="ghp_...",
            show="*"
        )
        self.token_entry.grid(row=1, column=1, padx=10, pady=10)

        # Button Frame
        button_frame = ctk.CTkFrame(self)
        button_frame.pack(pady=10, padx=20, fill="x")

        self.analyze_button = ctk.CTkButton(
            button_frame,
            text="📊 Analyse starten",
            command=self.start_analysis,
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40
        )
        self.analyze_button.pack(side="left", padx=10, pady=10, expand=True, fill="x")

        self.unfollow_button = ctk.CTkButton(
            button_frame,
            text="🚫 Entfolgen",
            command=self.confirm_unfollow,
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            state="disabled",
            fg_color="red",
            hover_color="darkred"
        )
        self.unfollow_button.pack(side="left", padx=10, pady=10, expand=True, fill="x")

        # Log/Output Frame
        log_frame = ctk.CTkFrame(self)
        log_frame.pack(pady=10, padx=20, fill="both", expand=True)

        ctk.CTkLabel(
            log_frame,
            text="📝 Log / Ausgabe:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=10, pady=5)

        self.log_text = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(size=12),
            wrap="word"
        )
        self.log_text.pack(padx=10, pady=5, fill="both", expand=True)

        # Progress Bar
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.pack(pady=10, padx=20, fill="x")
        self.progress_bar.set(0)

        # Footer
        footer = ctk.CTkLabel(
            self,
            text="Erstellt mit ❤️ für die GitHub Community | MIT License",
            font=ctk.CTkFont(size=10)
        )
        footer.pack(pady=10)

    def log(self, message: str):
        """Fügt eine Log-Nachricht zur Textbox hinzu."""
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")

    def start_analysis(self):
        """Startet die Analyse in einem separaten Thread."""
        username = self.username_entry.get().strip()
        token = self.token_entry.get().strip()

        if not username or not token:
            messagebox.showerror("Fehler", "Bitte Username und Token eingeben!")
            return

        self.analyze_button.configure(state="disabled")
        self.unfollow_button.configure(state="disabled")
        self.log_text.delete("1.0", "end")
        self.progress_bar.set(0)

        # Analyse in separatem Thread ausführen
        thread = threading.Thread(target=self.perform_analysis, args=(username, token))
        thread.daemon = True
        thread.start()

    def perform_analysis(self, username: str, token: str):
        """Führt die Follower-Analyse durch."""
        try:
            self.unfollower = GitHubUnfollower(username, token, log_callback=self.log)

            self.log("🔐 Validiere Zugangsdaten...")
            if not self.unfollower.validate_credentials():
                self.log("❌ Authentifizierung fehlgeschlagen!")
                self.analyze_button.configure(state="normal")
                return

            self.log("✅ Zugangsdaten gültig!\n")

            self.log("📡 Lade Follower...")
            followers = self.unfollower.get_all_users(f"users/{username}/followers")
            self.log(f"✅ {len(followers)} Follower gefunden\n")

            self.log("📡 Lade Following...")
            following = self.unfollower.get_all_users(f"users/{username}/following")
            self.log(f"✅ {len(following)} Following gefunden\n")

            self.not_following_back = sorted(following - followers)

            if not self.not_following_back:
                self.log("✅ Alle folgen dir zurück! 🎉")
                self.analyze_button.configure(state="normal")
                return

            self.log(f"🚫 Diese {len(self.not_following_back)} Nutzer folgen dir nicht zurück:\n")
            for user in self.not_following_back:
                self.log(f"   - {user}")

            self.log(f"\n✅ Analyse abgeschlossen!")
            self.unfollow_button.configure(state="normal")

        except Exception as e:
            self.log(f"❌ Fehler: {e}")
        finally:
            self.analyze_button.configure(state="normal")

    def confirm_unfollow(self):
        """Zeigt Bestätigungsdialog und startet Entfolgen."""
        if not self.not_following_back:
            messagebox.showwarning("Warnung", "Keine Nutzer zum Entfolgen!")
            return

        response = messagebox.askyesno(
            "Bestätigung",
            f"Möchtest du wirklich {len(self.not_following_back)} Nutzer entfolgen?\n\n"
            "Diese Aktion kann nicht rückgängig gemacht werden!"
        )

        if response:
            self.unfollow_button.configure(state="disabled")
            self.analyze_button.configure(state="disabled")

            thread = threading.Thread(target=self.perform_unfollow)
            thread.daemon = True
            thread.start()

    def perform_unfollow(self):
        """Führt das Entfolgen durch."""
        try:
            self.log("\n🚀 Starte Entfolgen...\n")

            success, failed = self.unfollower.unfollow_users(
                self.not_following_back,
                progress_callback=self.update_progress
            )

            self.log(f"\n📊 Fertig!")
            self.log(f"✅ Erfolgreich entfolgt: {success}")
            self.log(f"❌ Fehlgeschlagen: {failed}")

            self.not_following_back = []

        except Exception as e:
            self.log(f"❌ Fehler beim Entfolgen: {e}")
        finally:
            self.analyze_button.configure(state="normal")
            self.unfollow_button.configure(state="disabled")
            self.progress_bar.set(0)

    def update_progress(self, current: int, total: int):
        """Aktualisiert die Progress Bar."""
        progress = current / total
        self.progress_bar.set(progress)


if __name__ == "__main__":
    try:
        print("\n🚀 Starte GitHub Follower Checker GUI...")
        print("📝 Alle Dependencies sind installiert!\n")
        app = GitHubFollowerCheckerApp()
        app.mainloop()
    except Exception as e:
        print("\n" + "="*50)
        print("❌ FEHLER beim Starten der Anwendung!")
        print("="*50)
        print(f"\nFehlermeldung: {e}")
        print(f"\nFehlertyp: {type(e).__name__}")
        print("\n💡 Mögliche Lösungen:")
        print("   1. Überprüfe deine Python-Installation")
        print("   2. Installiere Dependencies: pip install -r requirements.txt")
        print("   3. Führe das Skript im Terminal aus für mehr Details")
        print("\n" + "="*50)
        input("\n👆 Drücke Enter zum Beenden...")
        sys.exit(1)
