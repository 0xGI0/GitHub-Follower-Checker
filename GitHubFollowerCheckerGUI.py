#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub Follower Checker – GUI (Flet, GitHub-Look).

Analysiert Follower/Following über die GitHub REST API v3 und kann Nutzern
entfolgen – allen, die nicht zurückfolgen, oder gezielt ausgewählten
Nutzern – sowie Nutzern (zurück)folgen. Dazu: Fans-Ansicht, Filter,
Whitelist geschützter Nutzer, Zeilen-Aktionsmenü, Rückgängig-Funktion und
ein lokaler Verlauf, der Follower-Veränderungen zwischen zwei Analysen
anzeigt. Alle API-Aufrufe laufen in Hintergrund-Threads, damit die
Oberfläche nicht einfriert. Das Token bleibt ausschließlich im
Arbeitsspeicher – es wird weder gespeichert noch geloggt.
"""

import subprocess
import sys


def _ensure_dependencies() -> None:
    """Installiert fehlende Pakete, damit der Doppelklick-Start funktioniert."""
    missing = []
    for import_name, pip_name in (
        ("flet", "flet>=0.86,<0.87"),
        ("requests", "requests"),
        ("keyring", "keyring"),
    ):
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_name)
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

import csv  # noqa: E402
import threading  # noqa: E402
import webbrowser  # noqa: E402
from datetime import datetime  # noqa: E402
from typing import Optional, Set  # noqa: E402

import flet as ft  # noqa: E402
import flet.canvas as fcv  # noqa: E402

try:
    import keyring  # noqa: E402
except Exception:  # keyring ist optional – ohne Backend einfach deaktivieren
    keyring = None  # type: ignore[assignment]

from gfc_core import (  # noqa: E402
    KEYRING_SERVICE,
    __version__,
    _detect_language,
    _load_settings,
    _save_settings,
    set_language,
    tr,
)
from gfc_controller import AppController, UiCallbacks  # noqa: E402


def _tabs():
    return (
        ("unfollower", tr("Folgen nicht zurück")),
        ("fans", tr("Fans")),
        ("followers", tr("Follower")),
        ("following", tr("Following")),
        ("changes", tr("Verlauf")),
    )


def _column_titles():
    return {
        "user": "Username",
        "follows_you": tr("Folgt dir"),
        "you_follow": tr("Du folgst"),
        "status": "Status",
    }


ZOOM_STEPS = (1.0, 1.25, 1.5, 1.75, 2.0)

# GitHub-Farbwelt (an Primer/github.com angelehnt)
PALETTE = {
    "dark": {
        "bg": "#0d1117",
        "card": "#161b22",
        "border": "#30363d",
        "text": "#e6edf3",
        "muted": "#8b949e",
        "green": "#3fb950",
        "green_btn": "#238636",
        "green_soft": "#12261e",
        "red": "#f85149",
        "red_btn": "#da3633",
        "red_soft": "#2d1417",
        "blue": "#58a6ff",
        "hover": "#1f242c",
        "selected": "#121d2f",
    },
    "light": {
        "bg": "#ffffff",
        "card": "#f6f8fa",
        "border": "#d0d7de",
        "text": "#1f2328",
        "muted": "#59636e",
        "green": "#1a7f37",
        "green_btn": "#1f883d",
        "green_soft": "#dafbe1",
        "red": "#cf222e",
        "red_btn": "#cf222e",
        "red_soft": "#ffebe9",
        "blue": "#0969da",
        "hover": "#eaeef2",
        "selected": "#ddf4ff",
    },
}


class FollowerCheckerView(UiCallbacks):
    """Baut die Flet-Oberfläche und reagiert auf Controller-Ereignisse."""

    def __init__(self, page: Optional[ft.Page] = None, settings: Optional[dict] = None):
        self.page = page
        self.settings = settings if settings is not None else _load_settings()
        self.scale = float(self.settings.get("zoom") or 1.0)
        self.mode = self._resolve_mode(self.settings.get("appearance", "Dark"))
        self.c = PALETTE[self.mode]
        self.controller = AppController(ui=self, settings=self.settings)
        self.current_tab = "unfollower"
        self.selection: Set[str] = set()
        self.filter_term = ""
        self._row_refs: dict = {}
        self._profile_cache: dict = {}
        self._detail_timer: Optional[threading.Timer] = None
        self._last_delta = ""
        self.file_picker = None
        self._build_controls()

    # ------------------------------------------------------------ Helfer

    def s(self, value: float) -> int:
        """Skaliert einen Basis-Pixelwert mit der Zoomstufe."""
        return round(value * self.scale)

    def _resolve_mode(self, appearance: str) -> str:
        if appearance == "Light":
            return "light"
        if appearance == "System" and self.page is not None:
            try:
                dark = self.page.platform_brightness == ft.Brightness.DARK
                return "dark" if dark else "light"
            except Exception:
                return "dark"
        return "dark"

    def _update(self):
        if self.page is not None:
            self.page.update()

    def _card(self, content, padding: int = 14) -> ft.Container:
        return ft.Container(
            content=content,
            bgcolor=self.c["card"],
            border=ft.Border.all(1, self.c["border"]),
            border_radius=self.s(8),
            padding=self.s(padding),
        )

    def _section_label(self, text: str) -> ft.Text:
        return ft.Text(
            text, size=self.s(11), weight=ft.FontWeight.BOLD, color=self.c["muted"]
        )

    def _field(self, hint: str, password: bool = False) -> ft.TextField:
        return ft.TextField(
            hint_text=hint,
            password=password,
            can_reveal_password=password,  # Auge-Symbol ersetzt „Token anzeigen“
            height=self.s(38),
            text_size=self.s(13),
            dense=True,
            filled=True,
            fill_color=self.c["card"],
            border_color=self.c["border"],
            focused_border_color=self.c["blue"],
            border_radius=self.s(6),
            on_submit=self.on_analyze,
        )

    def _footer_dropdown(self, values, current, on_select) -> ft.Dropdown:
        return ft.Dropdown(
            options=[ft.DropdownOption(key=v, text=v) for v in values],
            value=current,
            expand=True,
            dense=True,
            text_size=self.s(12),
            content_padding=ft.Padding.symmetric(
                horizontal=self.s(8), vertical=self.s(4)
            ),
            border_color=self.c["border"],
            on_select=on_select,
        )

    # ------------------------------------------------------------- Aufbau

    def _build_controls(self):
        sidebar = self.build_sidebar()
        main = self.build_main()
        self.root = ft.Row(
            [sidebar, main],
            spacing=0,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    def build_sidebar(self) -> ft.Container:
        s = self.s
        self.username_field = self._field("GitHub-Username")
        self.token_field = self._field("Personal Access Token", password=True)
        self.remember_box = ft.Checkbox(
            label=tr("Token merken (Schlüsselbund)"),
            value=bool(self.settings.get("remember_token")),
            visible=keyring is not None,
            on_change=self.on_remember_toggle,
        )
        self.analyze_button = ft.FilledButton(
            content=ft.Text(
                tr("Analyse starten"), size=s(13), weight=ft.FontWeight.BOLD
            ),
            height=s(38),
            style=ft.ButtonStyle(
                bgcolor=self.c["green_btn"],
                color="#ffffff",
                shape=ft.RoundedRectangleBorder(radius=s(6)),
            ),
            on_click=self.on_analyze,
        )
        self.progress_bar = ft.ProgressBar(
            value=0, bar_height=s(4), color=self.c["blue"], bgcolor=self.c["border"]
        )
        self.status_text = ft.Text(
            tr("Bereit. Gib Username und Token ein."), size=s(12), color=self.c["muted"]
        )

        self.stat_values = {}
        stat_defs = (
            ("followers", tr("Follower"), self.c["text"]),
            ("following", tr("Following"), self.c["text"]),
            ("fans", tr("Fans"), self.c["green"]),
            ("unfollower", tr("Folgen nicht zurück"), self.c["red"]),
        )
        stat_cards = []
        for key, title, color in stat_defs:
            value = ft.Text("–", size=s(22), weight=ft.FontWeight.BOLD, color=color)
            self.stat_values[key] = value
            stat_cards.append(
                ft.Container(
                    content=ft.Column(
                        [value, ft.Text(title, size=s(11), color=self.c["muted"])],
                        spacing=s(2),
                    ),
                    bgcolor=self.c["card"],
                    border=ft.Border.all(1, self.c["border"]),
                    border_radius=s(8),
                    padding=s(12),
                    expand=True,
                )
            )
        stats_grid = ft.Column(
            [ft.Row(stat_cards[:2], spacing=s(8)), ft.Row(stat_cards[2:], spacing=s(8))],
            spacing=s(8),
        )

        self.delta_text = ft.Text(
            tr("Noch kein Vergleich vorhanden."), size=s(11), color=self.c["muted"]
        )
        # Follower-Verlauf als Mini-Diagramm (erscheint ab zwei Analysen)
        self.spark_canvas = fcv.Canvas(
            shapes=[], width=s(250), height=s(36), visible=False
        )

        self.theme_menu = self._footer_dropdown(
            ["Dark", "Light", "System"],
            self.settings.get("appearance", "Dark"),
            self.on_appearance,
        )
        self.zoom_menu = self._footer_dropdown(
            [f"{int(step * 100)} %" for step in ZOOM_STEPS],
            f"{int(self.scale * 100)} %",
            self.on_zoom,
        )
        lang = str(self.settings.get("language", "auto")).lower()
        self.language_menu = self._footer_dropdown(
            ["Auto", "DE", "EN"],
            {"de": "DE", "en": "EN"}.get(lang, "Auto"),
            self.on_language,
        )
        self.rate_text = ft.Text("", size=s(10), color=self.c["muted"])

        return ft.Container(
            width=s(350),
            bgcolor=self.c["bg"],
            border=ft.Border.only(right=ft.BorderSide(1, self.c["border"])),
            padding=ft.Padding.symmetric(horizontal=s(16), vertical=s(14)),
            content=ft.Column(
                [
                    ft.Text(
                        "🐙 Follower Checker",
                        size=s(20),
                        weight=ft.FontWeight.BOLD,
                        color=self.c["text"],
                    ),
                    ft.Text(
                        tr("GitHub-Beziehungen analysieren"),
                        size=s(12),
                        color=self.c["muted"],
                    ),
                    ft.Container(height=s(8)),
                    self._section_label(tr("ZUGANGSDATEN")),
                    self.username_field,
                    self.token_field,
                    self.remember_box,
                    self.analyze_button,
                    self.progress_bar,
                    self.status_text,
                    ft.Container(height=s(6)),
                    self._section_label(tr("ERGEBNIS")),
                    stats_grid,
                    ft.Container(height=s(6)),
                    self._section_label(tr("SEIT LETZTER ANALYSE")),
                    self.delta_text,
                    self.spark_canvas,
                    ft.Column(
                        [
                            ft.Row(
                                [self.theme_menu, self.zoom_menu, self.language_menu],
                                spacing=s(6),
                            ),
                            self.rate_text,
                            ft.Text(
                                f"v{__version__} · MIT License · GitHub REST API v3",
                                size=s(10),
                                color=self.c["muted"],
                            ),
                        ],
                        spacing=s(4),
                        expand=True,
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=s(8),
                expand=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

    def build_main(self) -> ft.Container:
        s = self.s
        self.tab_buttons = {}
        self.tab_labels = {}
        pills = []
        for key, label in _tabs():
            text = ft.Text(label, size=s(12), color=self.c["muted"])
            pill = ft.Container(
                content=text,
                padding=ft.Padding.symmetric(horizontal=s(12), vertical=s(6)),
                border_radius=s(15),
                ink=True,
                on_click=lambda e, k=key: self.on_tab(k),
            )
            self.tab_labels[key] = text
            self.tab_buttons[key] = pill
            pills.append(pill)

        self.search_field = ft.TextField(
            hint_text=tr("Nutzer filtern…"),
            prefix_icon=ft.Icons.SEARCH,
            width=s(200),
            height=s(34),
            text_size=s(12),
            dense=True,
            filled=True,
            fill_color=self.c["card"],
            border_color=self.c["border"],
            focused_border_color=self.c["blue"],
            border_radius=s(6),
            on_change=self.on_search,
        )
        self.export_button = ft.OutlinedButton(
            content=ft.Text(tr("⬇  CSV exportieren"), size=s(12), color=self.c["text"]),
            style=ft.ButtonStyle(
                side=ft.BorderSide(1, self.c["border"]),
                shape=ft.RoundedRectangleBorder(radius=s(6)),
            ),
            on_click=self.on_export,
        )

        self.header_box = ft.Container(content=self._build_list_header())
        self.user_list = ft.ListView(controls=[], spacing=0, expand=True)
        self.empty_text = ft.Text(
            tr("Noch keine Daten.\nStarte links eine Analyse."),
            size=s(14),
            color=self.c["muted"],
            text_align=ft.TextAlign.CENTER,
        )
        self.empty_box = ft.Container(
            content=self.empty_text, alignment=ft.Alignment(0, 0), expand=True
        )
        table = ft.Container(
            expand=True,
            bgcolor=self.c["card"],
            border=ft.Border.all(1, self.c["border"]),
            border_radius=s(8),
            content=ft.Column(
                [
                    self.header_box,
                    ft.Container(
                        expand=True,
                        content=ft.Stack([self.user_list, self.empty_box]),
                    ),
                ],
                spacing=0,
                expand=True,
            ),
        )

        # Profil-Panel: erscheint, wenn genau ein Nutzer ausgewählt ist
        self.detail_avatar = ft.Image(
            src="", width=s(40), height=s(40), border_radius=s(20), visible=False
        )
        self.detail_text = ft.Text("", size=s(12), color=self.c["text"])
        self.detail_card = ft.Container(
            visible=False,
            bgcolor=self.c["card"],
            border=ft.Border.all(1, self.c["border"]),
            border_radius=s(8),
            padding=s(12),
            content=ft.Row(
                [self.detail_avatar, self.detail_text],
                spacing=s(10),
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        self.tip_text = ft.Text(
            tr("Tipp: Checkboxen wählen mehrere Nutzer aus, ⋯ öffnet Aktionen."),
            size=s(11),
            color=self.c["muted"],
        )
        self.undo_label = ft.Text(tr("↩ Rückgängig"), size=s(13), color=self.c["text"])
        self.undo_button = ft.OutlinedButton(
            content=self.undo_label,
            visible=False,
            style=ft.ButtonStyle(
                side=ft.BorderSide(1, self.c["border"]),
                shape=ft.RoundedRectangleBorder(radius=s(6)),
            ),
            on_click=lambda e: self.controller.undo_unfollow(),
        )
        self.unfollow_sel_label = ft.Text(
            tr("Auswahl entfolgen"), size=s(13), color=self.c["red"]
        )
        self.unfollow_sel_button = ft.OutlinedButton(
            content=self.unfollow_sel_label,
            disabled=True,
            style=ft.ButtonStyle(
                side=ft.BorderSide(1, self.c["red_btn"]),
                shape=ft.RoundedRectangleBorder(radius=s(6)),
            ),
            on_click=self.on_unfollow_selection,
        )
        self.unfollow_all_label = ft.Text(
            tr("🚫 Alle Nicht-Folgenden"),
            size=s(13),
            weight=ft.FontWeight.BOLD,
            color="#ffffff",
        )
        self.unfollow_all_button = ft.FilledButton(
            content=self.unfollow_all_label,
            disabled=True,
            style=ft.ButtonStyle(
                bgcolor=self.c["red_btn"],
                shape=ft.RoundedRectangleBorder(radius=s(6)),
            ),
            on_click=self.on_unfollow_all,
        )
        self.bottom_bar = ft.Row(
            [
                ft.Container(content=self.tip_text, expand=True),
                self.undo_button,
                self.unfollow_sel_button,
                self.unfollow_all_button,
            ],
            spacing=s(8),
        )

        return ft.Container(
            expand=True,
            bgcolor=self.c["bg"],
            padding=s(20),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Row(pills, spacing=s(4), expand=True),
                            self.search_field,
                            self.export_button,
                        ],
                        spacing=s(8),
                    ),
                    table,
                    self.detail_card,
                    self.bottom_bar,
                ],
                spacing=s(12),
                expand=True,
            ),
        )

    def _build_list_header(self) -> ft.Container:
        s = self.s
        col, reverse = self.controller.sort_state.get(self.current_tab, ("user", False))

        def head(col_key, width=None, expand=False, center=False):
            arrow = ("  ↓" if reverse else "  ↑") if col_key == col else ""
            label = ft.Text(
                _column_titles()[col_key] + arrow,
                size=s(11),
                weight=ft.FontWeight.BOLD,
                color=self.c["muted"],
            )
            return ft.Container(
                content=label,
                width=width,
                expand=expand,
                alignment=ft.Alignment(0, 0) if center else None,
                ink=True,
                on_click=lambda e, k=col_key: self.on_sort(k),
            )

        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(width=s(36)),  # Checkbox-Spalte
                    ft.Container(width=s(28)),  # Avatar-Spalte
                    head("user", expand=True),
                    head("follows_you", width=s(100), center=True),
                    head("you_follow", width=s(100), center=True),
                    head("status", width=s(170)),
                    ft.Container(width=s(40)),  # ⋯-Spalte
                ],
                spacing=s(8),
            ),
            padding=ft.Padding.symmetric(horizontal=s(10), vertical=s(8)),
            bgcolor=self.c["card"],
            border=ft.Border.only(bottom=ft.BorderSide(1, self.c["border"])),
            border_radius=ft.BorderRadius.only(top_left=s(8), top_right=s(8)),
        )

    def _row_menu(self, user) -> ft.Control:
        return ft.PopupMenuButton(
            icon=ft.Icons.MORE_HORIZ,
            icon_color=self.c["muted"],
            items=[
                ft.PopupMenuItem(
                    content=ft.Text(tr("Profil im Browser öffnen")),
                    on_click=lambda e, u=user: self.on_open_profiles(
                        self._menu_targets(u)
                    ),
                ),
                ft.PopupMenuItem(
                    content=ft.Text(tr("Folgen")),
                    on_click=lambda e, u=user: self.on_menu_follow(u),
                ),
                ft.PopupMenuItem(
                    content=ft.Text(tr("Entfolgen")),
                    on_click=lambda e, u=user: self.on_menu_unfollow(u),
                ),
                ft.PopupMenuItem(
                    content=ft.Text(tr("🛡 Schützen / Schutz aufheben")),
                    on_click=lambda e, u=user: self.on_menu_protect(u),
                ),
            ],
        )

    def _build_row(self, row: dict) -> ft.Container:
        s = self.s
        user = row["user"]
        selected = user in self.selection
        shield = "🛡 " if user in self.controller.whitelist else ""
        checkbox = ft.Checkbox(
            value=selected,
            on_change=lambda e, u=user: self.on_select_row(u, e.control.value),
        )
        avatar = ft.Image(
            src=f"https://github.com/{user}.png?size=64",
            width=s(28),
            height=s(28),
            border_radius=s(14),
            fit=ft.BoxFit.COVER,
            error_content=ft.Icon(
                ft.Icons.PERSON, size=s(18), color=self.c["muted"]
            ),
        )
        name = ft.Text(
            shield + user, size=s(13), color=self.c["text"], weight=ft.FontWeight.W_500
        )
        follows_cell = ft.Container(
            content=self._check_mark(row["follows_you"]),
            width=s(100),
            alignment=ft.Alignment(0, 0),
        )
        you_follow_cell = ft.Container(
            content=self._check_mark(row["you_follow"]),
            width=s(100),
            alignment=ft.Alignment(0, 0),
        )
        status_text = ft.Text(row["status"], size=s(12), color=self.c["muted"])
        container = ft.Container(
            content=ft.Row(
                [
                    ft.Container(content=checkbox, width=s(36)),
                    avatar,
                    ft.Container(
                        content=name,
                        expand=True,
                        ink=True,
                        on_click=lambda e, u=user: self.on_open_profiles([u]),
                        tooltip=tr("Profil im Browser öffnen"),
                    ),
                    follows_cell,
                    you_follow_cell,
                    ft.Container(content=status_text, width=s(170)),
                    self._row_menu(user),
                ],
                spacing=s(8),
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=s(10), vertical=s(2)),
            bgcolor=self.c["selected"] if selected else None,
            border=ft.Border.only(bottom=ft.BorderSide(1, self.c["border"])),
        )
        self._row_refs[user] = {
            "container": container,
            "name": name,
            "status": status_text,
            "you_follow": you_follow_cell,
        }
        return container

    # ------------------------------------------------ Fenster & Lebenslauf

    def mount(self, page: ft.Page):
        self.page = page
        page.title = "GitHub Follower Checker"
        page.padding = 0
        page.bgcolor = self.c["bg"]
        page.theme_mode = (
            ft.ThemeMode.DARK if self.mode == "dark" else ft.ThemeMode.LIGHT
        )
        page.window.min_width = 940
        page.window.min_height = 560
        size = self.settings.get("window_size") or [1180, 740]
        try:
            page.window.width, page.window.height = int(size[0]), int(size[1])
        except (TypeError, ValueError, IndexError):
            page.window.width, page.window.height = 1180, 740
        page.window.prevent_close = True
        page.window.on_event = self.on_window_event
        self.file_picker = ft.FilePicker()
        page.services.append(self.file_picker)
        # „System“-Theme lässt sich erst mit bekannter Page auflösen
        if self.settings.get("appearance", "Dark") == "System":
            resolved = self._resolve_mode("System")
            if resolved != self.mode:
                self.mode = resolved
                self.c = PALETTE[self.mode]
                self._build_controls()
                page.theme_mode = (
                    ft.ThemeMode.DARK if self.mode == "dark" else ft.ThemeMode.LIGHT
                )
        page.add(self.root)
        self._prefill_credentials()
        page.update()

    async def on_window_event(self, e):
        if e.type == ft.WindowEventType.CLOSE:
            try:
                self.settings["window_size"] = [
                    int(self.page.window.width or 1180),
                    int(self.page.window.height or 740),
                ]
            except (TypeError, ValueError):
                pass
            self.settings["whitelist"] = sorted(self.controller.whitelist)
            _save_settings(self.settings)
            await self.page.window.destroy()

    def _rebuild(self):
        """Baut die Oberfläche nach Theme-/Zoomwechsel komplett neu auf."""
        keep_user = getattr(self, "username_field", None) and self.username_field.value
        keep_token = getattr(self, "token_field", None) and self.token_field.value
        keep_status = getattr(self, "status_text", None) and self.status_text.value
        self.c = PALETTE[self.mode]
        self._build_controls()
        if keep_user:
            self.username_field.value = keep_user
        if keep_token:
            self.token_field.value = keep_token
        if keep_status:
            self.status_text.value = keep_status
        if self._last_delta:
            self.delta_text.value = self._last_delta
        if self.page is not None:
            self.page.bgcolor = self.c["bg"]
            self.page.theme_mode = (
                ft.ThemeMode.DARK if self.mode == "dark" else ft.ThemeMode.LIGHT
            )
            self.page.controls.clear()
            self.page.add(self.root)
        self.refresh_all()

    # ------------------------------------------------------ Zugangsdaten

    def _prefill_credentials(self):
        """Füllt Username/Token aus Settings und Schlüsselbund vor."""
        if keyring is None or not self.settings.get("remember_token"):
            return
        last = self.settings.get("last_username")
        if not last:
            return
        self.username_field.value = last
        try:
            token = keyring.get_password(KEYRING_SERVICE, last)
        except Exception:
            token = None
        if token:
            self.token_field.value = token
            self.status_text.value = tr("Zugangsdaten aus dem Schlüsselbund geladen.")

    def on_remember_toggle(self, e=None):
        remember = bool(self.remember_box.value)
        self.settings["remember_token"] = remember
        if not remember and keyring is not None:
            last = self.settings.get("last_username")
            if last:
                try:
                    keyring.delete_password(KEYRING_SERVICE, last)
                except Exception:
                    pass
        _save_settings(self.settings)

    def persist_credentials(self, username, token):
        """Speichert Token im Schlüsselbund, wenn „Token merken“ aktiv ist."""
        self.settings["last_username"] = username
        if keyring is not None and self.remember_box.value:
            try:
                keyring.set_password(KEYRING_SERVICE, username, token)
            except Exception:
                pass
        _save_settings(self.settings)

    # ------------------------------------------------------- Interaktion

    def on_analyze(self, e=None):
        username = (self.username_field.value or "").strip()
        token = (self.token_field.value or "").strip()
        if not username or not token:
            self._alert(tr("Eingabe fehlt"), tr("Bitte gib Username und Token ein."))
            return
        self.controller.start_analysis(username, token)

    def on_appearance(self, e):
        choice = e.control.value
        self.settings["appearance"] = choice
        _save_settings(self.settings)
        self.mode = self._resolve_mode(choice)
        self._rebuild()

    def on_zoom(self, e):
        self.scale = int(str(e.control.value).rstrip(" %")) / 100
        self.settings["zoom"] = self.scale
        _save_settings(self.settings)
        self._rebuild()

    def on_language(self, e):
        self.settings["language"] = {"DE": "de", "EN": "en"}.get(e.control.value, "auto")
        _save_settings(self.settings)
        set_language(_detect_language(self.settings))
        self._rebuild()

    async def on_export(self, e=None):
        table = self.controller.csv_table(self.current_tab, self.filter_term)
        if len(table) <= 1:
            self._alert(
                tr("Keine Daten"),
                tr("Starte zuerst eine Analyse – es gibt noch nichts zu exportieren."),
            )
            return
        if self.file_picker is None:
            return
        default_name = f"github_{self.current_tab}_{datetime.now():%Y-%m-%d}.csv"
        path = await self.file_picker.save_file(
            dialog_title=tr("Ergebnis als CSV speichern"),
            file_name=default_name,
            allowed_extensions=["csv"],
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerows(table)
        except OSError as err:
            self._alert(
                tr("Export fehlgeschlagen"),
                tr("Datei konnte nicht gespeichert werden: {err}").format(err=err),
            )
            return
        self.status(tr("CSV gespeichert: {path}").format(path=path))

    # ------------------------------------------------------------ Dialoge

    def _alert(self, title, message):
        if self.page is None:
            return
        self.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(title),
                content=ft.Text(message),
                bgcolor=self.c["card"],
                actions=[
                    ft.TextButton(
                        content="OK", on_click=lambda e: self.page.pop_dialog()
                    )
                ],
            )
        )

    def _confirm(self, title, question, action_label, on_confirm):
        if self.page is None:
            return

        def confirmed(e):
            self.page.pop_dialog()
            on_confirm()

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=self.c["card"],
                title=ft.Text(title),
                content=ft.Text(question),
                actions=[
                    ft.TextButton(
                        content=tr("Abbrechen"),
                        on_click=lambda e: self.page.pop_dialog(),
                    ),
                    ft.FilledButton(
                        content=ft.Text(action_label, color="#ffffff"),
                        style=ft.ButtonStyle(bgcolor=self.c["red_btn"]),
                        on_click=confirmed,
                    ),
                ],
            )
        )

    # ------------------------------------------- Controller-Rückmeldungen

    def status(self, text):
        self.status_text.value = text
        self._update()

    def busy_changed(self, busy, determinate):
        self.analyze_button.disabled = busy
        self.export_button.disabled = busy
        if busy and not determinate:
            self.progress_bar.value = None  # None = unbestimmte Animation
        else:
            self.progress_bar.value = 0
        self.refresh_buttons()
        self._update()

    def progress(self, fraction):
        self.progress_bar.value = fraction
        self._update()

    def data_changed(self):
        self.refresh_stats()
        self.refresh_list()
        self.refresh_buttons()
        self.refresh_rate()
        self._update()

    def row_changed(self, user):
        refs = self._row_refs.get(user)
        if refs:
            row = next(
                (
                    r
                    for r in self.controller.rows[self.current_tab]
                    if r["user"] == user
                ),
                None,
            )
            if row is not None:
                refs["status"].value = row["status"]
                refs["you_follow"].content = self._check_mark(row["you_follow"])
        self.refresh_buttons()
        self._update()

    def analysis_finished(self):
        self.current_tab = "unfollower"
        self.selection.clear()
        self._profile_cache.clear()
        self.detail_card.visible = False
        self.refresh_tabs()
        self.refresh_sparkline()
        self.data_changed()

    def delta_changed(self, text):
        self._last_delta = text
        self.delta_text.value = text
        self._update()

    def undo_changed(self, count):
        self.refresh_buttons()
        self._update()

    def error(self, message):
        self._alert(tr("Fehler"), message)

    def rate_limited(self, err):
        if err.reset_time:
            text = tr(
                "Das GitHub-API-Limit ist erreicht.\n\n"
                "Neue Anfragen sind ab {time} Uhr möglich."
            ).format(time=f"{err.reset_time:%H:%M}")
        else:
            text = tr(
                "Das GitHub-API-Limit ist erreicht.\n\n"
                "Bitte warte einige Minuten und versuche es erneut."
            )
        self._alert(tr("GitHub-Rate-Limit"), text)

    # ------------------------------------------------------------ Refresh

    def _check_mark(self, flag: bool) -> ft.Control:
        # Task 5 nutzt das in den Zeilen; hier definiert, damit row_changed läuft
        if flag:
            return ft.Text(
                "✓", size=self.s(13), color=self.c["green"], weight=ft.FontWeight.BOLD
            )
        return ft.Text("–", size=self.s(13), color=self.c["muted"])

    def refresh_stats(self):
        analysed = bool(
            self.controller.followers
            or self.controller.following
            or self.controller.client
        )
        for key, value in self.controller.stats().items():
            self.stat_values[key].value = str(value) if analysed else "–"

    def refresh_rate(self):
        client = self.controller.client
        remaining = getattr(client, "rate_remaining", None)
        limit = getattr(client, "rate_limit", None)
        if remaining is not None and limit:
            self.rate_text.value = f"{tr('API-Limit')}: {remaining}/{limit}"

    def refresh_tabs(self):
        for key, pill in self.tab_buttons.items():
            active = key == self.current_tab
            pill.bgcolor = self.c["selected"] if active else None
            pill.border = (
                ft.Border.all(1, self.c["border"]) if active else None
            )
            self.tab_labels[key].color = self.c["text"] if active else self.c["muted"]
            self.tab_labels[key].weight = (
                ft.FontWeight.BOLD if active else ft.FontWeight.NORMAL
            )

    def refresh_list(self):
        self._row_refs = {}
        rows = self.controller.sorted_rows(self.current_tab, self.filter_term)
        visible = {r["user"] for r in rows}
        self.selection &= visible
        if self.current_tab == "changes":
            self.user_list.controls = [self._build_change_row(r) for r in rows]
        else:
            self.user_list.controls = [self._build_row(r) for r in rows]
        self.header_box.content = self._build_list_header()
        term = self.filter_term.strip()
        self.user_list.visible = bool(rows)
        self.empty_box.visible = not rows
        self.empty_text.value = (
            tr("Keine Treffer für „{term}“.").format(term=term)
            if term
            else tr("Noch keine Daten.\nStarte links eine Analyse.")
        )

    def _build_change_row(self, row: dict) -> ft.Container:
        s = self.s
        gained = row["status"].startswith("+")
        icon = ft.Icon(
            ft.Icons.ADD_CIRCLE if gained else ft.Icons.REMOVE_CIRCLE,
            color=self.c["green"] if gained else self.c["red"],
            size=s(16),
        )
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(width=s(6)),
                    icon,
                    ft.Text(
                        row["user"],
                        size=s(13),
                        color=self.c["text"],
                        weight=ft.FontWeight.W_500,
                    ),
                    ft.Text(row["status"], size=s(12), color=self.c["muted"]),
                ],
                spacing=s(10),
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=s(10), vertical=s(8)),
            border=ft.Border.only(bottom=ft.BorderSide(1, self.c["border"])),
            ink=True,
            on_click=lambda e, u=row["user"]: self.on_open_profiles([u]),
        )

    def on_tab(self, key):
        self.current_tab = key
        self.refresh_tabs()
        self.refresh_list()
        self.refresh_buttons()
        self._schedule_detail_update()
        self._update()

    def on_search(self, e):
        self.filter_term = e.control.value or ""
        self.refresh_list()
        self._update()

    def on_sort(self, col):
        self.controller.sort_by(self.current_tab, col)
        self.refresh_list()
        self._update()

    def on_select_row(self, user, selected):
        if selected:
            self.selection.add(user)
        else:
            self.selection.discard(user)
        refs = self._row_refs.get(user)
        if refs:
            refs["container"].bgcolor = self.c["selected"] if selected else None
        self.refresh_buttons()
        self._schedule_detail_update()
        self._update()

    def _schedule_detail_update(self):
        if self._detail_timer is not None:
            self._detail_timer.cancel()
            self._detail_timer = None
        usable = (
            len(self.selection) == 1
            and self.controller.client is not None
            and hasattr(self.controller.client, "get_user")
            and not self.controller.busy
        )
        if not usable:
            self.detail_card.visible = False
            return
        user = next(iter(self.selection))
        if user in self._profile_cache:
            self._show_detail(user)
        else:
            self._detail_timer = threading.Timer(0.35, self._profile_worker, args=(user,))
            self._detail_timer.daemon = True
            self._detail_timer.start()

    def _profile_worker(self, user):
        self._detail_timer = None
        try:
            data = self.controller.client.get_user(user)
        except Exception:
            return  # Panel ist reiner Komfort – Fehler still ignorieren
        self._profile_cache[user] = data
        if self.selection == {user}:
            self._show_detail(user)
            self._update()

    def _show_detail(self, user):
        data = self._profile_cache[user]
        name = data.get("name") or user
        parts = [name if name == user else f"{name} (@{user})"]
        parts.append(f"{data.get('followers', '?')} {tr('Follower')}")
        parts.append(f"{data.get('following', '?')} {tr('Following')}")
        created = str(data.get("created_at", ""))[:4]
        if created:
            parts.append(f"{tr('dabei seit')} {created}")
        lines = ["  ·  ".join(parts)]
        bio = (data.get("bio") or "").strip().replace("\n", " ")
        if bio:
            if len(bio) > 110:
                bio = bio[:110] + "…"
            lines.append(bio)
        self.detail_text.value = "\n".join(lines)
        avatar = str(data.get("avatar_url") or "")
        if avatar:
            self.detail_avatar.src = avatar + ("&s=96" if "?" in avatar else "?s=96")
        self.detail_avatar.visible = bool(avatar)
        self.detail_card.visible = True

    @staticmethod
    def on_open_profiles(users):
        for user in users[:5]:
            webbrowser.open(f"https://github.com/{user}")

    def _menu_targets(self, user):
        """Aktive Auswahl plus die angeklickte Zeile."""
        return sorted(self.selection | {user})

    def on_menu_follow(self, user):
        targets = [
            u for u in self._menu_targets(user) if u not in self.controller.following
        ]
        if targets and self.controller.client:
            self.controller.start_follow(targets)

    def on_menu_unfollow(self, user):
        targets = self.controller.unfollowable(self._menu_targets(user))
        if targets:
            self._start_unfollow_flow(
                targets, self.controller.selection_question(targets)
            )

    def on_menu_protect(self, user):
        targets = self._menu_targets(user)
        unprotected = [u for u in targets if u not in self.controller.whitelist]
        # Erst alle schützen; sind bereits alle geschützt, Schutz aufheben
        if unprotected:
            self.controller.set_protected(unprotected, True)
        else:
            self.controller.set_protected(targets, False)

    def on_unfollow_all(self, e=None):
        users, question = self.controller.bulk_users_and_question()
        self._start_unfollow_flow(users, question)

    def on_unfollow_selection(self, e=None):
        users = self.controller.unfollowable(sorted(self.selection))
        if not users:
            self._alert(
                tr("Keine Auswahl"),
                tr("Markiere in der Tabelle Nutzer, denen du aktuell folgst."),
            )
            return
        self._start_unfollow_flow(users, self.controller.selection_question(users))

    def _start_unfollow_flow(self, users, question):
        if not self.controller.client:
            self._alert(tr("Keine Analyse"), tr("Starte zuerst eine Analyse."))
            return
        if not users:
            self._alert(tr("Nichts zu tun"), tr("Es gibt keine Nutzer zum Entfolgen."))
            return
        self._confirm(
            tr("Entfolgen bestätigen"),
            question + tr("\n\nDiese Aktion kann nicht rückgängig gemacht werden."),
            tr("Entfolgen"),
            lambda: self.controller.start_unfollow(users),
        )

    def refresh_buttons(self):
        if not hasattr(self, "unfollow_all_label"):
            return  # Sidebar-Aufbau läuft noch
        busy = self.controller.busy
        n = len(self.controller.unfollow_candidates)
        bulk = tr("🚫 Alle Nicht-Folgenden")
        self.unfollow_all_label.value = f"{bulk} ({n})" if n else bulk
        self.unfollow_all_button.disabled = not n or busy
        m = len(self.controller.unfollowable(sorted(self.selection)))
        selected = tr("Auswahl entfolgen")
        self.unfollow_sel_label.value = f"{selected} ({m})" if m else selected
        self.unfollow_sel_button.disabled = not m or busy
        k = len(self.controller.last_unfollowed)
        self.undo_button.visible = bool(k)
        self.undo_label.value = f"{tr('↩ Rückgängig')} ({k})"
        self.undo_button.disabled = busy

    def refresh_sparkline(self):
        counts = self.controller.spark_counts[-30:]
        if len(counts) < 2:
            self.spark_canvas.visible = False
            return
        s = self.s
        w, h, pad = s(250), s(36), s(5)
        lo, hi = min(counts), max(counts)
        span = (hi - lo) or 1
        points = []
        for i, value in enumerate(counts):
            x = pad + i * (w - 2 * pad) / (len(counts) - 1)
            y = h - pad - (value - lo) * (h - 2 * pad) / span
            points.append((x, y))
        stroke = ft.Paint(
            color=self.c["blue"], stroke_width=2, style=ft.PaintingStyle.STROKE
        )
        fill = ft.Paint(color=self.c["blue"], style=ft.PaintingStyle.FILL)
        shapes = [
            fcv.Line(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1],
                     paint=stroke)
            for i in range(len(points) - 1)
        ]
        shapes.append(fcv.Circle(points[-1][0], points[-1][1], 3, paint=fill))
        self.spark_canvas.shapes = shapes
        self.spark_canvas.visible = True

    def refresh_all(self):
        self.refresh_tabs()
        self.refresh_stats()
        self.refresh_list()
        self.refresh_buttons()
        self.refresh_rate()
        self.refresh_sparkline()
        self._update()


def _page_main(page: ft.Page):
    view = FollowerCheckerView()
    view.mount(page)


def main():
    ft.run(_page_main)


if __name__ == "__main__":
    try:
        main()
    except Exception as err:  # freundliche Meldung statt Stacktrace beim Doppelklick-Start
        print("❌ Die Anwendung konnte nicht gestartet werden.")
        print(f"   {type(err).__name__}: {err}")
        print("   Tipp: pip install -r requirements.txt")
        input("\nDrücke Enter zum Beenden...")
        sys.exit(1)
