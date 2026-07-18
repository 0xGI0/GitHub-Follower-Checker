# Flet-Neuaufbau (GitHub-Look) – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die CustomTkinter-GUI wird durch eine moderne Flet-Oberfläche im GitHub-Look ersetzt – volle Feature-Parität, unveränderte Nutzerdaten, CLI und Kernlogik-Tests laufen weiter.

**Architecture:** Die UI-freie Kernlogik (GitHubClient, i18n, Settings/History) wandert nach `gfc_core.py`, die Ablauflogik (Zustand, Worker-Threads) in einen testbaren `AppController` in `gfc_controller.py`. `GitHubFollowerCheckerGUI.py` wird als reine Flet-View neu geschrieben und hängt sich über eine `UiCallbacks`-Schnittstelle an den Controller.

**Tech Stack:** Python ≥3.10, Flet ≥0.86,<0.87 (neue API-Generation: `ft.run`, `page.show_dialog`/`pop_dialog`, `ft.Border.all`/`ft.Padding.symmetric` als Klassen-Helfer), requests, keyring (optional), pytest.

**Spec:** `docs/superpowers/specs/2026-07-18-flet-redesign-design.md`

## Global Constraints

- Flet-Version exakt pinnen: `flet>=0.86,<0.87`. Python-Mindestversion: `>=3.10` (Flet-Vorgabe).
- Deutsche UI-Texte sind die Quelle, `_EN` in `gfc_core.py` enthält die Übersetzungen. Code-Kommentare auf Deutsch, Stil wie Bestandscode.
- ruff `line-length = 100`, `target-version` wird in Task 8 auf `py310` gehoben. Nach JEDEM Task: `ruff check .` und `python -m pytest -q` grün.
- Tests pinnen die Sprache mit `GFC_LANG=de` (steht bereits in `tests/test_github_follower_checker.py`).
- Token niemals loggen oder auf Platte schreiben – einzige Ausnahme: Keyring bei aktivem „Token merken“ (Service-Name `github-follower-checker`).
- `~/.config/github-follower-checker/settings.json` und `history.json`: Pfad und Format unverändert (Keys: `zoom`, `appearance`, `language`, `whitelist`, `remember_token`, `last_username`; neu nur `window_size` statt `window_geometry`).
- Flet-API-Fakten (am 2026-07-18 gegen flet 0.86.1 verifiziert): `ft.run(main)`; `page.show_dialog(dlg)` / `page.pop_dialog()`; FilePicker ist ein Service → `page.services.append(fp)`, `fp.save_file(...)` ist async und liefert awaited `str | None`; `ft.Dropdown` feuert `on_select` (NICHT `on_change`); `ft.Border.all/only`, `ft.BorderRadius.all/only`, `ft.Padding.symmetric/all` sind Klassenmethoden (die Kleinbuchstaben-Module `ft.border.only` etc. existieren NICHT mehr); `ft.BoxFit.COVER` (nicht `ImageFit`); Canvas via `import flet.canvas`; `ft.PopupMenuItem(content=..., on_click=...)` (kein `text=`-Parameter); Fenster über `page.window.width/height/min_width/min_height/prevent_close/on_event` mit `ft.WindowEventType.CLOSE`.

---

## Datei-Struktur

| Datei | Verantwortung |
|---|---|
| `gfc_core.py` (neu) | GitHubClient, Fehlerklassen, i18n (`tr`), Settings-/History-Helfer, `compute_follower_delta`, Konstanten. Kein UI-Import. |
| `gfc_controller.py` (neu) | `AppController` + `UiCallbacks`: Analyse-Zustand, Kandidaten, Whitelist, Verlauf/Delta, Worker-Threads. Importiert nur `gfc_core`, requests, threading. Kein Flet-Import. |
| `GitHubFollowerCheckerGUI.py` (neu geschrieben) | Flet-View: Theme-Tokens, Aufbau, Dialoge, Ereignis-Handler, `main()`. |
| `GitHubFollowerCheckerCLI.py` (angepasst) | Nur Import-Umstellung auf `gfc_core`. |
| `tests/test_github_follower_checker.py` (angepasst) | Neue Fixtures `core`/`controller_mod`/`viewmod`; Controller- und View-Tests ersetzen den Tk-Smoke-Test. Alle Tests laufen OHNE Display. |
| `requirements.txt`, `pyproject.toml` | flet statt customtkinter/pillow (Task 4), Version 2.0.0 (Task 9). |
| `.github/workflows/ci.yml`, `release.yml` | Ohne Xvfb; Packaging via `flet pack` (Task 8). |

---

### Task 1: Kernlogik nach `gfc_core.py` extrahieren

**Files:**
- Create: `gfc_core.py`
- Modify: `GitHubFollowerCheckerGUI.py` (Import statt Definition)
- Modify: `GitHubFollowerCheckerCLI.py:21-29` (Import-Quelle)
- Test: `tests/test_github_follower_checker.py`

**Interfaces:**
- Produces: Modul `gfc_core` mit exakt diesen öffentlichen Namen (Signaturen unverändert aus dem heutigen GUI-Modul): `__version__: str`, `KEYRING_SERVICE`, `BASE_URL`, `ACTION_DELAY`, `SETTINGS_PATH`, `HISTORY_PATH`, `HISTORY_LIMIT`, `_load_settings() -> dict`, `_save_settings(dict)`, `_detect_language(dict) -> str`, `_EN: dict`, `_LANG: str`, `tr(str) -> str`, `_load_history() -> dict`, `_save_history(dict)`, `_normalize_history_entries(value) -> list`, `compute_follower_delta(Set[str], Set[str]) -> tuple`, `RateLimitError`, `AuthError`, `GitHubClient`.
- Consumes: bestehender Code (reine Verschiebung).

- [ ] **Step 1: `gfc_core.py` anlegen**

Kopf der neuen Datei:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub Follower Checker – UI-freie Kernlogik.

GitHub-API-Client, Übersetzungen, Einstellungs- und Verlaufs-Speicher.
Wird von GUI und CLI gemeinsam genutzt. Das Token bleibt ausschließlich
im Arbeitsspeicher – es wird weder gespeichert noch geloggt.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Set

import requests

__version__ = "1.2.0"
```

Dann folgende Blöcke UNVERÄNDERT (Wortlaut inkl. Kommentare) aus `GitHubFollowerCheckerGUI.py` hierher verschieben – Zeilenangaben beziehen sich auf den aktuellen Stand (Commit `8eb7ce5`):

1. Zeilen 68–81: `KEYRING_SERVICE`, `BASE_URL`, `ACTION_DELAY` (+ Kommentar), `SETTINGS_PATH` (+ Kommentar), `HISTORY_PATH` (+ Kommentar)
2. Zeilen 84–99: `_load_settings`, `_save_settings`
3. Zeilen 102–254: Sprachblock – `_detect_language`, `_EN`, `_LANG = _detect_language(_load_settings())`, `tr`
4. Zeilen 265–266: `HISTORY_LIMIT = 50` (+ Kommentar „Anzahl gespeicherter Analyse-Stände pro Nutzer")
5. Zeilen 281–314: `_load_history`, `_save_history`, `_normalize_history_entries`, `compute_follower_delta`
6. Zeilen 339–430: `RateLimitError`, `AuthError`, `GitHubClient`

- [ ] **Step 2: Neue Übersetzungs-Keys für die künftige Flet-UI ergänzen**

In `gfc_core.py` ans Ende des `_EN`-Dicts (vor dem `# CLI`-Kommentarblock) einfügen:

```python
    "Abbrechen": "Cancel",
    "Folgen": "Follow",
    "Entfolgen": "Unfollow",
    "🛡 Schützen / Schutz aufheben": "🛡 Protect / unprotect",
    "Nutzer filtern…": "Filter users…",
    "Tipp: Checkboxen wählen mehrere Nutzer aus, ⋯ öffnet Aktionen.": "Tip: checkboxes select multiple users, ⋯ opens actions.",
```

- [ ] **Step 3: Altes GUI-Modul auf Import umstellen**

In `GitHubFollowerCheckerGUI.py` die in Step 1 verschobenen Blöcke löschen und direkt nach dem `keyring`-Import-Block (nach Zeile 66) einfügen:

```python
from gfc_core import (  # noqa: E402
    ACTION_DELAY,
    AuthError,
    GitHubClient,
    HISTORY_LIMIT,
    KEYRING_SERVICE,
    RateLimitError,
    __version__,
    _load_history,
    _load_settings,
    _normalize_history_entries,
    _save_history,
    _save_settings,
    compute_follower_delta,
    tr,
)
```

Außerdem im GUI-Kopf den jetzt ungenutzten Import `json` entfernen (Zeile 17) und aus der `typing`-Zeile `Callable` streichen, falls ruff es als ungenutzt meldet. `os`, `time`, `datetime`, `Path`, `requests` bleiben (werden weiter verwendet).

- [ ] **Step 4: CLI-Import umstellen**

`GitHubFollowerCheckerCLI.py` Zeilen 21–29 ersetzen durch:

```python
from gfc_core import (
    ACTION_DELAY,
    AuthError,
    GitHubClient,
    RateLimitError,
    __version__,
    _load_settings,
    tr,
)
```

- [ ] **Step 5: Test-Fixtures umstellen**

In `tests/test_github_follower_checker.py` die Fixtures so ändern (die `gui`-Fixture bleibt bis Task 4 für den Tk-Smoke-Test bestehen und hängt jetzt von `core` ab, damit `gfc_core` importierbar ist):

```python
@pytest.fixture(scope="session")
def core():
    sys.path.insert(0, str(REPO))
    import gfc_core

    return gfc_core


@pytest.fixture(scope="session")
def gui(core):
    spec = importlib.util.spec_from_file_location(
        "gui_under_test", REPO / "GitHubFollowerCheckerGUI.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
```

Dann rein mechanisch in diesen Tests den Parameter `gui` durch `core` ersetzen (inkl. aller `gui.`-Zugriffe im Body): `test_unfollow_success`, `test_unfollow_error`, `test_follow_success`, `test_rate_limit_raises`, `test_get_user`, `test_rate_limit_tracking`, `test_fetch_all_users_paginates`, `test_compute_follower_delta`, `test_compute_follower_delta_unchanged`, `test_history_roundtrip`, `test_history_corrupt_file`, `test_language_detection`, `test_translation_lookup`, `test_translations_nonempty`, `test_history_normalizes_old_format`. Auch die Helferfunktion anpassen:

```python
def make_client(core, responses):
    client = core.GitHubClient("demo-user", "demo-token")
    client.session = FakeSession(responses)
    return client
```

Im Tk-Smoke-Test `test_gui_end_to_end` zusätzlich `core` als Fixture aufnehmen und zwei Stellen ändern – die History liegt jetzt im Core-Modul:

```python
def test_gui_end_to_end(gui, core, tmp_path, monkeypatch):
    ...
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")   # statt gui
    ...
    assert "demo-user" in core._load_history()                             # statt gui
```

Alle übrigen Patches des Smoke-Tests (`gui._load_settings`, `gui.ACTION_DELAY`, `gui.messagebox`, `gui.threading`) bleiben unverändert – das GUI-Modul ruft diese Namen aus seinen eigenen Modul-Globals auf.

- [ ] **Step 6: Suite laufen lassen**

Run: `python -m pytest -q && ruff check .`
Expected: 25 Tests PASS (der GUI-Test nur mit DISPLAY), ruff ohne Befund.

- [ ] **Step 7: Commit**

```bash
git add gfc_core.py GitHubFollowerCheckerGUI.py GitHubFollowerCheckerCLI.py tests/test_github_follower_checker.py
git commit -m "refactor: Kernlogik in gfc_core extrahiert"
```

---

### Task 2: `AppController` – Zustand, Ergebnis, Verlauf

**Files:**
- Create: `gfc_controller.py`
- Test: `tests/test_github_follower_checker.py` (neuer Abschnitt)

**Interfaces:**
- Consumes: `gfc_core` (Task 1).
- Produces: `gfc_controller.TAB_KEYS = ("unfollower", "fans", "followers", "following", "changes")`; Klasse `UiCallbacks` mit No-Op-Methoden `status(text)`, `busy_changed(busy, determinate)`, `progress(fraction)`, `data_changed()`, `row_changed(user)`, `analysis_finished()`, `delta_changed(text)`, `undo_changed(count)`, `error(message)`, `rate_limited(err)`, `persist_credentials(username, token)`; Klasse `AppController(ui=None, settings=None, client_factory=GitHubClient)` mit Attributen `client`, `followers`, `following`, `rows`, `sort_state`, `unfollow_candidates`, `whitelist`, `last_unfollowed`, `spark_counts`, `busy` und Methoden `stats() -> dict`, `set_row_status(user, text)`, `mark_unfollowed(user)`, `mark_followed(user)`, `compute_candidates() -> list`, `unfollowable(users) -> list`, `set_protected(users, protect)`, `sort_by(tab, col)`, `visible_rows(tab, term="") -> list`, `sorted_rows(tab, term="") -> list`, `csv_table(tab, term="") -> list[list[str]]`, `apply_results(followers, following)`.

- [ ] **Step 1: Failing Tests schreiben**

Ans Ende von `tests/test_github_follower_checker.py` anhängen (ersetzt nichts Bestehendes):

```python
# ---------------------------------------------------------- AppController


class RecorderUi:
    """Zeichnet Controller-Callbacks für Assertions auf."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name,) + args)

        return record

    def last(self, name):
        matches = [c for c in self.calls if c[0] == name]
        return matches[-1] if matches else None


class CtrlFakeClient:
    username = "demo-user"
    rate_remaining = None
    rate_limit = None

    def unfollow(self, user):
        return True, "✓ Entfolgt"

    def follow(self, user):
        return True, "✓ Gefolgt"

    def get_user(self, user):
        return {"login": user}


@pytest.fixture(scope="session")
def controller_mod(core):
    import gfc_controller

    return gfc_controller


def make_controller(controller_mod, monkeypatch):
    monkeypatch.setattr(controller_mod, "_save_settings", lambda settings: None)
    ui = RecorderUi()
    return controller_mod.AppController(ui=ui, settings={}), ui


def test_controller_apply_results(controller_mod, monkeypatch):
    ctrl, ui = make_controller(controller_mod, monkeypatch)
    ctrl.apply_results({"alice", "bob", "carol", "dave"}, {"bob", "carol", "erin", "frank"})
    assert ctrl.stats() == {"followers": 4, "following": 4, "fans": 2, "unfollower": 2}
    assert [r["user"] for r in ctrl.rows["unfollower"]] == ["erin", "frank"]
    assert [r["user"] for r in ctrl.rows["fans"]] == ["alice", "dave"]
    assert ctrl.unfollow_candidates == ["erin", "frank"]
    assert ui.last("analysis_finished") is not None
    assert ui.last("busy_changed") == ("busy_changed", False, False)
    assert "2 Nutzer folgen dir nicht zurück" in ui.last("status")[1]


def test_controller_history_and_delta(controller_mod, core, tmp_path, monkeypatch):
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    ctrl, ui = make_controller(controller_mod, monkeypatch)
    ctrl.client = CtrlFakeClient()
    ctrl.apply_results({"alice", "bob", "carol", "dave"}, {"bob"})
    assert "Erste Analyse" in ui.last("delta_changed")[1]
    ctrl.apply_results({"alice", "bob", "carol", "neu-nutzer"}, {"bob"})
    delta = ui.last("delta_changed")[1]
    assert "+1 Follower: neu-nutzer" in delta
    assert "−1 Follower: dave" in delta
    assert ctrl.spark_counts == [4, 4]
    assert any(
        r["user"] == "dave" and "entfolgte dich" in r["status"] for r in ctrl.rows["changes"]
    )
    assert any(
        r["user"] == "neu-nutzer" and "folgt dir seit" in r["status"]
        for r in ctrl.rows["changes"]
    )
    assert "demo-user" in core._load_history()


def test_controller_whitelist(controller_mod, monkeypatch):
    ctrl, ui = make_controller(controller_mod, monkeypatch)
    ctrl.apply_results({"alice"}, {"erin", "frank"})
    ctrl.set_protected(["erin"], True)
    assert ctrl.unfollow_candidates == ["frank"]
    assert ctrl.settings["whitelist"] == ["erin"]
    assert ui.last("data_changed") is not None
    ctrl.set_protected(["erin"], False)
    assert ctrl.unfollow_candidates == ["erin", "frank"]


def test_controller_sort_and_filter(controller_mod, monkeypatch):
    ctrl, ui = make_controller(controller_mod, monkeypatch)
    ctrl.apply_results({"bob"}, {"anna", "bob", "Zoe"})
    assert [r["user"] for r in ctrl.sorted_rows("following")] == ["anna", "bob", "Zoe"]
    ctrl.sort_by("following", "user")   # gleiche Spalte → Richtung umkehren
    assert [r["user"] for r in ctrl.sorted_rows("following")] == ["Zoe", "bob", "anna"]
    assert [r["user"] for r in ctrl.sorted_rows("following", term="bo")] == ["bob"]


def test_controller_csv_table(controller_mod, monkeypatch):
    ctrl, ui = make_controller(controller_mod, monkeypatch)
    ctrl.apply_results({"alice", "bob"}, {"bob", "erin"})
    table = ctrl.csv_table("unfollower")
    assert table[0] == ["username", "folgt_dir", "du_folgst", "status"]
    assert table[1] == ["erin", "nein", "ja", ""]


def test_controller_row_marks(controller_mod, monkeypatch):
    ctrl, ui = make_controller(controller_mod, monkeypatch)
    ctrl.apply_results({"alice", "bob"}, {"bob", "erin"})
    ctrl.mark_unfollowed("erin")
    assert "erin" not in ctrl.following
    assert all(not r["you_follow"] for r in ctrl.rows["unfollower"] if r["user"] == "erin")
    ctrl.set_row_status("erin", "✓ Entfolgt")
    assert ctrl.compute_candidates() == []
    assert ui.last("row_changed") == ("row_changed", "erin")
```

- [ ] **Step 2: Tests laufen lassen – sie müssen fehlschlagen**

Run: `python -m pytest -q tests/test_github_follower_checker.py -k controller`
Expected: FAIL / ERROR mit `ModuleNotFoundError: No module named 'gfc_controller'`

- [ ] **Step 3: `gfc_controller.py` implementieren**

Vollständige neue Datei:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub Follower Checker – UI-freie Ablauf- und Zustandslogik.

Hält den Analyse-Zustand (Follower/Following, Tabellenzeilen, Whitelist,
Rückgängig-Liste) und führt alle API-Abläufe in Hintergrund-Threads aus.
Die Oberfläche hängt sich über UiCallbacks an – dadurch ist die gesamte
Logik ohne Fenster testbar.
"""

from datetime import datetime
from typing import List, Optional, Set

from gfc_core import (
    GitHubClient,
    HISTORY_LIMIT,
    RateLimitError,
    _load_history,
    _normalize_history_entries,
    _save_history,
    _save_settings,
    compute_follower_delta,
    tr,
)

# Hinweis: threading, time, requests, ACTION_DELAY und AuthError kommen erst
# mit den Workern in Task 3 dazu – hier noch nicht importieren (ruff F401).

TAB_KEYS = ("unfollower", "fans", "followers", "following", "changes")


class UiCallbacks:
    """No-Op-Basis: Die View überschreibt nur, was sie darstellt."""

    def status(self, text: str) -> None:
        pass

    def busy_changed(self, busy: bool, determinate: bool) -> None:
        pass

    def progress(self, fraction: float) -> None:
        pass

    def data_changed(self) -> None:
        pass

    def row_changed(self, user: str) -> None:
        pass

    def analysis_finished(self) -> None:
        pass

    def delta_changed(self, text: str) -> None:
        pass

    def undo_changed(self, count: int) -> None:
        pass

    def error(self, message: str) -> None:
        pass

    def rate_limited(self, err: RateLimitError) -> None:
        pass

    def persist_credentials(self, username: str, token: str) -> None:
        pass


class AppController:
    def __init__(self, ui: Optional[UiCallbacks] = None, settings: Optional[dict] = None,
                 client_factory=GitHubClient):
        self.ui = ui or UiCallbacks()
        self.settings = settings if settings is not None else {}
        self.client_factory = client_factory
        self.client: Optional[GitHubClient] = None
        self.followers: Set[str] = set()
        self.following: Set[str] = set()
        self.rows: dict = {key: [] for key in TAB_KEYS}
        self.sort_state: dict = {"changes": ("status", True)}  # Verlauf: Neuestes zuerst
        self.unfollow_candidates: List[str] = []
        self.whitelist: Set[str] = set(self.settings.get("whitelist", []))
        self.last_unfollowed: List[str] = []
        self.spark_counts: List[int] = []
        self.busy = False
        self._pending_token: Optional[str] = None

    # ------------------------------------------------------------ Zustand

    def stats(self) -> dict:
        return {
            "followers": len(self.followers),
            "following": len(self.following),
            "fans": len(self.followers - self.following),
            "unfollower": len(self.following - self.followers),
        }

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

    def set_row_status(self, user, text):
        for key, rows in self.rows.items():
            if key == "changes":  # Verlaufs-Einträge nicht überschreiben
                continue
            for row in rows:
                if row["user"] == user:
                    row["status"] = text
        self.ui.row_changed(user)

    def mark_unfollowed(self, user):
        self.following.discard(user)
        for rows in self.rows.values():
            for row in rows:
                if row["user"] == user:
                    row["you_follow"] = False
        self.ui.row_changed(user)

    def mark_followed(self, user):
        self.following.add(user)
        for rows in self.rows.values():
            for row in rows:
                if row["user"] == user:
                    row["you_follow"] = True
        self.ui.row_changed(user)

    def compute_candidates(self):
        """Nicht-Zurückfolgende ohne bereits Entfolgte und ohne Whitelist."""
        return [
            r["user"]
            for r in self.rows["unfollower"]
            if r["status"] != tr("✓ Entfolgt") and r["user"] not in self.whitelist
        ]

    def unfollowable(self, users):
        """Teilmenge der übergebenen Nutzer, denen aktuell noch gefolgt wird."""
        return [u for u in users if u in self.following]

    def set_protected(self, users, protect):
        if protect:
            self.whitelist.update(users)
        else:
            self.whitelist.difference_update(users)
        self.settings["whitelist"] = sorted(self.whitelist)
        _save_settings(self.settings)
        self.unfollow_candidates = self.compute_candidates()
        self.ui.data_changed()

    # -------------------------------------------------- Sortierung/Filter

    @staticmethod
    def _sort_key(row, col):
        if col == "user":
            return (row["user"].lower(),)
        if col in ("follows_you", "you_follow"):
            return (row[col], row["user"].lower())
        # Verlauf-Zeilen tragen einen ISO-Zeitstempel als Sortierschlüssel
        return (row.get("sort", row["status"]), row["user"].lower())

    def sort_by(self, tab, col):
        prev_col, prev_reverse = self.sort_state.get(tab, ("user", False))
        reverse = not prev_reverse if prev_col == col else False
        self.sort_state[tab] = (col, reverse)

    def visible_rows(self, tab, term=""):
        rows = self.rows[tab]
        term = term.strip().lower()
        if term:
            rows = [r for r in rows if term in r["user"].lower()]
        return rows

    def sorted_rows(self, tab, term=""):
        col, reverse = self.sort_state.get(tab, ("user", False))
        return sorted(
            self.visible_rows(tab, term),
            key=lambda r: self._sort_key(r, col),
            reverse=reverse,
        )

    # ------------------------------------------------------------- Export

    def csv_table(self, tab, term=""):
        """Sichtbare Zeilen als CSV-Tabelle inklusive Kopfzeile."""
        table = [["username", tr("folgt_dir"), tr("du_folgst"), "status"]]
        for row in self.visible_rows(tab, term):
            table.append([
                row["user"],
                tr("ja") if row["follows_you"] else tr("nein"),
                tr("ja") if row["you_follow"] else tr("nein"),
                row["status"],
            ])
        return table

    # ----------------------------------------------------------- Verlauf

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
                when = tr("unbekannt")
            gained, lost = compute_follower_delta(
                set(prev.get("followers", [])), set(curr.get("followers", []))
            )
            for user in gained:
                events[user] = (stamp, tr("+ folgt dir seit {when}").format(when=when))
            for user in lost:
                events[user] = (stamp, tr("− entfolgte dich am {when}").format(when=when))
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

        self.spark_counts = [len(e.get("followers", [])) for e in entries]
        self._rebuild_changes_rows(entries)

        if len(entries) < 2:
            return tr(
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
            when = tr("letzter Analyse")
        if not gained and not lost:
            return tr("Keine Follower-Veränderung seit {when}.").format(when=when)

        def fmt(users):
            names = ", ".join(users[:5])
            if len(users) > 5:
                names += f" … (+{len(users) - 5})"
            return names

        lines = [tr("Seit {when}:").format(when=when)]
        if gained:
            lines.append(
                tr("+{n} Follower: {names}").format(n=len(gained), names=fmt(gained))
            )
        if lost:
            lines.append(
                tr("−{n} Follower: {names}").format(n=len(lost), names=fmt(lost))
            )
        return "\n".join(lines)

    # ----------------------------------------------------------- Ergebnis

    def _set_busy(self, busy, status=None, determinate=False):
        self.busy = busy
        self.ui.busy_changed(busy, determinate)
        if status is not None:
            self.ui.status(status)

    def apply_results(self, followers, following):
        self.followers = set(followers)
        self.following = set(following)
        self._rebuild_rows()
        self.last_unfollowed = []
        self.ui.undo_changed(0)
        self.unfollow_candidates = self.compute_candidates()
        if self.client:
            self.ui.delta_changed(self._update_history())
            if self._pending_token:
                self.ui.persist_credentials(self.client.username, self._pending_token)
                self._pending_token = None
        self.ui.analysis_finished()
        n = len(self.unfollow_candidates)
        if n:
            status = tr(
                "Analyse abgeschlossen: {n} Nutzer folgen dir nicht zurück."
            ).format(n=n)
        else:
            status = tr("Analyse abgeschlossen: Alle folgen dir zurück. 🎉")
        self._set_busy(False, status)
```

(Die Abschnitte Analyse/Entfolgen/Folgen kommen in Task 3 in dieselbe Datei.)

- [ ] **Step 4: Tests laufen lassen**

Run: `python -m pytest -q tests/test_github_follower_checker.py -k controller`
Expected: 6 PASS

- [ ] **Step 5: Gesamtsuite + Lint**

Run: `python -m pytest -q && ruff check .`
Expected: alles PASS, ruff ohne Befund (der Import-Kopf oben enthält bewusst nur die in Task 2 genutzten Namen)

- [ ] **Step 6: Commit**

```bash
git add gfc_controller.py tests/test_github_follower_checker.py
git commit -m "feat: UI-freier AppController (Zustand, Verlauf, Delta)"
```

---

### Task 3: `AppController` – Analyse-, Entfolgen-, Folgen-Worker

**Files:**
- Modify: `gfc_controller.py` (Methoden anhängen)
- Test: `tests/test_github_follower_checker.py` (Abschnitt erweitern)

**Interfaces:**
- Consumes: Task-2-Stand von `AppController`.
- Produces: zusätzliche Methoden `start_analysis(username, token)`, `bulk_users_and_question() -> tuple[list, str]`, `selection_question(users) -> str` (statisch), `start_unfollow(users)`, `start_follow(users, is_undo=False)`, `undo_unfollow()`. Worker laufen in `threading.Thread(daemon=True)`; Tests ersetzen `gfc_controller.threading.Thread` durch einen synchronen Fake und setzen `gfc_controller.ACTION_DELAY = 0`.

- [ ] **Step 1: Failing Tests schreiben**

Ans Ende der Testdatei anhängen:

```python
class ImmediateCtrlThread:
    """Thread-Ersatz: führt das Target synchron aus (für Controller-Tests)."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


class AnalysisFakeClient:
    def __init__(self, username, token):
        self.username = username
        self.rate_remaining = 4998
        self.rate_limit = 5000

    def validate_credentials(self):
        pass

    def fetch_all_users(self, endpoint, on_page=None):
        if on_page:
            on_page(1)
        if endpoint.endswith("/followers"):
            return {"alice", "bob"}
        return {"bob", "erin"}


@pytest.fixture()
def sync_controller(controller_mod, core, monkeypatch, tmp_path):
    # HISTORY_PATH IMMER umbiegen – die Worker-Tests schreiben sonst in die
    # echte Nutzer-History unter ~/.config
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(controller_mod.threading, "Thread", ImmediateCtrlThread)
    monkeypatch.setattr(controller_mod, "ACTION_DELAY", 0)
    monkeypatch.setattr(controller_mod, "_save_settings", lambda settings: None)
    ui = RecorderUi()
    return controller_mod.AppController(ui=ui, settings={}), ui


def test_controller_analysis_flow(sync_controller):
    ctrl, ui = sync_controller
    ctrl.client_factory = AnalysisFakeClient
    ctrl.start_analysis("demo-user", "tok-123")
    assert ctrl.client is not None and ctrl.client.username == "demo-user"
    assert ctrl.stats()["unfollower"] == 1
    assert ui.last("persist_credentials") == ("persist_credentials", "demo-user", "tok-123")
    assert ctrl.busy is False


def test_controller_analysis_auth_error(controller_mod, sync_controller):
    ctrl, ui = sync_controller

    class BadClient(AnalysisFakeClient):
        def validate_credentials(self):
            raise controller_mod.AuthError("kaputt")

    ctrl.client_factory = BadClient
    ctrl.start_analysis("demo-user", "tok")
    assert "Token ungültig" in ui.last("error")[1]
    assert ctrl.busy is False


def test_controller_unfollow_and_undo(controller_mod, sync_controller):
    ctrl, ui = sync_controller
    ctrl.client = CtrlFakeClient()
    ctrl.apply_results({"alice", "bob"}, {"bob", "erin", "frank"})
    ctrl.start_unfollow(["erin", "frank"])
    assert "erin" not in ctrl.following and "frank" not in ctrl.following
    assert ui.last("undo_changed") == ("undo_changed", 2)
    assert "Fertig: 2 entfolgt." in ui.last("status")[1]
    assert ctrl.unfollow_candidates == []
    ctrl.undo_unfollow()
    assert {"erin", "frank"} <= ctrl.following
    assert ui.last("undo_changed") == ("undo_changed", 0)
    assert "Fertig: 2 gefolgt." in ui.last("status")[1]


def test_controller_unfollow_rate_limit(controller_mod, sync_controller):
    ctrl, ui = sync_controller

    class LimitedClient(CtrlFakeClient):
        def __init__(self):
            self.calls = 0

        def unfollow(self, user):
            self.calls += 1
            if self.calls >= 2:
                raise controller_mod.RateLimitError(None)
            return True, "✓ Entfolgt"

    ctrl.client = LimitedClient()
    ctrl.apply_results({"alice"}, {"erin", "frank", "gerd"})
    ctrl.start_unfollow(["erin", "frank", "gerd"])
    assert ui.last("rate_limited") is not None
    statuses = {r["user"]: r["status"] for r in ctrl.rows["following"]}
    assert statuses["erin"] == "✓ Entfolgt"
    assert statuses["frank"] == "Übersprungen (Rate-Limit)"
    assert statuses["gerd"] == "Übersprungen (Rate-Limit)"


def test_controller_questions(controller_mod, monkeypatch):
    ctrl, ui = make_controller(controller_mod, monkeypatch)
    ctrl.apply_results({"a"}, {"erin", "frank"})
    ctrl.set_protected(["erin"], True)
    users, question = ctrl.bulk_users_and_question()
    assert users == ["frank"]
    assert "🛡 1 geschützte Nutzer" in question
    single = controller_mod.AppController.selection_question(["bob"])
    assert "„bob“" in single
    many = controller_mod.AppController.selection_question([f"u{i}" for i in range(10)])
    assert "… und 2 weitere" in many
```

- [ ] **Step 2: Tests laufen lassen – sie müssen fehlschlagen**

Run: `python -m pytest -q -k "controller_analysis or controller_unfollow or controller_questions"`
Expected: FAIL mit `AttributeError: ... has no attribute 'start_analysis'`

- [ ] **Step 3: Worker-Methoden implementieren**

In `gfc_controller.py` – Importe im Kopf vervollständigen (jetzt werden alle gebraucht): `threading`, `time`, `requests`, `ACTION_DELAY`, `AuthError`. Dann ans Ende der Klasse `AppController` anhängen:

```python
    # ------------------------------------------------------ Fragen/Texte

    def bulk_users_and_question(self):
        """Kandidatenliste plus Bestätigungsfrage fürs Bulk-Entfolgen."""
        users = list(self.unfollow_candidates)
        if len(users) == 1:
            question = tr(
                "Wirklich „{user}“ entfolgen (folgt dir nicht zurück)?"
            ).format(user=users[0])
        else:
            question = tr(
                "Wirklich allen {n} Nutzern entfolgen, die dir nicht zurückfolgen?"
            ).format(n=len(users))
        protected = [
            r["user"]
            for r in self.rows["unfollower"]
            if r["user"] in self.whitelist and r["status"] != tr("✓ Entfolgt")
        ]
        if protected:
            question += tr(
                "\n\n🛡 {n} geschützte Nutzer werden übersprungen."
            ).format(n=len(protected))
        return users, question

    @staticmethod
    def selection_question(users):
        if len(users) == 1:
            return tr("Wirklich „{user}“ entfolgen?").format(user=users[0])
        shown = ", ".join(users[:8])
        if len(users) > 8:
            shown += tr(" … und {n} weitere").format(n=len(users) - 8)
        return tr("Wirklich {n} ausgewählten Nutzern entfolgen?\n\n{shown}").format(
            n=len(users), shown=shown
        )

    # ----------------------------------------------------------- Analyse

    def start_analysis(self, username, token):
        self._pending_token = token
        self._set_busy(True, tr("Validiere Zugangsdaten…"))
        threading.Thread(
            target=self._analysis_worker, args=(username, token), daemon=True
        ).start()

    def _analysis_worker(self, username, token):
        try:
            client = self.client_factory(username, token)
            client.validate_credentials()

            self.ui.status(tr("Lade Follower…"))
            followers = client.fetch_all_users(
                f"users/{username}/followers",
                on_page=lambda p: self.ui.status(
                    tr("Lade Follower… (Seite {page})").format(page=p)
                ),
            )

            self.ui.status(tr("Lade Following…"))
            following = client.fetch_all_users(
                f"users/{username}/following",
                on_page=lambda p: self.ui.status(
                    tr("Lade Following… (Seite {page})").format(page=p)
                ),
            )

            self.client = client
            self.apply_results(followers, following)

        except RateLimitError as err:
            self._set_busy(
                False, tr("GitHub-Rate-Limit erreicht – bitte später erneut versuchen.")
            )
            self.ui.rate_limited(err)
        except AuthError:
            self._fail(
                tr("Token ungültig oder abgelaufen. Prüfe auch den Scope „user:follow“.")
            )
        except requests.HTTPError as err:
            code = err.response.status_code if err.response is not None else "?"
            hint = tr(" Existiert der Username?") if code == 404 else ""
            self._fail(
                tr("GitHub-API-Fehler (HTTP {code}).{hint}").format(code=code, hint=hint)
            )
        except requests.RequestException:
            self._fail(
                tr("Keine Verbindung zur GitHub-API. Prüfe deine Internetverbindung.")
            )

    def _fail(self, message):
        self._set_busy(False, message)
        self.ui.error(message)

    # --------------------------------------------------------- Entfolgen

    def start_unfollow(self, users):
        self._set_busy(True, tr("Entfolge Nutzer…"), determinate=True)
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
                    self.set_row_status(skipped, tr("Übersprungen (Rate-Limit)"))
                break
            except requests.RequestException:
                ok, status_text = False, tr("Netzwerkfehler")

            if ok:
                succeeded.append(user)
                self.mark_unfollowed(user)
            else:
                failed += 1

            self.set_row_status(user, status_text)
            self.ui.progress(idx / total)
            self.ui.status(
                tr("Entfolge Nutzer… {idx}/{total}").format(idx=idx, total=total)
            )
            time.sleep(ACTION_DELAY)

        self._finish_unfollow(succeeded, failed, rate_limited)

    def _finish_unfollow(self, succeeded, failed, rate_limited):
        self.unfollow_candidates = self.compute_candidates()
        if succeeded:
            self.last_unfollowed = list(succeeded)
            self.ui.undo_changed(len(self.last_unfollowed))
        self.ui.data_changed()

        parts = [tr("{n} entfolgt").format(n=len(succeeded))]
        if failed:
            parts.append(tr("{n} fehlgeschlagen").format(n=failed))
        self._set_busy(False, tr("Fertig: ") + ", ".join(parts) + ".")

        if rate_limited:
            self.ui.rate_limited(rate_limited)

    # ----------------------------------------------------------- Folgen

    def undo_unfollow(self):
        self.start_follow(list(self.last_unfollowed), is_undo=True)

    def start_follow(self, users, is_undo=False):
        if not users or not self.client:
            return
        self._set_busy(True, tr("Folge Nutzern…"), determinate=True)
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
                    self.set_row_status(skipped, tr("Übersprungen (Rate-Limit)"))
                break
            except requests.RequestException:
                ok, status_text = False, tr("Netzwerkfehler")

            if ok:
                succeeded.append(user)
                self.mark_followed(user)
            else:
                failed += 1

            self.set_row_status(user, status_text)
            self.ui.progress(idx / total)
            self.ui.status(
                tr("Folge Nutzern… {idx}/{total}").format(idx=idx, total=total)
            )
            time.sleep(ACTION_DELAY)

        self._finish_follow(succeeded, failed, rate_limited, is_undo)

    def _finish_follow(self, succeeded, failed, rate_limited, is_undo):
        if is_undo and succeeded:
            self.last_unfollowed = []
            self.ui.undo_changed(0)
        self.unfollow_candidates = self.compute_candidates()
        self.ui.data_changed()

        parts = [tr("{n} gefolgt").format(n=len(succeeded))]
        if failed:
            parts.append(tr("{n} fehlgeschlagen").format(n=failed))
        self._set_busy(False, tr("Fertig: ") + ", ".join(parts) + ".")

        if rate_limited:
            self.ui.rate_limited(rate_limited)
```

- [ ] **Step 4: Tests laufen lassen**

Run: `python -m pytest -q && ruff check .`
Expected: alle Tests PASS (30+), ruff ohne Befund

- [ ] **Step 5: Commit**

```bash
git add gfc_controller.py tests/test_github_follower_checker.py
git commit -m "feat: AppController-Aktionen (Analyse, Entfolgen, Folgen, Undo)"
```

---

### Task 4: Flet-View – Grundgerüst, Sidebar, Fenster & Einstellungen

Ab diesem Task ersetzt die Flet-View die CustomTkinter-GUI vollständig. Der Tk-Smoke-Test entfällt (Ersatz: Controller-Tests aus Task 2/3 plus neue headless View-Tests – KEIN Display mehr nötig).

**Files:**
- Rewrite: `GitHubFollowerCheckerGUI.py` (kompletter Neuinhalt, alte Datei wird verworfen)
- Modify: `requirements.txt` (flet rein, customtkinter/pillow raus)
- Modify: `pyproject.toml` (dependencies, py-modules, requires-python)
- Test: `tests/test_github_follower_checker.py` (`gui`-Fixture + `test_gui_end_to_end` + `FakeClient`/`ImmediateThread`-Klassen des Tk-Tests löschen; neue `viewmod`-Fixture + Konstruktions-Tests)

**Interfaces:**
- Consumes: `gfc_core` (Task 1), `AppController`/`UiCallbacks` (Task 2/3).
- Produces: Klasse `FollowerCheckerView(UiCallbacks)` mit `__init__(page=None, settings=None)`, `mount(page)`, Attributen `controller`, `settings`, `scale`, `mode`, `c` (Farbtokens), `current_tab`, `selection`, `filter_term`, Controls `username_field`, `token_field`, `remember_box`, `analyze_button`, `progress_bar`, `status_text`, `stat_values` (dict key→`ft.Text`), `delta_text`, `spark_canvas`, `theme_menu`, `zoom_menu`, `language_menu`, `rate_text`, `export_button`, `root`; Methoden `s(px)`, `_card(...)`, `build_sidebar()`, `build_main()` (in diesem Task Platzhalter, ab Task 5 echt), `_rebuild()`, Refresh-Stubs `refresh_tabs/refresh_list/refresh_buttons/refresh_sparkline` (Task 5–7 füllen sie), `refresh_stats()`, `refresh_rate()`, `refresh_all()`, alle `UiCallbacks`-Implementierungen, `_alert(title, message)`, `_confirm(title, question, action_label, on_confirm)`, `on_analyze`, `on_appearance`, `on_zoom`, `on_language`, `on_remember_toggle`, `on_window_event`; Modulfunktionen `_page_main(page)`, `main()`; Konstanten `PALETTE`, `TABS`, `COLUMN_TITLES`, `ZOOM_STEPS`.

- [ ] **Step 1: flet lokal installieren**

Run: `pip install 'flet>=0.86,<0.87'`
Expected: erfolgreiche Installation (flet 0.86.x)

- [ ] **Step 2: Failing View-Tests schreiben**

In `tests/test_github_follower_checker.py`: Den kompletten Abschnitt „GUI-Smoke“ löschen (Klassen `FakeClient`, `ImmediateThread` und Funktion `test_gui_end_to_end`) sowie die `gui`-Fixture entfernen. Neu anhängen:

```python
# ------------------------------------------------------------ Flet-View


@pytest.fixture(scope="session")
def viewmod(core, controller_mod):
    spec = importlib.util.spec_from_file_location(
        "view_under_test", REPO / "GitHubFollowerCheckerGUI.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_view(viewmod, monkeypatch):
    import gfc_controller

    # Beide Module patchen – View UND Controller schreiben sonst echte Settings
    monkeypatch.setattr(viewmod, "_save_settings", lambda settings: None)
    monkeypatch.setattr(gfc_controller, "_save_settings", lambda settings: None)
    return viewmod.FollowerCheckerView(settings={"zoom": 1.0, "appearance": "Dark"})


def collect_texts(control, found=None):
    """Sammelt rekursiv alle ft.Text-Werte eines Control-Baums ein."""
    found = found if found is not None else []
    value = getattr(control, "value", None)
    if isinstance(value, str):
        found.append(value)
    for attr in ("content", "controls", "title", "actions", "label", "shapes"):
        child = getattr(control, attr, None)
        if child is None:
            continue
        for item in child if isinstance(child, list) else [child]:
            if hasattr(item, "__dataclass_fields__"):
                collect_texts(item, found)
    return found


def test_view_sidebar_builds(viewmod, monkeypatch):
    view = make_view(viewmod, monkeypatch)
    texts = " ".join(collect_texts(view.root))
    assert "Follower Checker" in texts
    assert "ZUGANGSDATEN" in texts
    assert "Analyse starten" in texts
    assert view.stat_values["followers"].value == "–"
    assert view.token_field.password is True
    assert view.c["bg"] == "#0d1117"


def test_view_light_palette(viewmod, monkeypatch):
    monkeypatch.setattr(viewmod, "_save_settings", lambda settings: None)
    view = viewmod.FollowerCheckerView(settings={"zoom": 1.0, "appearance": "Light"})
    assert view.mode == "light"
    assert view.c["bg"] == "#ffffff"


def test_view_zoom_scales(viewmod, monkeypatch):
    monkeypatch.setattr(viewmod, "_save_settings", lambda settings: None)
    view = viewmod.FollowerCheckerView(settings={"zoom": 1.5, "appearance": "Dark"})
    assert view.s(100) == 150


def test_view_analyze_requires_input(viewmod, monkeypatch):
    view = make_view(viewmod, monkeypatch)
    alerts = []
    monkeypatch.setattr(view, "_alert", lambda title, msg: alerts.append((title, msg)))
    view.on_analyze()
    assert alerts and "Eingabe fehlt" in alerts[0][0]
```

- [ ] **Step 3: Tests laufen lassen – sie müssen fehlschlagen**

Run: `python -m pytest -q -k view`
Expected: FAIL (altes Modul hat keine `FollowerCheckerView`; ggf. schlägt bereits der Import wegen customtkinter-Bootstrap fehl – genau deshalb wird die Datei jetzt ersetzt)

- [ ] **Step 4: `GitHubFollowerCheckerGUI.py` neu schreiben**

Kompletter neuer Dateiinhalt (ersetzt die Tk-Implementierung; Hauptbereich/Aktionen sind hier bewusst noch minimal und werden in Task 5–7 gefüllt):

```python
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
        page.window.min_width = 990
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
```

- [ ] **Step 5: Abhängigkeitsdateien anpassen**

`requirements.txt` komplett ersetzen durch:

```
requests>=2.31.0
flet>=0.86,<0.87
keyring>=24
```

In `pyproject.toml`: `requires-python = ">=3.10"`, den `dependencies`-Block ersetzen durch:

```toml
dependencies = [
    "requests>=2.31.0",
    "flet>=0.86,<0.87",
    "keyring>=24",
]
```

und `py-modules` erweitern:

```toml
[tool.setuptools]
py-modules = ["gfc_core", "gfc_controller", "GitHubFollowerCheckerGUI", "GitHubFollowerCheckerCLI"]
```

- [ ] **Step 6: Tests laufen lassen**

Run: `python -m pytest -q && ruff check .`
Expected: alle PASS – komplett OHNE Display (kein `DISPLAY`-Skip mehr in der Ausgabe)

- [ ] **Step 7: App manuell starten (Sichtprüfung)**

Run: `python GitHubFollowerCheckerGUI.py`
Expected: Fenster „GitHub Follower Checker“ öffnet sich im Dark-GitHub-Look, Sidebar vollständig (Felder, Button, Stat-Karten mit „–“, Dropdowns unten), Hauptbereich noch leer. Fenster schließen speichert Settings ohne Traceback.

- [ ] **Step 8: Commit**

```bash
git add GitHubFollowerCheckerGUI.py requirements.txt pyproject.toml tests/test_github_follower_checker.py
git commit -m "feat!: Flet-GUI im GitHub-Look – Grundgerüst und Sidebar"
```

---

### Task 5: Flet-View – Tabs, Filter, Sortierung, Nutzerliste

**Files:**
- Modify: `GitHubFollowerCheckerGUI.py` (`build_main` ersetzen, Zeilen-Builder + Refresh-Methoden ergänzen)
- Test: `tests/test_github_follower_checker.py`

**Interfaces:**
- Consumes: Task-4-View, `controller.sorted_rows(tab, term)`, `controller.sort_by(tab, col)`.
- Produces: echte `build_main()`; Controls `tab_buttons` (dict key→Container), `tab_labels` (dict key→Text), `search_field`, `header_box`, `user_list` (ListView), `empty_box`, `empty_text`, `detail_card` (unsichtbarer Platzhalter bis Task 7), `bottom_bar` (Row, Buttons folgen in Task 6); Methoden `_build_row(row) -> ft.Container`, `_build_list_header() -> ft.Container`, `refresh_tabs()`, `refresh_list()`, `on_tab(key)`, `on_search(e)`, `on_sort(col)`, `on_select_row(user, selected)`, `on_open_profiles(users)`, `_schedule_detail_update()` (Stub bis Task 7), `_row_menu(user)` (Stub-⋯-Button bis Task 6).

- [ ] **Step 1: Failing Tests schreiben**

Anhängen an die Testdatei:

```python
def demo_view(viewmod, monkeypatch):
    """View mit eingespeisten Fake-Daten (ohne Netzwerk)."""
    view = make_view(viewmod, monkeypatch)
    view.controller.client = CtrlFakeClient()
    view.controller.apply_results(
        {"alice", "bob", "carol", "dave"}, {"bob", "carol", "erin", "frank"}
    )
    return view


def test_view_list_shows_unfollowers(viewmod, monkeypatch, core, tmp_path):
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    view = demo_view(viewmod, monkeypatch)
    assert view.current_tab == "unfollower"
    assert set(view._row_refs) == {"erin", "frank"}
    assert view.stat_values["followers"].value == "4"
    assert view.stat_values["fans"].value == "2"


def test_view_tab_and_filter(viewmod, monkeypatch, core, tmp_path):
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    view = demo_view(viewmod, monkeypatch)
    view.on_tab("following")
    assert set(view._row_refs) == {"bob", "carol", "erin", "frank"}
    view.filter_term = "bo"
    view.refresh_list()
    assert set(view._row_refs) == {"bob"}
    view.filter_term = "zzz"
    view.refresh_list()
    assert view.empty_box.visible is True
    assert "zzz" in view.empty_text.value


def test_view_sort_toggle(viewmod, monkeypatch, core, tmp_path):
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    view = demo_view(viewmod, monkeypatch)
    view.on_tab("following")
    first = list(view._row_refs)[0]
    assert first == "bob"
    view.on_sort("user")  # war schon nach user aufsteigend → jetzt absteigend
    assert list(view._row_refs)[0] == "frank"


def test_view_selection_updates_state(viewmod, monkeypatch, core, tmp_path):
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    view = demo_view(viewmod, monkeypatch)
    view.on_select_row("erin", True)
    assert view.selection == {"erin"}
    view.on_select_row("erin", False)
    assert view.selection == set()


def test_view_whitelist_shield(viewmod, monkeypatch, core, tmp_path):
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    view = demo_view(viewmod, monkeypatch)
    view.controller.set_protected(["erin"], True)
    assert view._row_refs["erin"]["name"].value.startswith("🛡 ")
```

- [ ] **Step 2: Tests laufen lassen – sie müssen fehlschlagen**

Run: `python -m pytest -q -k "view_list or view_tab or view_sort or view_selection or view_whitelist"`
Expected: FAIL (`_row_refs` bleibt leer, `refresh_list` ist noch ein Stub)

- [ ] **Step 3: `build_main` und Listen-Methoden implementieren**

In `GitHubFollowerCheckerGUI.py` zuerst im Import-Kopf `import webbrowser  # noqa: E402` ergänzen (direkt vor `from typing import …`), dann die Platzhalter-`build_main` sowie die Stubs `refresh_tabs`/`refresh_list` ersetzen und die neuen Methoden einfügen:

```python
    def build_main(self) -> ft.Container:
        s = self.s
        self.tab_buttons = {}
        self.tab_labels = {}
        pills = []
        for key, label in TABS:
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

        # Platzhalter – Task 7 füllt das Profil-Panel
        self.detail_card = ft.Container(visible=False)
        # Platzhalter – Task 6 füllt die Aktionsleiste
        self.bottom_bar = ft.Row([])

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
                COLUMN_TITLES[col_key] + arrow,
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
        # Platzhalter – Task 6 hängt hier das ⋯-Aktionsmenü ein
        return ft.Container(width=self.s(40))

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
        # Task 7 gestaltet den Verlauf als Timeline; bis dahin normale Zeile
        return self._build_row(row)

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
        pass  # Task 7

    @staticmethod
    def on_open_profiles(users):
        for user in users[:5]:
            webbrowser.open(f"https://github.com/{user}")
```

Außerdem in Task-4-Code die doppelte `export_button`-Erzeugung aus der alten Platzhalter-`build_main` entfernen (der Button wird jetzt hier gebaut).

- [ ] **Step 4: Tests laufen lassen**

Run: `python -m pytest -q && ruff check .`
Expected: alle PASS

- [ ] **Step 5: Sichtprüfung mit Fake-Daten**

Run (Scratch-Skript, Muster siehe Task 9 Step 5 – nur mount + `apply_results` mit Demo-Daten):
Expected: Tabs als Pills (aktiver Tab hervorgehoben), Liste mit Avataren, ✓/– Spalten, Filterfeld filtert live.

- [ ] **Step 6: Commit**

```bash
git add GitHubFollowerCheckerGUI.py tests/test_github_follower_checker.py
git commit -m "feat: Flet-GUI – Tabs, Filter, Sortierung, Nutzerliste"
```

---

### Task 6: Flet-View – Aktionsleiste, Dialoge, Zeilenmenü, Rückgängig

**Files:**
- Modify: `GitHubFollowerCheckerGUI.py` (`bottom_bar` füllen, `refresh_buttons` + `_row_menu` ersetzen, Aktions-Handler ergänzen)
- Test: `tests/test_github_follower_checker.py`

**Interfaces:**
- Consumes: `controller.bulk_users_and_question()`, `controller.selection_question(users)`, `controller.start_unfollow/start_follow/undo_unfollow`, `controller.unfollowable(users)`, `controller.set_protected(users, protect)`.
- Produces: Controls `tip_text`, `undo_button`/`undo_label`, `unfollow_sel_button`/`unfollow_sel_label`, `unfollow_all_button`/`unfollow_all_label`; Methoden `refresh_buttons()` (echt), `_row_menu(user)` (echtes ⋯-Menü), `on_unfollow_all()`, `on_unfollow_selection()`, `_start_unfollow_flow(users, question)`, `_menu_targets(user)`, `on_menu_follow(user)`, `on_menu_unfollow(user)`, `on_menu_protect(user)`.

- [ ] **Step 1: Failing Tests schreiben (End-to-End headless, Portierung des alten Tk-Smoke-Tests)**

Anhängen an die Testdatei:

```python
def test_view_end_to_end(viewmod, controller_mod, core, monkeypatch, tmp_path):
    """Portierung des alten Tk-Smoke-Tests: Analyse → Entfolgen → Undo."""
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(controller_mod.threading, "Thread", ImmediateCtrlThread)
    monkeypatch.setattr(controller_mod, "ACTION_DELAY", 0)
    view = make_view(viewmod, monkeypatch)
    # Bestätigungsdialoge automatisch bestätigen (headless keine Page)
    monkeypatch.setattr(
        view, "_confirm", lambda title, q, label, on_confirm: on_confirm()
    )
    view.controller.client = CtrlFakeClient()
    view.controller.apply_results(
        {"alice", "bob", "carol", "dave"}, {"bob", "carol", "erin", "frank"}
    )
    assert view.stat_values["followers"].value == "4"
    assert "Erste Analyse" in view.delta_text.value

    # Whitelist schützt vor dem Bulk-Entfolgen
    view.controller.set_protected(["erin"], True)
    assert view.controller.unfollow_candidates == ["frank"]
    view.controller.set_protected(["erin"], False)

    # Auswahl entfolgen (zwei Mutuals)
    view.on_tab("following")
    view.on_select_row("bob", True)
    view.on_select_row("carol", True)
    assert "(2)" in view.unfollow_sel_label.value
    assert view.unfollow_sel_button.disabled is False
    view.on_unfollow_selection()
    assert "Fertig: 2 entfolgt." in view.status_text.value
    assert "bob" not in view.controller.following
    assert view._row_refs["bob"]["status"].value == "✓ Entfolgt"
    assert view.undo_button.visible is True
    assert "(2)" in view.undo_label.value

    # Rückgängig folgt beiden wieder
    view.controller.undo_unfollow()
    assert "Fertig: 2 gefolgt." in view.status_text.value
    assert {"bob", "carol"} <= view.controller.following
    assert view.undo_button.visible is False


def test_view_unfollow_all_needs_client(viewmod, monkeypatch):
    view = make_view(viewmod, monkeypatch)
    view.controller.rows["unfollower"] = [
        {"user": "x", "follows_you": False, "you_follow": True, "status": ""}
    ]
    view.controller.unfollow_candidates = ["x"]
    alerts = []
    monkeypatch.setattr(view, "_alert", lambda title, msg: alerts.append(title))
    view.on_unfollow_all()
    assert alerts == ["Keine Analyse"]


def test_view_menu_protect_toggles(viewmod, monkeypatch, core, tmp_path):
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    view = demo_view(viewmod, monkeypatch)
    view.on_menu_protect("erin")
    assert "erin" in view.controller.whitelist
    view.on_menu_protect("erin")
    assert "erin" not in view.controller.whitelist
```

- [ ] **Step 2: Tests laufen lassen – sie müssen fehlschlagen**

Run: `python -m pytest -q -k "end_to_end or unfollow_all_needs or menu_protect"`
Expected: FAIL (`unfollow_sel_label` existiert nicht, `on_unfollow_all`/`on_menu_protect` fehlen)

- [ ] **Step 3: Aktionsleiste, Menü und Handler implementieren**

In `build_main` die Platzhalter-Zeile `self.bottom_bar = ft.Row([])` ersetzen durch:

```python
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
```

Den Stub `refresh_buttons` (Task 4) ersetzen durch:

```python
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
```

Den Stub `_row_menu` (Task 5) ersetzen durch das echte Menü – die Handler werten die Auswahl erst beim Klick aus, damit das Menü nie veraltet:

```python
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
```

Neue Handler-Methoden (nach `on_open_profiles` einfügen):

```python
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
```

Hinweis Reihenfolge der Guards: „Keine Analyse“ wird VOR „Nichts zu tun“ geprüft (der Test `test_view_unfollow_all_needs_client` erwartet genau das; das alte GUI prüfte andersherum, aber ohne Client ist die Kandidatenliste ohnehin leer und „Keine Analyse“ die hilfreichere Meldung).

- [ ] **Step 4: Tests laufen lassen**

Run: `python -m pytest -q && ruff check .`
Expected: alle PASS

- [ ] **Step 5: Commit**

```bash
git add GitHubFollowerCheckerGUI.py tests/test_github_follower_checker.py
git commit -m "feat: Flet-GUI – Aktionen, Dialoge, Rückgängig"
```

---

### Task 7: Flet-View – Profilpanel, Verlauf-Timeline, Sparkline, CSV-Export

**Files:**
- Modify: `GitHubFollowerCheckerGUI.py`
- Test: `tests/test_github_follower_checker.py`

**Interfaces:**
- Consumes: `controller.client.get_user(user)` (liefert dict mit `name`, `followers`, `following`, `created_at`, `bio`, `avatar_url`), `controller.spark_counts`, `controller.csv_table(tab, term)`.
- Produces: echtes `detail_card` (+ `detail_avatar`, `detail_text`), `_schedule_detail_update()` (350-ms-Debounce via `threading.Timer`), `_profile_worker(user)`, `_show_detail(user)`, echte `_build_change_row(row)`, echte `refresh_sparkline()`, echtes `on_export()`.

- [ ] **Step 1: Failing Tests schreiben**

```python
def test_view_detail_panel(viewmod, monkeypatch, core, tmp_path):
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    view = demo_view(viewmod, monkeypatch)
    view._profile_cache["erin"] = {
        "name": "Erin Beispiel",
        "followers": 42,
        "following": 7,
        "created_at": "2019-04-01T00:00:00Z",
        "bio": "Hallo Welt",
        "avatar_url": "https://avatars.githubusercontent.com/u/1?v=4",
    }
    view.selection = {"erin"}
    view._schedule_detail_update()
    assert view.detail_card.visible is True
    assert "Erin Beispiel (@erin)" in view.detail_text.value
    assert "42" in view.detail_text.value
    assert "2019" in view.detail_text.value
    view.selection = set()
    view._schedule_detail_update()
    assert view.detail_card.visible is False


def test_view_change_rows_timeline(viewmod, monkeypatch, core, tmp_path):
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    view = demo_view(viewmod, monkeypatch)
    # zweite Analyse erzeugt Verlaufseinträge
    view.controller.apply_results(
        {"alice", "bob", "carol", "neu-nutzer"}, {"bob", "carol", "erin", "frank"}
    )
    view.on_tab("changes")
    texts = " ".join(collect_texts(view.user_list))
    assert "neu-nutzer" in texts
    assert "dave" in texts


def test_view_sparkline_appears(viewmod, monkeypatch, core, tmp_path):
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    view = demo_view(viewmod, monkeypatch)
    assert view.spark_canvas.visible is False  # erst eine Analyse
    view.controller.apply_results({"alice", "bob"}, {"bob"})
    assert view.spark_canvas.visible is True
    assert len(view.spark_canvas.shapes) >= 2  # mind. 1 Linie + Endpunkt


def test_view_csv_export(viewmod, monkeypatch, core, tmp_path):
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    view = demo_view(viewmod, monkeypatch)
    target = tmp_path / "export.csv"

    class PickerStub:
        async def save_file(self, **kwargs):
            return str(target)

    view.file_picker = PickerStub()
    asyncio.run(view.on_export())
    content = target.read_text(encoding="utf-8-sig")
    assert "username" in content.splitlines()[0]
    assert "erin" in content
    assert "CSV gespeichert" in view.status_text.value


def test_view_csv_export_without_data(viewmod, monkeypatch):
    view = make_view(viewmod, monkeypatch)
    alerts = []
    monkeypatch.setattr(view, "_alert", lambda title, msg: alerts.append(title))
    asyncio.run(view.on_export())
    assert alerts == ["Keine Daten"]
```

- [ ] **Step 2: Tests laufen lassen – sie müssen fehlschlagen**

Run: `python -m pytest -q -k "detail_panel or timeline or sparkline or csv_export"`
Expected: FAIL (Detail-Panel/Export sind Stubs)

- [ ] **Step 3: Implementieren**

Zuerst im Import-Kopf `import csv  # noqa: E402` und `from datetime import datetime  # noqa: E402` ergänzen (bei den anderen Stdlib-Importen). Dann in `build_main` den Platzhalter `self.detail_card = ft.Container(visible=False)` ersetzen durch:

```python
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
```

Den Stub `_schedule_detail_update` (Task 5) ersetzen und die Worker-Methoden ergänzen:

```python
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
```

Die Stub-`_build_change_row` (Task 5) ersetzen – Verlauf als Timeline:

```python
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
```

Den Stub `refresh_sparkline` (Task 4) ersetzen:

```python
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
```

Den Stub `on_export` (Task 4) ersetzen:

```python
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
```

Zusätzlich in `analysis_finished` nach `self._profile_cache.clear()` die Zeile `self.detail_card.visible = False` einfügen (Panel nach neuer Analyse schließen). Achtung: In den headless-Tests existiert `file_picker` nicht automatisch (wird erst in `mount` erzeugt) – der CSV-Test setzt deshalb einen `PickerStub`. Damit `on_export` ohne `mount` nicht crasht, im `__init__` `self.file_picker = None` vorbelegen und in `on_export` nach der „Keine Daten“-Prüfung einfügen:

```python
        if self.file_picker is None:
            return
```

(`mount` überschreibt `self.file_picker` mit dem echten Picker wie in Task 4 gezeigt.)

- [ ] **Step 4: Tests laufen lassen**

Run: `python -m pytest -q && ruff check .`
Expected: alle PASS

- [ ] **Step 5: Commit**

```bash
git add GitHubFollowerCheckerGUI.py tests/test_github_follower_checker.py
git commit -m "feat: Flet-GUI – Profilpanel, Verlauf-Timeline, Sparkline, CSV-Export"
```

---

### Task 8: CI und Release-Packaging auf Flet umstellen

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/release.yml`
- Modify: `pyproject.toml` (`[tool.ruff] target-version`)

**Interfaces:**
- Consumes: Modulnamen aus Task 1–4 (`gfc_core.py`, `gfc_controller.py`, `GitHubFollowerCheckerGUI.py`, `GitHubFollowerCheckerCLI.py`).
- Produces: CI ohne Xvfb (Tests laufen headless), Release-Binaries via `flet pack`.

- [ ] **Step 1: `ci.yml` anpassen**

Die Steps „Typen (mypy)“, „Syntax-Check“ und „Tests (pytest unter Xvfb)“ ersetzen durch:

```yaml
      - name: Typen (mypy)
        run: mypy gfc_core.py gfc_controller.py GitHubFollowerCheckerGUI.py GitHubFollowerCheckerCLI.py

      - name: Syntax-Check
        run: python -m py_compile gfc_core.py gfc_controller.py GitHubFollowerCheckerGUI.py GitHubFollowerCheckerCLI.py

      - name: Tests (pytest)
        run: python -m pytest -q
```

(Der Install-Step bleibt unverändert – `requirements.txt` enthält seit Task 4 flet.)

- [ ] **Step 2: `release.yml` anpassen**

Die Steps „Abhängigkeiten installieren“ und „Binary bauen“ ersetzen durch:

```yaml
      - name: Abhängigkeiten installieren
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt flet-cli pyinstaller

      - name: Binary bauen
        run: >
          flet pack GitHubFollowerCheckerGUI.py
          --name GitHubFollowerChecker
          --icon docs/icon.ico
```

Aus der Build-Matrix den nun ungenutzten Schlüssel `sep` entfernen (`--add-data` entfällt, das PNG-Icon wird zur Laufzeit nicht mehr gebraucht). Die Schritte „Artefakt umbenennen (Linux)“ und „An Release anhängen“ bleiben unverändert.

- [ ] **Step 3: ruff-Zielversion anheben**

In `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py310"
```

- [ ] **Step 4: Lokal validieren**

Run: `python -m pytest -q && ruff check . && python -m py_compile gfc_core.py gfc_controller.py GitHubFollowerCheckerGUI.py GitHubFollowerCheckerCLI.py`
Expected: alles grün. Zusätzlich YAML-Syntax prüfen (pyyaml ggf. vorher via `pip install pyyaml`): `python -c "import yaml, pathlib; [yaml.safe_load(p.read_text()) for p in pathlib.Path('.github/workflows').glob('*.yml')]"` → keine Ausgabe.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml .github/workflows/release.yml pyproject.toml
git commit -m "chore: CI und Release-Packaging auf Flet umgestellt"
```

---

### Task 9: Version 2.0.0, Changelog, READMEs, Screenshots

**Files:**
- Modify: `gfc_core.py` (`__version__`), `pyproject.toml` (`version`)
- Modify: `CHANGELOG.md`, `README.md`, `README.en.md`
- Create: `docs/screenshot-dark.png` (Name an vorhandene README-Einbindung anpassen, vorher prüfen mit `grep -n "docs/" README.md`)

**Interfaces:**
- Consumes: fertige App aus Task 4–7.
- Produces: Release-fertiger Stand v2.0.0.

- [ ] **Step 1: Version anheben**

In `gfc_core.py`: `__version__ = "2.0.0"`. In `pyproject.toml`: `version = "2.0.0"`.

- [ ] **Step 2: CHANGELOG-Eintrag**

In `CHANGELOG.md` oben (unter der Kopfzeile, im Stil der bestehenden Einträge) einfügen:

```markdown
## [2.0.0] – 2026-07-18

### Geändert
- **Komplett neue Oberfläche:** GUI von CustomTkinter auf Flet umgestellt –
  GitHub-Look (Dark/Light), Stat-Karten, Tab-Pills, Nutzerliste mit Avataren
  und ⋯-Aktionsmenü, Verlauf als Timeline.
- Kernlogik in `gfc_core.py` und `gfc_controller.py` ausgelagert; CLI
  unverändert nutzbar.
- „Token anzeigen“ ist jetzt das Augen-Symbol im Token-Feld; das
  Rechtsklick-Menü wurde durch das ⋯-Menü pro Zeile ersetzt.

### Entfernt
- Abhängigkeiten `customtkinter` und `pillow` (ersetzt durch `flet`).

### Hinweise
- Einstellungen, Verlauf und Keyring-Token bleiben erhalten (gleiche Pfade).
- Python ≥ 3.10 erforderlich.
```

- [ ] **Step 3: READMEs aktualisieren**

Vorher prüfen, welche Stellen betroffen sind: `grep -n -i "customtkinter\|pillow\|screenshot\|tkinter" README.md README.en.md`. In beiden Dateien: Technologie-Erwähnungen auf Flet umstellen, Installationsabschnitt prüfen (`pip install -r requirements.txt` bleibt korrekt), Screenshot-Verweise auf die neuen Bilder zeigen lassen. Zusätzlich einen Troubleshooting-Hinweis für Linux ergänzen: Flet benötigt auf manchen Distributionen `libmpv` (Fedora: `sudo dnf install mpv-libs`, Debian/Ubuntu: `sudo apt install libmpv2`).

- [ ] **Step 4: Screenshot-Skript schreiben (Scratchpad, nicht ins Repo)**

Datei `<scratchpad>/screenshot_flet.py`:

```python
#!/usr/bin/env python3
"""Screenshot der neuen Flet-GUI mit Fake-Daten (ohne Netzwerk)."""
import importlib.util
import subprocess
import sys
import threading
import time

REPO = "/home/x/Dokumente/Github/GitHub-Follower-Checker"
sys.path.insert(0, REPO)

spec = importlib.util.spec_from_file_location("gui", f"{REPO}/GitHubFollowerCheckerGUI.py")
gui = importlib.util.module_from_spec(spec)
sys.modules["gui"] = gui
spec.loader.exec_module(gui)
gui._save_settings = lambda s: None  # Nutzer-Settings nicht überschreiben


class FakeClient:
    username = "demo-user"
    rate_remaining = 4987
    rate_limit = 5000


def page_main(page):
    view = gui.FollowerCheckerView(settings={"zoom": 1.0, "appearance": "Dark"})
    view.mount(page)
    view.controller.client = FakeClient()
    followers = {f"fan_{i}" for i in range(8)} | {f"mutual_{i}" for i in range(12)}
    following = {f"mutual_{i}" for i in range(12)} | {f"notback_{i}" for i in range(9)}

    def later():
        time.sleep(1.0)
        view.controller.apply_results(followers, following)
        time.sleep(2.0)  # Avatare laden lassen
        subprocess.run(
            ["import", "-window", "GitHub Follower Checker",
             f"{REPO}/docs/screenshot-dark.png"],
            check=False,
        )
        page.window.destroy()

    threading.Thread(target=later, daemon=True).start()


gui.ft.run(page_main)
print("done")
```

Run: `python <scratchpad>/screenshot_flet.py`
Expected: `docs/screenshot-dark.png` zeigt die neue Oberfläche. Falls `import -window` das Flutter-Fenster nicht findet (Titel abweichend), mit `xdotool search --name Follower getwindowname` den exakten Titel ermitteln. Screenshot mit dem Read-Tool ansehen und Layout prüfen (Sidebar vollständig, Liste mit Avataren, Aktionsleiste unten). Bei Bedarf hell/`Light` wiederholen, falls das README beide zeigt.

- [ ] **Step 5: End-to-End-Verifikation**

1. `python -m pytest -q && ruff check .` → grün.
2. `python GitHubFollowerCheckerGUI.py` → App startet; Sichtprüfung: Theme-Wechsel Dark→Light, Zoom 125 %, Sprache EN (Hinweistext), Fenster schließen und neu öffnen (Größe gemerkt).
3. `python GitHubFollowerCheckerCLI.py --help` → Hilfe erscheint, Version 2.0.0 via `--version`.

- [ ] **Step 6: Commit**

```bash
git add gfc_core.py pyproject.toml CHANGELOG.md README.md README.en.md docs/
git commit -m "chore(release): v2.0.0 – Flet-Redesign, Changelog, READMEs, Screenshots"
```

---

## Offene Punkte für die Ausführung

- **Flet-Thread-Verhalten real prüfen:** Die Worker rufen View-Callbacks aus Hintergrund-Threads auf; `page.update()` ist in Flet 0.8x thread-tauglich. Beim ersten manuellen Lauf (Task 4 Step 7 / Task 5 Step 5) gezielt prüfen, dass Statusmeldungen während einer echten Analyse ankommen. Falls nicht: Callbacks in der View mit `page.run_thread` bzw. der Flet-Dokumentation zu Thread-Updates abgleichen.
- **`flet pack` unter Windows/Linux:** Erst beim ersten Tag-Release sichtbar; falls der Build fehlschlägt, `flet pack --help` der installierten flet-cli-Version konsultieren (Optionen ändern sich zwischen Minor-Versionen).
- **Memory-Notiz aktualisieren:** Nach Abschluss die gespeicherte Screenshot-Anleitung (`gui-screenshot-verification.md`) auf das neue Flet-Verfahren umschreiben (Tk-Rezept gilt nicht mehr).

