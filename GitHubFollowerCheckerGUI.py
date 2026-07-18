#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub Follower Checker – GUI (CustomTkinter).

Analysiert Follower/Following über die GitHub REST API v3 und kann Nutzern
entfolgen – allen, die nicht zurückfolgen, oder gezielt in der Tabelle
ausgewählten Nutzern – sowie Nutzern (zurück)folgen. Dazu: Fans-Ansicht,
Filter, Whitelist geschützter Nutzer, Rechtsklick-Menü, Rückgängig-Funktion
und ein lokaler Verlauf, der Follower-Veränderungen zwischen zwei Analysen
anzeigt. Alle API-Aufrufe laufen in einem Hintergrund-Thread, damit die
Oberfläche nicht einfriert. Das Token bleibt ausschließlich im
Arbeitsspeicher – es wird weder gespeichert noch geloggt.
"""

import csv
import io
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import Canvas, Menu, PhotoImage, filedialog, font as tkfont, messagebox, ttk
from typing import Callable, Optional, Set

__version__ = "1.1.0"


def _ensure_dependencies() -> None:
    """Installiert fehlende Pakete, damit der Doppelklick-Start funktioniert."""
    missing = []
    for package in ("customtkinter", "requests", "keyring"):
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    if not missing:
        return
    print(f"📦 Installiere fehlende Pakete: {', '.join(missing)}")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
    except subprocess.CalledProcessError:
        print("❌ Automatische Installation fehlgeschlagen.")
        print("   Bitte manuell installieren:  pip install -r requirements.txt")
        input("\nDrücke Enter zum Beenden...")
        sys.exit(1)


_ensure_dependencies()

import customtkinter as ctk  # noqa: E402
import requests  # noqa: E402
from PIL import Image  # noqa: E402  (Abhängigkeit von customtkinter)

try:
    import keyring  # noqa: E402
except Exception:  # keyring ist optional – ohne Backend einfach deaktivieren
    keyring = None

KEYRING_SERVICE = "github-follower-checker"

BASE_URL = "https://api.github.com"

# Pause zwischen Folgen/Entfolgen-Requests (Rate-Limit-Schonung)
ACTION_DELAY = 1.0

TABS = (
    ("unfollower", "Folgen nicht zurück"),
    ("fans", "Fans"),
    ("followers", "Follower"),
    ("following", "Following"),
    ("changes", "Verlauf"),
)

# Anzahl gespeicherter Analyse-Stände pro Nutzer
HISTORY_LIMIT = 50
TAB_LABELS = dict(TABS)
LABEL_TO_KEY = {label: key for key, label in TABS}

COLUMNS = ("user", "follows_you", "you_follow", "status")
COLUMN_TITLES = {
    "user": "Username",
    "follows_you": "Folgt dir",
    "you_follow": "Du folgst",
    "status": "Status",
}

# Nur Darstellungs-Einstellungen (Zoom, Theme, Fenster, Whitelist) –
# niemals Zugangsdaten!
SETTINGS_PATH = Path.home() / ".config" / "github-follower-checker" / "settings.json"

# Letzter Analyse-Stand pro Username (nur Nutzernamen, kein Token)
HISTORY_PATH = SETTINGS_PATH.parent / "history.json"

ZOOM_STEPS = (1.0, 1.25, 1.5, 1.75, 2.0)


def _load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_settings(settings: dict) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except OSError:
        pass  # Anzeige-Einstellungen sind nicht kritisch


def _load_history() -> dict:
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_history(history: dict) -> None:
    try:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except OSError:
        pass  # Verlauf ist nicht kritisch


def _normalize_history_entries(value) -> list:
    """Migriert das alte Ein-Snapshot-Format auf die Snapshot-Liste."""
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return value
    return []


def compute_follower_delta(previous: Set[str], current: Set[str]) -> tuple:
    """Neue und verlorene Follower seit dem letzten Lauf, alphabetisch sortiert."""
    by_name = lambda u: u.lower()  # noqa: E731
    return (
        sorted(current - previous, key=by_name),
        sorted(previous - current, key=by_name),
    )


TREE_THEME = {
    "dark": {
        "bg": "#1d1e1e",
        "fg": "#e6e6e6",
        "stripe": "#242526",
        "heading_bg": "#2b2b2b",
        "heading_fg": "#f0f0f0",
        "heading_active": "#333333",
        "selected": "#1f538d",
    },
    "light": {
        "bg": "#fbfbfb",
        "fg": "#1c1c1c",
        "stripe": "#f1f1f1",
        "heading_bg": "#e4e4e4",
        "heading_fg": "#1c1c1c",
        "heading_active": "#d8d8d8",
        "selected": "#3a7ebf",
    },
}


class RateLimitError(Exception):
    """GitHub-Rate-Limit erreicht."""

    def __init__(self, reset_time: Optional[datetime]):
        super().__init__("GitHub-Rate-Limit erreicht")
        self.reset_time = reset_time


class AuthError(Exception):
    """Token ungültig oder Berechtigung fehlt."""


class GitHubClient:
    def __init__(self, username: str, token: str):
        self.username = username
        self.rate_remaining: Optional[int] = None
        self.rate_limit: Optional[int] = None
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        })

    def _raise_for_rate_limit(self, response: requests.Response) -> None:
        try:
            self.rate_remaining = int(response.headers["X-RateLimit-Remaining"])
            self.rate_limit = int(response.headers["X-RateLimit-Limit"])
        except (KeyError, ValueError):
            pass
        if (
            response.status_code in (403, 429)
            and response.headers.get("X-RateLimit-Remaining") == "0"
        ):
            reset_header = response.headers.get("X-RateLimit-Reset")
            reset_time = (
                datetime.fromtimestamp(int(reset_header)) if reset_header else None
            )
            raise RateLimitError(reset_time)

    def validate_credentials(self) -> None:
        response = self.session.get(f"{BASE_URL}/user", timeout=10)
        self._raise_for_rate_limit(response)
        if response.status_code == 401:
            raise AuthError("Token ungültig oder abgelaufen")
        response.raise_for_status()

    def fetch_all_users(
        self, endpoint: str, on_page: Optional[Callable[[int], None]] = None
    ) -> Set[str]:
        """Holt alle User eines Endpoints mit Pagination."""
        users: Set[str] = set()
        page = 1
        while True:
            if on_page:
                on_page(page)
            response = self.session.get(
                f"{BASE_URL}/{endpoint}",
                params={"per_page": 100, "page": page},
                timeout=10,
            )
            self._raise_for_rate_limit(response)
            response.raise_for_status()
            data = response.json()
            if not data:
                return users
            users.update(user["login"] for user in data)
            page += 1
            time.sleep(0.1)

    def unfollow(self, user: str) -> tuple:
        response = self.session.delete(
            f"{BASE_URL}/user/following/{user}", timeout=10
        )
        self._raise_for_rate_limit(response)
        if response.status_code == 204:
            return True, "✓ Entfolgt"
        return False, f"Fehler (HTTP {response.status_code})"

    def follow(self, user: str) -> tuple:
        response = self.session.put(
            f"{BASE_URL}/user/following/{user}", timeout=10
        )
        self._raise_for_rate_limit(response)
        if response.status_code == 204:
            return True, "✓ Gefolgt"
        return False, f"Fehler (HTTP {response.status_code})"

    def get_user(self, user: str) -> dict:
        response = self.session.get(f"{BASE_URL}/users/{user}", timeout=10)
        self._raise_for_rate_limit(response)
        response.raise_for_status()
        return response.json()


class FollowerCheckerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.settings = _load_settings()

        ctk.set_appearance_mode(self.settings.get("appearance", "Dark"))
        ctk.set_default_color_theme("blue")

        # CustomTkinter erkennt die Display-Skalierung unter Linux/Wayland
        # nicht selbst – gespeicherten bzw. erkannten Faktor anwenden.
        self.ui_scale = float(self.settings.get("zoom") or self._detect_ui_scale())
        ctk.set_widget_scaling(self.ui_scale)
        ctk.set_window_scaling(self.ui_scale)

        self.title("GitHub Follower Checker")
        self.geometry("1180x740")
        self._apply_minsize()
        icon_path = Path(__file__).resolve().parent / "docs" / "icon.png"
        if icon_path.exists():
            try:
                self.iconphoto(True, PhotoImage(file=str(icon_path)))
            except Exception:
                pass

        self.client: Optional[GitHubClient] = None
        self.followers: Set[str] = set()
        self.following: Set[str] = set()
        self.rows = {key: [] for key, _ in TABS}
        self.sort_state = {}
        self.unfollow_candidates = []
        self.current_tab = "unfollower"
        self._busy = False
        self.whitelist: Set[str] = set(self.settings.get("whitelist", []))
        self.last_unfollowed = []
        self.sort_state["changes"] = ("status", True)  # Verlauf: Neuestes zuerst
        self._spark_counts = []
        self._profile_cache = {}
        self._detail_after = None
        self._pending_token = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main()
        self._style_treeview()
        self._populate_tree()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # Manche Window-Manager stauchen das Fenster beim Start auf die
        # Mindestgröße – Geometrie nach dem Mapping erneut durchsetzen.
        self.after(250, self._restore_geometry)

    def _restore_geometry(self):
        saved = self.settings.get("window_geometry")
        try:
            if saved:
                self.wm_geometry(saved)
            else:
                self.geometry("1180x740")
        except Exception:
            pass

    def _on_close(self):
        self.settings["window_geometry"] = self.wm_geometry()
        self.settings["whitelist"] = sorted(self.whitelist)
        _save_settings(self.settings)
        self.destroy()

    # ------------------------------------------------------------- Aufbau

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=300, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsw")
        # Kinder sind pack-verwaltet: pack_propagate stoppt das Schrumpfen
        # auf Inhaltsbreite, grid_propagate würde hier nichts bewirken.
        sidebar.pack_propagate(False)

        ctk.CTkLabel(
            sidebar,
            text="🐙 Follower Checker",
            font=ctk.CTkFont(size=21, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(14, 0))
        ctk.CTkLabel(
            sidebar,
            text="GitHub-Beziehungen analysieren",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
        ).pack(anchor="w", padx=20)

        self._section_label(sidebar, "ZUGANGSDATEN", pady=(16, 4))

        self.username_entry = ctk.CTkEntry(
            sidebar, placeholder_text="GitHub-Username", height=36
        )
        self.username_entry.pack(fill="x", padx=20, pady=(0, 8))

        self.token_entry = ctk.CTkEntry(
            sidebar, placeholder_text="Personal Access Token", height=36, show="•"
        )
        self.token_entry.pack(fill="x", padx=20)
        self.token_entry.bind("<Return>", lambda _e: self.start_analysis())

        self.show_token = ctk.CTkCheckBox(
            sidebar,
            text="Token anzeigen",
            font=ctk.CTkFont(size=12),
            command=self._toggle_token_visibility,
            checkbox_width=18,
            checkbox_height=18,
        )
        self.show_token.pack(anchor="w", padx=20, pady=(8, 0))

        self.remember_token = None
        if keyring is not None:
            self.remember_token = ctk.CTkCheckBox(
                sidebar,
                text="Token merken (Schlüsselbund)",
                font=ctk.CTkFont(size=12),
                command=self._on_remember_toggle,
                checkbox_width=18,
                checkbox_height=18,
            )
            self.remember_token.pack(anchor="w", padx=20, pady=(6, 0))
            if self.settings.get("remember_token"):
                self.remember_token.select()
                self._prefill_credentials()

        self.analyze_button = ctk.CTkButton(
            sidebar,
            text="Analyse starten",
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.start_analysis,
        )
        self.analyze_button.pack(fill="x", padx=20, pady=(12, 0))

        self.progress = ctk.CTkProgressBar(sidebar, height=6)
        self.progress.pack(fill="x", padx=20, pady=(8, 0))
        self.progress.set(0)

        self.status_label = ctk.CTkLabel(
            sidebar,
            text="Bereit. Gib Username und Token ein.",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray65"),
            wraplength=250,
            justify="left",
            anchor="w",
        )
        self.status_label.pack(fill="x", padx=20, pady=(6, 0))

        self._section_label(sidebar, "ERGEBNIS", pady=(14, 4))

        stats_card = ctk.CTkFrame(sidebar, corner_radius=10)
        stats_card.pack(fill="x", padx=20)
        self.stat_values = {}
        stats = (
            ("followers", "Follower", None),
            ("following", "Following", None),
            ("fans", "Fans", ("#2e7d32", "#66bb6a")),
            ("unfollower", "Folgen nicht zurück", ("#c62828", "#ef5350")),
        )
        for i, (key, title, accent) in enumerate(stats):
            row = ctk.CTkFrame(stats_card, fg_color="transparent")
            row.pack(
                fill="x",
                padx=14,
                pady=(10 if i == 0 else 3, 10 if i == len(stats) - 1 else 3),
            )
            ctk.CTkLabel(
                row,
                text=title,
                font=ctk.CTkFont(size=12),
                text_color=("gray30", "gray65"),
            ).pack(side="left")
            value = ctk.CTkLabel(
                row,
                text="–",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=accent,
            )
            value.pack(side="right")
            self.stat_values[key] = value

        self._section_label(sidebar, "SEIT LETZTER ANALYSE", pady=(14, 4))
        self.delta_label = ctk.CTkLabel(
            sidebar,
            text="Noch kein Vergleich vorhanden.",
            font=ctk.CTkFont(size=11),
            text_color=("gray30", "gray65"),
            wraplength=250,
            justify="left",
            anchor="w",
        )
        self.delta_label.pack(fill="x", padx=20)

        # Follower-Verlauf als Mini-Diagramm (erscheint ab zwei Analysen)
        self.spark_canvas = Canvas(
            sidebar, height=36, width=250, highlightthickness=0, bd=0
        )

        ctk.CTkLabel(
            sidebar,
            text=f"v{__version__} · MIT License · GitHub REST API v3",
            font=ctk.CTkFont(size=10),
            text_color=("gray45", "gray50"),
        ).pack(side="bottom", pady=(0, 12))

        footer_row = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer_row.pack(side="bottom", fill="x", padx=20, pady=(0, 10))
        footer_row.grid_columnconfigure((0, 1), weight=1, uniform="footer")

        self.appearance_menu = ctk.CTkOptionMenu(
            footer_row,
            values=["Dark", "Light", "System"],
            command=self._change_appearance,
            height=28,
            font=ctk.CTkFont(size=12),
        )
        self.appearance_menu.set(self.settings.get("appearance", "Dark"))
        self.appearance_menu.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.zoom_menu = ctk.CTkOptionMenu(
            footer_row,
            values=[f"{int(step * 100)} %" for step in ZOOM_STEPS],
            command=self._change_zoom,
            height=28,
            font=ctk.CTkFont(size=12),
        )
        self.zoom_menu.set(f"{int(self.ui_scale * 100)} %")
        self.zoom_menu.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.rate_label = ctk.CTkLabel(
            sidebar,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=("gray45", "gray50"),
            anchor="w",
        )
        self.rate_label.pack(side="bottom", fill="x", padx=20, pady=(0, 4))

    def _prefill_credentials(self):
        """Füllt Username/Token aus Settings und Schlüsselbund vor."""
        last = self.settings.get("last_username")
        if not last:
            return
        self.username_entry.insert(0, last)
        try:
            token = keyring.get_password(KEYRING_SERVICE, last)
        except Exception:
            token = None
        if token:
            self.token_entry.insert(0, token)
            self.status_label.configure(
                text="Zugangsdaten aus dem Schlüsselbund geladen."
            )

    def _on_remember_toggle(self):
        remember = bool(self.remember_token.get())
        self.settings["remember_token"] = remember
        if not remember:
            last = self.settings.get("last_username")
            if last:
                try:
                    keyring.delete_password(KEYRING_SERVICE, last)
                except Exception:
                    pass
        _save_settings(self.settings)

    def _persist_credentials(self, username, token):
        """Speichert Token im Schlüsselbund, wenn „Token merken“ aktiv ist."""
        self.settings["last_username"] = username
        if self.remember_token is not None and self.remember_token.get():
            try:
                keyring.set_password(KEYRING_SERVICE, username, token)
            except Exception:
                pass
        _save_settings(self.settings)

    def _update_rate_label(self):
        remaining = getattr(self.client, "rate_remaining", None)
        limit = getattr(self.client, "rate_limit", None)
        if remaining is not None and limit:
            self.rate_label.configure(text=f"API-Limit: {remaining}/{limit}")

    @staticmethod
    def _section_label(parent, text, pady):
        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).pack(anchor="w", padx=20, pady=pady)

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        top_bar = ctk.CTkFrame(main, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        self.segment = ctk.CTkSegmentedButton(
            top_bar,
            values=[label for _, label in TABS],
            command=self._on_tab_change,
            font=ctk.CTkFont(size=12),
        )
        self.segment.set(TAB_LABELS["unfollower"])
        self.segment.pack(side="left")

        self.export_button = ctk.CTkButton(
            top_bar,
            text="⬇  CSV exportieren",
            width=150,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color="transparent",
            border_width=1,
            border_color=("gray55", "gray40"),
            text_color=("gray15", "gray85"),
            hover_color=("gray85", "gray25"),
            command=self.export_csv,
        )
        self.export_button.pack(side="right")

        self.search_entry = ctk.CTkEntry(
            top_bar,
            placeholder_text="🔍  Nutzer filtern…",
            width=180,
            height=32,
            font=ctk.CTkFont(size=12),
        )
        self.search_entry.pack(side="right", padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", lambda _e: self._populate_tree())
        self.search_entry.bind(
            "<Escape>",
            lambda _e: (self.search_entry.delete(0, "end"), self._populate_tree()),
        )

        self.table_frame = ctk.CTkFrame(main, corner_radius=10)
        self.table_frame.grid(row=1, column=0, sticky="nsew")

        self.tree = ttk.Treeview(
            self.table_frame,
            columns=COLUMNS,
            show="headings",
            style="Checker.Treeview",
            selectmode="extended",
        )
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._on_selection_change())
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.column("user", width=280, anchor="w")
        self.tree.column("follows_you", width=110, anchor="center", stretch=False)
        self.tree.column("you_follow", width=110, anchor="center", stretch=False)
        self.tree.column("status", width=200, anchor="w", stretch=False)

        scrollbar = ctk.CTkScrollbar(self.table_frame, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=8)
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)

        self.empty_label = ctk.CTkLabel(
            self.table_frame,
            text="Noch keine Daten.\nStarte links eine Analyse.",
            font=ctk.CTkFont(size=14),
            text_color=("gray45", "gray55"),
            justify="center",
        )

        # Profil-Panel: erscheint, wenn genau ein Nutzer ausgewählt ist
        self.detail_frame = ctk.CTkFrame(main, corner_radius=10)
        self.detail_avatar = ctk.CTkLabel(self.detail_frame, text="")
        self.detail_avatar.pack(side="left", padx=(12, 10), pady=8)
        self.detail_text = ctk.CTkLabel(
            self.detail_frame,
            text="",
            font=ctk.CTkFont(size=12),
            justify="left",
            anchor="w",
        )
        self.detail_text.pack(side="left", fill="x", expand=True, pady=8, padx=(0, 12))

        bottom_bar = ctk.CTkFrame(main, fg_color="transparent")
        bottom_bar.grid(row=3, column=0, sticky="ew", pady=(12, 0))

        self.unfollow_button = ctk.CTkButton(
            bottom_bar,
            text="🚫 Alle Nicht-Folgenden",
            width=190,
            height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=("#c62828", "#b3261e"),
            hover_color=("#a91f1f", "#8c1d18"),
            state="disabled",
            command=self.confirm_unfollow,
        )
        self.unfollow_button.pack(side="right")

        self.unfollow_selected_button = ctk.CTkButton(
            bottom_bar,
            text="Auswahl entfolgen",
            width=150,
            height=34,
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            border_width=1,
            border_color=("#c62828", "#b3261e"),
            text_color=("#c62828", "#ef5350"),
            hover_color=("gray85", "gray25"),
            state="disabled",
            command=self.confirm_unfollow_selection,
        )
        self.unfollow_selected_button.pack(side="right", padx=(0, 8))

        # Erscheint erst nach einem Entfolgen-Lauf (folgt den Nutzern wieder)
        self.undo_button = ctk.CTkButton(
            bottom_bar,
            text="↩ Rückgängig",
            width=140,
            height=34,
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            border_width=1,
            border_color=("gray55", "gray40"),
            text_color=("gray15", "gray85"),
            hover_color=("gray85", "gray25"),
            command=self.undo_unfollow,
        )

        ctk.CTkLabel(
            bottom_bar,
            text="Tipp: Strg/Shift-Klick wählt mehrere, Rechtsklick öffnet Aktionen.",
            font=ctk.CTkFont(size=11),
            text_color=("gray45", "gray55"),
            anchor="w",
        ).pack(side="left", fill="x")

    def _style_treeview(self):
        mode = "dark" if ctk.get_appearance_mode() == "Dark" else "light"
        colors = TREE_THEME[mode]
        family = tkfont.nametofont("TkDefaultFont").actual("family")

        style = ttk.Style(self)
        style.theme_use("clam")
        # Rahmenelemente des clam-Themes entfernen, nur die Datenfläche zeichnen
        style.layout(
            "Checker.Treeview",
            [("Checker.Treeview.treearea", {"sticky": "nswe"})],
        )
        # ttk skaliert nicht mit CustomTkinter mit – Zoomfaktor selbst anwenden
        scale = self.ui_scale
        style.configure(
            "Checker.Treeview",
            background=colors["bg"],
            fieldbackground=colors["bg"],
            foreground=colors["fg"],
            rowheight=int(32 * scale),
            borderwidth=0,
            relief="flat",
            font=(family, int(10 * scale)),
        )
        style.configure(
            "Checker.Treeview.Heading",
            background=colors["heading_bg"],
            foreground=colors["heading_fg"],
            relief="flat",
            borderwidth=0,
            padding=(int(10 * scale), int(8 * scale)),
            font=(family, int(10 * scale), "bold"),
        )
        style.map(
            "Checker.Treeview.Heading",
            background=[("active", colors["heading_active"])],
        )
        style.map(
            "Checker.Treeview",
            background=[("selected", colors["selected"])],
            foreground=[("selected", "#ffffff")],
        )
        self.tree.tag_configure("odd", background=colors["stripe"])
        self.table_frame.configure(fg_color=colors["bg"])

        self.tree.column("user", width=int(280 * scale), anchor="w")
        self.tree.column("follows_you", width=int(110 * scale), anchor="center", stretch=False)
        self.tree.column("you_follow", width=int(110 * scale), anchor="center", stretch=False)
        self.tree.column("status", width=int(200 * scale), anchor="w", stretch=False)

        self._draw_sparkline()

    # ---------------------------------------------------------- Tabelle

    def _on_tab_change(self, label):
        self.current_tab = LABEL_TO_KEY[label]
        self._populate_tree()

    def _sort_by(self, col):
        prev_col, prev_reverse = self.sort_state.get(self.current_tab, ("user", False))
        reverse = not prev_reverse if prev_col == col else False
        self.sort_state[self.current_tab] = (col, reverse)
        self._populate_tree()

    @staticmethod
    def _sort_key(row, col):
        if col == "user":
            return (row["user"].lower(),)
        if col in ("follows_you", "you_follow"):
            return (row[col], row["user"].lower())
        # Verlauf-Zeilen tragen einen ISO-Zeitstempel als Sortierschlüssel
        return (row.get("sort", row["status"]), row["user"].lower())

    def _visible_rows(self):
        rows = self.rows[self.current_tab]
        term = self.search_entry.get().strip().lower()
        if term:
            rows = [r for r in rows if term in r["user"].lower()]
        return rows

    def _populate_tree(self):
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())

        col, reverse = self.sort_state.get(self.current_tab, ("user", False))
        rows = sorted(
            self._visible_rows(),
            key=lambda r: self._sort_key(r, col),
            reverse=reverse,
        )
        for index, row in enumerate(rows):
            shield = "🛡 " if row["user"] in self.whitelist else ""
            self.tree.insert(
                "",
                "end",
                iid=row["user"],
                tags=("odd",) if index % 2 else (),
                values=(
                    shield + row["user"],
                    "✓" if row["follows_you"] else "–",
                    "✓" if row["you_follow"] else "–",
                    row["status"],
                ),
            )
        keep = [r["user"] for r in rows if r["user"] in selected]
        if keep:
            self.tree.selection_set(keep)

        for c in COLUMNS:
            arrow = ("  ↓" if reverse else "  ↑") if c == col else ""
            self.tree.heading(
                c,
                text=COLUMN_TITLES[c] + arrow,
                anchor="center" if c in ("follows_you", "you_follow") else "w",
                command=lambda c=c: self._sort_by(c),
            )

        if rows:
            self.empty_label.place_forget()
        else:
            term = self.search_entry.get().strip()
            self.empty_label.configure(
                text=f"Keine Treffer für „{term}“."
                if term
                else "Noch keine Daten.\nStarte links eine Analyse."
            )
            self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

        self._update_unfollow_buttons()

    def _rebuild_rows(self):
        def row(user):
            return {
                "user": user,
                "follows_you": user in self.followers,
                "you_follow": user in self.following,
                "status": "",
            }

        by_name = lambda u: u.lower()  # noqa: E731
        self.rows["followers"] = [row(u) for u in sorted(self.followers, key=by_name)]
        self.rows["following"] = [row(u) for u in sorted(self.following, key=by_name)]
        self.rows["unfollower"] = [
            row(u) for u in sorted(self.following - self.followers, key=by_name)
        ]
        self.rows["fans"] = [
            row(u) for u in sorted(self.followers - self.following, key=by_name)
        ]

    def _set_row_status(self, user, text):
        for key, rows in self.rows.items():
            if key == "changes":  # Verlaufs-Einträge nicht überschreiben
                continue
            for row in rows:
                if row["user"] == user:
                    row["status"] = text
        if self.current_tab != "changes" and self.tree.exists(user):
            self.tree.set(user, "status", text)

    def _update_stats(self):
        self.stat_values["followers"].configure(text=str(len(self.followers)))
        self.stat_values["following"].configure(text=str(len(self.following)))
        self.stat_values["fans"].configure(
            text=str(len(self.followers - self.following))
        )
        self.stat_values["unfollower"].configure(
            text=str(len(self.following - self.followers))
        )

    def _selected_unfollowable(self):
        """Ausgewählte Nutzer, denen aktuell noch gefolgt wird."""
        return [u for u in self.tree.selection() if u in self.following]

    def _compute_candidates(self):
        """Nicht-Zurückfolgende ohne bereits Entfolgte und ohne Whitelist."""
        return [
            r["user"]
            for r in self.rows["unfollower"]
            if r["status"] != "✓ Entfolgt" and r["user"] not in self.whitelist
        ]

    def _update_unfollow_buttons(self):
        n = len(self.unfollow_candidates)
        self.unfollow_button.configure(
            text=f"🚫 Alle Nicht-Folgenden ({n})" if n else "🚫 Alle Nicht-Folgenden",
            state="normal" if n and not self._busy else "disabled",
        )
        m = len(self._selected_unfollowable())
        self.unfollow_selected_button.configure(
            text=f"Auswahl entfolgen ({m})" if m else "Auswahl entfolgen",
            state="normal" if m and not self._busy else "disabled",
        )
        if self.last_unfollowed:
            self.undo_button.configure(
                text=f"↩ Rückgängig ({len(self.last_unfollowed)})",
                state="disabled" if self._busy else "normal",
            )

    def _show_undo_button(self):
        self.undo_button.pack(
            side="right", padx=(0, 8), after=self.unfollow_selected_button
        )

    def _hide_undo_button(self):
        self.last_unfollowed = []
        self.undo_button.pack_forget()

    def _mark_unfollowed(self, user):
        self.following.discard(user)
        for rows in self.rows.values():
            for row in rows:
                if row["user"] == user:
                    row["you_follow"] = False
        if self.tree.exists(user):
            self.tree.set(user, "you_follow", "–")

    def _mark_followed(self, user):
        self.following.add(user)
        for rows in self.rows.values():
            for row in rows:
                if row["user"] == user:
                    row["you_follow"] = True
        if self.tree.exists(user):
            self.tree.set(user, "you_follow", "✓")

    def _set_protected(self, users, protect):
        if protect:
            self.whitelist.update(users)
        else:
            self.whitelist.difference_update(users)
        self.settings["whitelist"] = sorted(self.whitelist)
        _save_settings(self.settings)
        self.unfollow_candidates = self._compute_candidates()
        self._populate_tree()

    # ------------------------------------------------- Profil-Detailpanel

    def _on_selection_change(self):
        self._update_unfollow_buttons()
        self._schedule_detail_update()

    def _schedule_detail_update(self):
        if self._detail_after is not None:
            self.after_cancel(self._detail_after)
            self._detail_after = None
        selection = self.tree.selection()
        usable = (
            len(selection) == 1
            and self.client is not None
            and hasattr(self.client, "get_user")
            and not self._busy
        )
        if not usable:
            self.detail_frame.grid_remove()
            return
        user = selection[0]
        if user in self._profile_cache:
            self._show_detail(user)
        else:
            self._detail_after = self.after(350, lambda: self._start_profile_fetch(user))

    def _start_profile_fetch(self, user):
        self._detail_after = None
        threading.Thread(target=self._profile_worker, args=(user,), daemon=True).start()

    def _profile_worker(self, user):
        try:
            data = self.client.get_user(user)
            avatar = None
            url = data.get("avatar_url")
            if url:
                response = self.client.session.get(url, params={"s": 96}, timeout=10)
                if response.status_code == 200:
                    avatar = response.content
        except Exception:
            return  # Panel ist reiner Komfort – Fehler still ignorieren
        self._ui(self._store_profile, user, data, avatar)

    def _store_profile(self, user, data, avatar_bytes):
        image = None
        if avatar_bytes:
            try:
                pil = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
                image = ctk.CTkImage(light_image=pil, dark_image=pil, size=(36, 36))
            except Exception:
                image = None
        self._profile_cache[user] = (data, image)
        selection = self.tree.selection()
        if len(selection) == 1 and selection[0] == user:
            self._show_detail(user)

    def _show_detail(self, user):
        data, image = self._profile_cache[user]
        name = data.get("name") or user
        parts = [name if name == user else f"{name} (@{user})"]
        parts.append(f"{data.get('followers', '?')} Follower")
        parts.append(f"{data.get('following', '?')} Following")
        created = str(data.get("created_at", ""))[:4]
        if created:
            parts.append(f"dabei seit {created}")
        lines = ["  ·  ".join(parts)]
        bio = (data.get("bio") or "").strip().replace("\n", " ")
        if bio:
            if len(bio) > 110:
                bio = bio[:110] + "…"
            lines.append(bio)
        self.detail_text.configure(text="\n".join(lines))
        self.detail_avatar.configure(image=image, text="" if image else "👤")
        self.detail_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))

    # ------------------------------------------------------- Sparkline

    def _draw_sparkline(self):
        counts = self._spark_counts[-30:]
        if len(counts) < 2:
            self.spark_canvas.pack_forget()
            return
        dark = ctk.get_appearance_mode() == "Dark"
        self.spark_canvas.configure(bg="#2b2b2b" if dark else "#dbdbdb")
        line = "#4d9de0" if dark else "#1f538d"
        self.spark_canvas.delete("all")
        w, h, pad = 250, 36, 5
        lo, hi = min(counts), max(counts)
        span = (hi - lo) or 1
        points = []
        for i, value in enumerate(counts):
            x = pad + i * (w - 2 * pad) / (len(counts) - 1)
            y = h - pad - (value - lo) * (h - 2 * pad) / span
            points.extend((x, y))
        self.spark_canvas.create_line(*points, fill=line, width=2)
        x, y = points[-2], points[-1]
        self.spark_canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=line, outline="")
        self.spark_canvas.pack(fill="x", padx=20, pady=(6, 0))

    # ---------------------------------------------------- Kontextmenü

    def _show_context_menu(self, event):
        if self._busy:
            return
        row = self.tree.identify_row(event.y)
        if row and row not in self.tree.selection():
            self.tree.selection_set(row)
        selection = list(self.tree.selection())
        if not selection:
            return

        to_unfollow = [u for u in selection if u in self.following]
        to_follow = [u for u in selection if u not in self.following]
        unprotected = [u for u in selection if u not in self.whitelist]
        protected = [u for u in selection if u in self.whitelist]

        menu = Menu(self, tearoff=0)
        menu.add_command(
            label="Profil im Browser öffnen"
            if len(selection) == 1
            else f"{min(len(selection), 5)} Profile im Browser öffnen",
            command=lambda: self._open_profiles(selection),
        )
        if (to_follow and self.client) or to_unfollow:
            menu.add_separator()
        if to_follow and self.client:
            menu.add_command(
                label=f"➕ Folgen ({len(to_follow)})",
                command=lambda: self._start_follow(to_follow),
            )
        if to_unfollow:
            menu.add_command(
                label=f"🚫 Entfolgen ({len(to_unfollow)})",
                command=lambda: self._confirm_and_unfollow(
                    to_unfollow, self._selection_question(to_unfollow)
                ),
            )
        menu.add_separator()
        if unprotected:
            menu.add_command(
                label=f"🛡 Schützen ({len(unprotected)})",
                command=lambda: self._set_protected(unprotected, True),
            )
        if protected:
            menu.add_command(
                label=f"Schutz aufheben ({len(protected)})",
                command=lambda: self._set_protected(protected, False),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_double_click(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self._open_profiles([row])

    @staticmethod
    def _open_profiles(users):
        for user in users[:5]:
            webbrowser.open(f"https://github.com/{user}")

    # ------------------------------------------------------- Interaktion

    def _detect_ui_scale(self) -> float:
        """Ermittelt die Display-Skalierung (Xft-DPI, GDK_SCALE, GNOME-Textskalierung)."""
        scale = 1.0
        try:
            scale = max(scale, self.winfo_fpixels("1i") / 96.0)
        except Exception:
            pass
        try:
            scale = max(scale, float(os.environ.get("GDK_SCALE", "1")))
        except ValueError:
            pass
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "text-scaling-factor"],
                capture_output=True, text=True, timeout=2,
            )
            scale = max(scale, float(result.stdout.strip()))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        return min(ZOOM_STEPS, key=lambda step: abs(step - scale))

    def _toggle_token_visibility(self):
        self.token_entry.configure(show="" if self.show_token.get() else "•")

    def _change_appearance(self, mode):
        ctk.set_appearance_mode(mode)
        self._style_treeview()
        self.settings["appearance"] = mode
        _save_settings(self.settings)

    def _apply_minsize(self):
        # CTk multipliziert minsize mit der Window-Skalierung – zurückrechnen,
        # damit die physische Mindestgröße auf kleinen Displays nutzbar bleibt
        self.minsize(int(940 / self.ui_scale), int(560 / self.ui_scale))

    def _change_zoom(self, choice):
        self.ui_scale = int(choice.rstrip(" %")) / 100
        ctk.set_widget_scaling(self.ui_scale)
        ctk.set_window_scaling(self.ui_scale)
        self._apply_minsize()
        self._style_treeview()
        self.settings["zoom"] = self.ui_scale
        _save_settings(self.settings)

    def _ui(self, fn, *args, **kwargs):
        """Führt einen UI-Update-Aufruf threadsicher im Mainloop aus."""
        self.after(0, lambda: fn(*args, **kwargs))

    def _set_busy(self, busy, status=None, mode="indeterminate"):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.analyze_button.configure(state=state)
        self.export_button.configure(state=state)
        if busy:
            self.progress.configure(mode=mode)
            if mode == "indeterminate":
                self.progress.start()
            else:
                self.progress.stop()
                self.progress.set(0)
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress.set(0)
        self._update_unfollow_buttons()
        if status is not None:
            self.status_label.configure(text=status)

    def _fail(self, message):
        self._set_busy(False, message)
        messagebox.showerror("Fehler", message)

    def _show_rate_limit_message(self, err: RateLimitError):
        if err.reset_time:
            text = (
                "Das GitHub-API-Limit ist erreicht.\n\n"
                f"Neue Anfragen sind ab {err.reset_time:%H:%M} Uhr möglich."
            )
        else:
            text = (
                "Das GitHub-API-Limit ist erreicht.\n\n"
                "Bitte warte einige Minuten und versuche es erneut."
            )
        messagebox.showwarning("GitHub-Rate-Limit", text)

    def _handle_rate_limit(self, err: RateLimitError):
        self._set_busy(False, "GitHub-Rate-Limit erreicht – bitte später erneut versuchen.")
        self._show_rate_limit_message(err)

    # ----------------------------------------------------------- Analyse

    def start_analysis(self):
        username = self.username_entry.get().strip()
        token = self.token_entry.get().strip()
        if not username or not token:
            messagebox.showerror(
                "Eingabe fehlt", "Bitte gib Username und Token ein."
            )
            return
        self._pending_token = token
        self._set_busy(True, "Validiere Zugangsdaten…")
        threading.Thread(
            target=self._analysis_worker, args=(username, token), daemon=True
        ).start()

    def _analysis_worker(self, username, token):
        try:
            client = GitHubClient(username, token)
            client.validate_credentials()

            self._ui(self.status_label.configure, text="Lade Follower…")
            followers = client.fetch_all_users(
                f"users/{username}/followers",
                on_page=lambda p: self._ui(
                    self.status_label.configure, text=f"Lade Follower… (Seite {p})"
                ),
            )

            self._ui(self.status_label.configure, text="Lade Following…")
            following = client.fetch_all_users(
                f"users/{username}/following",
                on_page=lambda p: self._ui(
                    self.status_label.configure, text=f"Lade Following… (Seite {p})"
                ),
            )

            self.client = client
            self._ui(self._apply_results, followers, following)

        except RateLimitError as err:
            self._ui(self._handle_rate_limit, err)
        except AuthError:
            self._ui(
                self._fail,
                "Token ungültig oder abgelaufen. Prüfe auch den Scope „user:follow“.",
            )
        except requests.HTTPError as err:
            code = err.response.status_code if err.response is not None else "?"
            hint = " Existiert der Username?" if code == 404 else ""
            self._ui(self._fail, f"GitHub-API-Fehler (HTTP {code}).{hint}")
        except requests.RequestException:
            self._ui(
                self._fail,
                "Keine Verbindung zur GitHub-API. Prüfe deine Internetverbindung.",
            )

    def _rebuild_changes_rows(self, entries):
        """Baut den Verlauf-Tab aus den gespeicherten Analyse-Ständen.

        Pro Nutzer bleibt das jeweils letzte Ereignis stehen (eindeutige
        Zeilen-IDs), sortiert wird über den ISO-Zeitstempel in "sort".
        """
        events = {}
        for prev, curr in zip(entries[:-1], entries[1:]):
            stamp = str(curr.get("timestamp", ""))
            try:
                when = datetime.fromisoformat(stamp).strftime("%d.%m.%Y")
            except ValueError:
                when = "unbekannt"
            gained, lost = compute_follower_delta(
                set(prev.get("followers", [])), set(curr.get("followers", []))
            )
            for user in gained:
                events[user] = (stamp, f"+ folgt dir seit {when}")
            for user in lost:
                events[user] = (stamp, f"− entfolgte dich am {when}")
        self.rows["changes"] = [
            {
                "user": user,
                "follows_you": user in self.followers,
                "you_follow": user in self.following,
                "status": text,
                "sort": stamp,
            }
            for user, (stamp, text) in events.items()
        ]

    def _update_history(self):
        """Speichert den Analyse-Stand und liefert den Vergleichstext."""
        history = _load_history()
        entries = _normalize_history_entries(history.get(self.client.username))
        entries.append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "followers": sorted(self.followers),
            "following": sorted(self.following),
        })
        entries = entries[-HISTORY_LIMIT:]
        history[self.client.username] = entries
        _save_history(history)

        self._spark_counts = [len(e.get("followers", [])) for e in entries]
        self._draw_sparkline()
        self._rebuild_changes_rows(entries)

        if len(entries) < 2:
            return (
                "Erste Analyse gespeichert – Veränderungen "
                "siehst du beim nächsten Lauf."
            )
        previous = entries[-2]
        gained, lost = compute_follower_delta(
            set(previous.get("followers", [])), self.followers
        )
        try:
            when = datetime.fromisoformat(previous["timestamp"]).strftime(
                "%d.%m.%Y, %H:%M"
            )
        except (KeyError, ValueError):
            when = "letzter Analyse"
        if not gained and not lost:
            return f"Keine Follower-Veränderung seit {when}."

        def fmt(users):
            names = ", ".join(users[:5])
            if len(users) > 5:
                names += f" … (+{len(users) - 5})"
            return names

        lines = [f"Seit {when}:"]
        if gained:
            lines.append(f"+{len(gained)} Follower: {fmt(gained)}")
        if lost:
            lines.append(f"−{len(lost)} Follower: {fmt(lost)}")
        return "\n".join(lines)

    def _apply_results(self, followers, following):
        self.followers = followers
        self.following = following
        self._rebuild_rows()
        self._hide_undo_button()
        self._profile_cache.clear()
        self.unfollow_candidates = self._compute_candidates()
        self._update_stats()
        if self.client:
            self.delta_label.configure(text=self._update_history())
            self._update_rate_label()
            if self._pending_token:
                self._persist_credentials(self.client.username, self._pending_token)
                self._pending_token = None

        self.segment.set(TAB_LABELS["unfollower"])
        self.current_tab = "unfollower"
        self._populate_tree()

        n = len(self.unfollow_candidates)
        if n:
            status = f"Analyse abgeschlossen: {n} Nutzer folgen dir nicht zurück."
        else:
            status = "Analyse abgeschlossen: Alle folgen dir zurück. 🎉"
        self._set_busy(False, status)

    # --------------------------------------------------------- Entfolgen

    def confirm_unfollow(self):
        users = list(self.unfollow_candidates)
        if len(users) == 1:
            question = f"Wirklich „{users[0]}“ entfolgen (folgt dir nicht zurück)?"
        else:
            question = (
                f"Wirklich allen {len(users)} Nutzern entfolgen, "
                "die dir nicht zurückfolgen?"
            )
        protected = [
            r["user"]
            for r in self.rows["unfollower"]
            if r["user"] in self.whitelist and r["status"] != "✓ Entfolgt"
        ]
        if protected:
            question += (
                f"\n\n🛡 {len(protected)} geschützte Nutzer werden übersprungen."
            )
        self._confirm_and_unfollow(users, question)

    @staticmethod
    def _selection_question(users):
        if len(users) == 1:
            return f"Wirklich „{users[0]}“ entfolgen?"
        shown = ", ".join(users[:8])
        if len(users) > 8:
            shown += f" … und {len(users) - 8} weitere"
        return f"Wirklich {len(users)} ausgewählten Nutzern entfolgen?\n\n{shown}"

    def confirm_unfollow_selection(self):
        users = self._selected_unfollowable()
        if not users:
            messagebox.showinfo(
                "Keine Auswahl",
                "Markiere in der Tabelle Nutzer, denen du aktuell folgst.",
            )
            return
        self._confirm_and_unfollow(users, self._selection_question(users))

    def _confirm_and_unfollow(self, users, question):
        if not users:
            messagebox.showinfo("Nichts zu tun", "Es gibt keine Nutzer zum Entfolgen.")
            return
        if not self.client:
            messagebox.showinfo("Keine Analyse", "Starte zuerst eine Analyse.")
            return
        if not messagebox.askyesno(
            "Entfolgen bestätigen",
            question + "\n\nDiese Aktion kann nicht rückgängig gemacht werden.",
        ):
            return
        self._set_busy(True, "Entfolge Nutzer…", mode="determinate")
        threading.Thread(
            target=self._unfollow_worker, args=(list(users),), daemon=True
        ).start()

    def _unfollow_worker(self, users):
        succeeded = []
        failed = 0
        total = len(users)
        rate_limited = None

        for idx, user in enumerate(users, 1):
            try:
                ok, status_text = self.client.unfollow(user)
            except RateLimitError as err:
                rate_limited = err
                for skipped in users[idx - 1:]:
                    self._ui(self._set_row_status, skipped, "Übersprungen (Rate-Limit)")
                break
            except requests.RequestException:
                ok, status_text = False, "Netzwerkfehler"

            if ok:
                succeeded.append(user)
                self._ui(self._mark_unfollowed, user)
            else:
                failed += 1

            self._ui(self._set_row_status, user, status_text)
            self._ui(self.progress.set, idx / total)
            self._ui(self.status_label.configure, text=f"Entfolge Nutzer… {idx}/{total}")
            time.sleep(ACTION_DELAY)

        self._ui(self._finish_unfollow, succeeded, failed, rate_limited)

    def _finish_unfollow(self, succeeded, failed, rate_limited):
        self.unfollow_candidates = self._compute_candidates()
        self._update_stats()
        self._update_rate_label()
        if succeeded:
            self.last_unfollowed = list(succeeded)
            self._show_undo_button()

        parts = [f"{len(succeeded)} entfolgt"]
        if failed:
            parts.append(f"{failed} fehlgeschlagen")
        self._set_busy(False, "Fertig: " + ", ".join(parts) + ".")

        if rate_limited:
            self._show_rate_limit_message(rate_limited)

    # ----------------------------------------------------------- Folgen

    def undo_unfollow(self):
        self._start_follow(list(self.last_unfollowed), is_undo=True)

    def _start_follow(self, users, is_undo=False):
        if not users or not self.client:
            return
        self._set_busy(True, "Folge Nutzern…", mode="determinate")
        threading.Thread(
            target=self._follow_worker, args=(list(users), is_undo), daemon=True
        ).start()

    def _follow_worker(self, users, is_undo):
        succeeded = []
        failed = 0
        total = len(users)
        rate_limited = None

        for idx, user in enumerate(users, 1):
            try:
                ok, status_text = self.client.follow(user)
            except RateLimitError as err:
                rate_limited = err
                for skipped in users[idx - 1:]:
                    self._ui(self._set_row_status, skipped, "Übersprungen (Rate-Limit)")
                break
            except requests.RequestException:
                ok, status_text = False, "Netzwerkfehler"

            if ok:
                succeeded.append(user)
                self._ui(self._mark_followed, user)
            else:
                failed += 1

            self._ui(self._set_row_status, user, status_text)
            self._ui(self.progress.set, idx / total)
            self._ui(self.status_label.configure, text=f"Folge Nutzern… {idx}/{total}")
            time.sleep(ACTION_DELAY)

        self._ui(self._finish_follow, succeeded, failed, rate_limited, is_undo)

    def _finish_follow(self, succeeded, failed, rate_limited, is_undo):
        if is_undo and succeeded:
            self._hide_undo_button()
        self.unfollow_candidates = self._compute_candidates()
        self._update_stats()
        self._update_rate_label()

        parts = [f"{len(succeeded)} gefolgt"]
        if failed:
            parts.append(f"{failed} fehlgeschlagen")
        self._set_busy(False, "Fertig: " + ", ".join(parts) + ".")

        if rate_limited:
            self._show_rate_limit_message(rate_limited)

    # ------------------------------------------------------------- Export

    def export_csv(self):
        rows = self._visible_rows()
        if not rows:
            messagebox.showinfo(
                "Keine Daten",
                "Starte zuerst eine Analyse – es gibt noch nichts zu exportieren.",
            )
            return

        default_name = f"github_{self.current_tab}_{datetime.now():%Y-%m-%d}.csv"
        path = filedialog.asksaveasfilename(
            title="Ergebnis als CSV speichern",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV-Datei", "*.csv"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["username", "folgt_dir", "du_folgst", "status"])
                for row in rows:
                    writer.writerow([
                        row["user"],
                        "ja" if row["follows_you"] else "nein",
                        "ja" if row["you_follow"] else "nein",
                        row["status"],
                    ])
        except OSError as err:
            messagebox.showerror(
                "Export fehlgeschlagen", f"Datei konnte nicht gespeichert werden: {err}"
            )
            return

        self.status_label.configure(text=f"CSV gespeichert: {path}")


def main():
    app = FollowerCheckerApp()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as err:  # freundliche Meldung statt Stacktrace beim Doppelklick-Start
        print("❌ Die Anwendung konnte nicht gestartet werden.")
        print(f"   {type(err).__name__}: {err}")
        print("   Tipp: pip install -r requirements.txt")
        input("\nDrücke Enter zum Beenden...")
        sys.exit(1)
