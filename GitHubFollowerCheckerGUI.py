#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub Follower Checker – GUI (CustomTkinter).

Analysiert Follower/Following über die GitHub REST API v3 und kann Nutzern
entfolgen, die nicht zurückfolgen. Alle API-Aufrufe laufen in einem
Hintergrund-Thread, damit die Oberfläche nicht einfriert. Das Token bleibt
ausschließlich im Arbeitsspeicher – es wird weder gespeichert noch geloggt.
"""

import csv
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk
from typing import Callable, Optional, Set


def _ensure_dependencies() -> None:
    """Installiert fehlende Pakete, damit der Doppelklick-Start funktioniert."""
    missing = []
    for package in ("customtkinter", "requests"):
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

BASE_URL = "https://api.github.com"

TABS = (
    ("unfollower", "Folgen nicht zurück"),
    ("followers", "Follower"),
    ("following", "Following"),
)
TAB_LABELS = dict(TABS)
LABEL_TO_KEY = {label: key for key, label in TABS}

COLUMNS = ("user", "follows_you", "you_follow", "status")
COLUMN_TITLES = {
    "user": "Username",
    "follows_you": "Folgt dir",
    "you_follow": "Du folgst",
    "status": "Status",
}

# Nur Darstellungs-Einstellungen (Zoom, Theme) – niemals Zugangsdaten!
SETTINGS_PATH = Path.home() / ".config" / "github-follower-checker" / "settings.json"

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
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        })

    @staticmethod
    def _raise_for_rate_limit(response: requests.Response) -> None:
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
        self.geometry("1100x680")
        self._apply_minsize()

        self.client: Optional[GitHubClient] = None
        self.followers: Set[str] = set()
        self.following: Set[str] = set()
        self.rows = {key: [] for key, _ in TABS}
        self.sort_state = {}
        self.unfollow_candidates = []
        self.current_tab = "unfollower"

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main()
        self._style_treeview()
        self._populate_tree()

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
        ).pack(anchor="w", padx=20, pady=(20, 2))
        ctk.CTkLabel(
            sidebar,
            text="GitHub-Beziehungen analysieren",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
        ).pack(anchor="w", padx=20)

        self._section_label(sidebar, "ZUGANGSDATEN", pady=(22, 6))

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

        self.analyze_button = ctk.CTkButton(
            sidebar,
            text="Analyse starten",
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.start_analysis,
        )
        self.analyze_button.pack(fill="x", padx=20, pady=(16, 0))

        self.progress = ctk.CTkProgressBar(sidebar, height=6)
        self.progress.pack(fill="x", padx=20, pady=(12, 0))
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
        self.status_label.pack(fill="x", padx=20, pady=(8, 0))

        self._section_label(sidebar, "ERGEBNIS", pady=(18, 6))

        stats_card = ctk.CTkFrame(sidebar, corner_radius=10)
        stats_card.pack(fill="x", padx=20)
        self.stat_values = {}
        stats = (
            ("followers", "Follower", None),
            ("following", "Following", None),
            ("unfollower", "Folgen nicht zurück", ("#c62828", "#ef5350")),
        )
        for i, (key, title, accent) in enumerate(stats):
            row = ctk.CTkFrame(stats_card, fg_color="transparent")
            row.pack(
                fill="x",
                padx=14,
                pady=(12 if i == 0 else 4, 12 if i == len(stats) - 1 else 4),
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

        ctk.CTkLabel(
            sidebar,
            text="MIT License · GitHub REST API v3",
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

        self.table_frame = ctk.CTkFrame(main, corner_radius=10)
        self.table_frame.grid(row=1, column=0, sticky="nsew")

        self.tree = ttk.Treeview(
            self.table_frame,
            columns=COLUMNS,
            show="headings",
            style="Checker.Treeview",
            selectmode="browse",
        )
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

        bottom_bar = ctk.CTkFrame(main, fg_color="transparent")
        bottom_bar.grid(row=2, column=0, sticky="ew", pady=(12, 0))

        ctk.CTkLabel(
            bottom_bar,
            text="Tipp: Klick auf eine Spaltenüberschrift sortiert die Tabelle.",
            font=ctk.CTkFont(size=11),
            text_color=("gray45", "gray55"),
        ).pack(side="left")

        self.unfollow_button = ctk.CTkButton(
            bottom_bar,
            text="🚫 Entfolgen",
            width=170,
            height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=("#c62828", "#b3261e"),
            hover_color=("#a91f1f", "#8c1d18"),
            state="disabled",
            command=self.confirm_unfollow,
        )
        self.unfollow_button.pack(side="right")

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
        return (row["status"], row["user"].lower())

    def _populate_tree(self):
        self.tree.delete(*self.tree.get_children())

        col, reverse = self.sort_state.get(self.current_tab, ("user", False))
        rows = sorted(
            self.rows[self.current_tab],
            key=lambda r: self._sort_key(r, col),
            reverse=reverse,
        )
        for index, row in enumerate(rows):
            self.tree.insert(
                "",
                "end",
                iid=row["user"],
                tags=("odd",) if index % 2 else (),
                values=(
                    row["user"],
                    "✓" if row["follows_you"] else "–",
                    "✓" if row["you_follow"] else "–",
                    row["status"],
                ),
            )

        for c in COLUMNS:
            arrow = ("  ↓" if reverse else "  ↑") if c == col else ""
            self.tree.heading(
                c,
                text=COLUMN_TITLES[c] + arrow,
                anchor="center" if c in ("follows_you", "you_follow") else "w",
                command=lambda c=c: self._sort_by(c),
            )

        display = COLUMNS if self.current_tab == "unfollower" else COLUMNS[:3]
        self.tree.configure(displaycolumns=display)

        if rows:
            self.empty_label.place_forget()
        else:
            self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

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

    def _set_row_status(self, user, text):
        for rows in self.rows.values():
            for row in rows:
                if row["user"] == user:
                    row["status"] = text
        if self.tree.exists(user):
            self.tree.set(user, "status", text)

    def _update_stats(self):
        self.stat_values["followers"].configure(text=str(len(self.followers)))
        self.stat_values["following"].configure(text=str(len(self.following)))
        self.stat_values["unfollower"].configure(
            text=str(len(self.following - self.followers))
        )

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
        state = "disabled" if busy else "normal"
        self.analyze_button.configure(state=state)
        self.export_button.configure(state=state)
        if busy:
            self.unfollow_button.configure(state="disabled")
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
            self.unfollow_button.configure(
                state="normal" if self.unfollow_candidates else "disabled"
            )
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

    def _apply_results(self, followers, following):
        self.followers = followers
        self.following = following
        self._rebuild_rows()
        self.unfollow_candidates = [r["user"] for r in self.rows["unfollower"]]
        self._update_stats()

        self.segment.set(TAB_LABELS["unfollower"])
        self.current_tab = "unfollower"
        self._populate_tree()

        n = len(self.unfollow_candidates)
        if n:
            status = f"Analyse abgeschlossen: {n} Nutzer folgen dir nicht zurück."
            self.unfollow_button.configure(text=f"🚫 Entfolgen ({n})")
        else:
            status = "Analyse abgeschlossen: Alle folgen dir zurück. 🎉"
            self.unfollow_button.configure(text="🚫 Entfolgen")
        self._set_busy(False, status)

    # --------------------------------------------------------- Entfolgen

    def confirm_unfollow(self):
        n = len(self.unfollow_candidates)
        if not n:
            messagebox.showinfo("Nichts zu tun", "Es gibt keine Nutzer zum Entfolgen.")
            return
        if not messagebox.askyesno(
            "Entfolgen bestätigen",
            f"Wirklich {n} Nutzern entfolgen?\n\n"
            "Diese Aktion kann nicht rückgängig gemacht werden.",
        ):
            return
        self._set_busy(True, "Entfolge Nutzer…", mode="determinate")
        threading.Thread(
            target=self._unfollow_worker,
            args=(list(self.unfollow_candidates),),
            daemon=True,
        ).start()

    def _unfollow_worker(self, users):
        success = failed = 0
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
                success += 1
                self.following.discard(user)
            else:
                failed += 1

            self._ui(self._set_row_status, user, status_text)
            self._ui(self.progress.set, idx / total)
            self._ui(self.status_label.configure, text=f"Entfolge Nutzer… {idx}/{total}")
            time.sleep(1)

        self._ui(self._finish_unfollow, success, failed, rate_limited)

    def _finish_unfollow(self, success, failed, rate_limited):
        self.unfollow_candidates = [
            r["user"] for r in self.rows["unfollower"] if r["status"] != "✓ Entfolgt"
        ]
        self._update_stats()

        parts = [f"{success} entfolgt"]
        if failed:
            parts.append(f"{failed} fehlgeschlagen")
        self._set_busy(False, "Fertig: " + ", ".join(parts) + ".")

        n = len(self.unfollow_candidates)
        self.unfollow_button.configure(
            text=f"🚫 Entfolgen ({n})" if n else "🚫 Entfolgen"
        )
        if rate_limited:
            self._show_rate_limit_message(rate_limited)

    # ------------------------------------------------------------- Export

    def export_csv(self):
        rows = self.rows[self.current_tab]
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
