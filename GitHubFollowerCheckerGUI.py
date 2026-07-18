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

import threading  # noqa: E402
from typing import Optional, Set  # noqa: E402

import flet as ft  # noqa: E402
import flet.canvas as fcv  # noqa: E402

# Hinweis: webbrowser kommt in Task 5 dazu, csv und datetime in Task 7 –
# hier noch nicht importieren (ruff F401).

try:
    import keyring  # noqa: E402
except Exception:  # keyring ist optional – ohne Backend einfach deaktivieren
    keyring = None  # type: ignore[assignment]

from gfc_core import (  # noqa: E402
    KEYRING_SERVICE,
    __version__,
    _load_settings,
    _save_settings,
    tr,
)
from gfc_controller import AppController, UiCallbacks  # noqa: E402

TABS = (
    ("unfollower", tr("Folgen nicht zurück")),
    ("fans", tr("Fans")),
    ("followers", tr("Follower")),
    ("following", tr("Following")),
    ("changes", tr("Verlauf")),
)
COLUMN_TITLES = {
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
            width=s(300),
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
        # Platzhalter – Task 5 baut Tabs, Filter und Nutzerliste hier auf.
        s = self.s
        self.export_button = ft.OutlinedButton(
            content=ft.Text(tr("⬇  CSV exportieren"), size=s(12), color=self.c["text"]),
            style=ft.ButtonStyle(
                side=ft.BorderSide(1, self.c["border"]),
                shape=ft.RoundedRectangleBorder(radius=s(6)),
            ),
            on_click=self.on_export,
        )
        return ft.Container(expand=True, bgcolor=self.c["bg"], padding=s(20))

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

    def on_window_event(self, e):
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
            self.page.window.destroy()

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
        self.status(tr("Sprache geändert – bitte starte die App neu."))

    def on_export(self, e=None):
        pass  # Task 7

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
        pass  # Task 5

    def refresh_list(self):
        pass  # Task 5

    def refresh_buttons(self):
        pass  # Task 6

    def refresh_sparkline(self):
        pass  # Task 7

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
