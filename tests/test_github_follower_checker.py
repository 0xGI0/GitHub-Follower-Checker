# -*- coding: utf-8 -*-
"""Tests für den GitHub Follower Checker.

Alle Tests – inklusive der Flet-View-Tests – laufen headless, ohne
Display-Abhängigkeit.
"""
import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

REPO = Path(__file__).resolve().parents[1]

# Tests prüfen deutsche UI-Texte – Sprache unabhängig vom System pinnen
os.environ.setdefault("GFC_LANG", "de")


@pytest.fixture(scope="session")
def core():
    sys.path.insert(0, str(REPO))
    import gfc_core

    return gfc_core


@pytest.fixture(scope="session")
def cli(core):
    sys.path.insert(0, str(REPO))
    import GitHubFollowerCheckerCLI

    return GitHubFollowerCheckerCLI


class FakeResponse:
    def __init__(self, status=204, json_data=None, headers=None):
        self.status_code = status
        self._json = [] if json_data is None else json_data
        self.headers = headers or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)


class FakeSession:
    """Gibt vorbereitete Antworten der Reihe nach zurück."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def _next(self, method, url, **kwargs):
        self.calls.append((method, url))
        return self.responses.pop(0)

    def get(self, url, **kwargs):
        return self._next("GET", url, **kwargs)

    def put(self, url, **kwargs):
        return self._next("PUT", url, **kwargs)

    def delete(self, url, **kwargs):
        return self._next("DELETE", url, **kwargs)


def make_client(core, responses):
    client = core.GitHubClient("demo-user", "demo-token")
    client.session = FakeSession(responses)
    return client


# ------------------------------------------------------------ GitHubClient


def test_unfollow_success(core):
    client = make_client(core, [FakeResponse(204)])
    assert client.unfollow("foo") == (True, "✓ Entfolgt")
    assert client.session.calls == [("DELETE", f"{core.BASE_URL}/user/following/foo")]


def test_unfollow_error(core):
    client = make_client(core, [FakeResponse(404)])
    assert client.unfollow("foo") == (False, "Fehler (HTTP 404)")


def test_follow_success(core):
    client = make_client(core, [FakeResponse(204)])
    assert client.follow("foo") == (True, "✓ Gefolgt")
    assert client.session.calls == [("PUT", f"{core.BASE_URL}/user/following/foo")]


def test_rate_limit_raises(core):
    limited = FakeResponse(
        403,
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1750000000"},
    )
    client = make_client(core, [limited])
    with pytest.raises(core.RateLimitError) as excinfo:
        client.unfollow("foo")
    assert excinfo.value.reset_time is not None


def test_get_user(core):
    client = make_client(
        core, [FakeResponse(200, json_data={"login": "foo", "name": "Foo Bar"})]
    )
    assert client.get_user("foo")["name"] == "Foo Bar"
    assert client.session.calls == [("GET", f"{core.BASE_URL}/users/foo")]


def test_rate_limit_tracking(core):
    headers = {"X-RateLimit-Remaining": "4999", "X-RateLimit-Limit": "5000"}
    client = make_client(core, [FakeResponse(204, headers=headers)])
    client.unfollow("foo")
    assert (client.rate_remaining, client.rate_limit) == (4999, 5000)


def test_fetch_all_users_paginates(core):
    pages = [
        FakeResponse(200, json_data=[{"login": "a"}, {"login": "b"}]),
        FakeResponse(200, json_data=[{"login": "c"}]),
        FakeResponse(200, json_data=[]),
    ]
    client = make_client(core, pages)
    assert client.fetch_all_users("users/demo-user/followers") == {"a", "b", "c"}
    assert len(client.session.calls) == 3


# ------------------------------------------------------- Verlauf & Delta


def test_compute_follower_delta(core):
    gained, lost = core.compute_follower_delta({"Alice", "bob"}, {"bob", "carol", "Zed"})
    assert gained == ["carol", "Zed"]
    assert lost == ["Alice"]


def test_compute_follower_delta_unchanged(core):
    assert core.compute_follower_delta({"a"}, {"a"}) == ([], [])


def test_history_roundtrip(core, tmp_path, monkeypatch):
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    data = {"demo-user": {"timestamp": "2026-07-18T06:00:00", "followers": ["a"]}}
    core._save_history(data)
    assert core._load_history() == data


def test_history_corrupt_file(core, tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    path.write_text("kein json", encoding="utf-8")
    monkeypatch.setattr(core, "HISTORY_PATH", path)
    assert core._load_history() == {}


def test_language_detection(core, monkeypatch):
    assert core._detect_language({"language": "en"}) == "en"
    assert core._detect_language({"language": "de"}) == "de"
    monkeypatch.setenv("GFC_LANG", "en")
    assert core._detect_language({}) == "en"


def test_translation_lookup(core, monkeypatch):
    assert core.tr("Analyse starten") == "Analyse starten"  # de gepinnt
    monkeypatch.setattr(core, "_LANG", "en")
    assert core.tr("Analyse starten") == "Start analysis"
    assert core.tr("✓ Entfolgt") == "✓ Unfollowed"
    assert core.tr("unbekannter Schlüssel") == "unbekannter Schlüssel"


def test_translations_nonempty(core):
    assert all(value.strip() for value in core._EN.values())


def test_history_normalizes_old_format(core):
    old = {"timestamp": "2026-07-14T10:00:00", "followers": ["a"]}
    assert core._normalize_history_entries(old) == [old]
    assert core._normalize_history_entries([old]) == [old]
    assert core._normalize_history_entries(None) == []


# ------------------------------------------------------------------- CLI


class CLIFakeClient:
    def __init__(self, username, token):
        self.username = username
        self.unfollowed = []

    def validate_credentials(self):
        pass

    def fetch_all_users(self, endpoint):
        if endpoint.endswith("/followers"):
            return {"anna", "berta", "chris"}
        return {"berta", "chris", "dora"}

    def unfollow(self, user):
        self.unfollowed.append(user)
        return True, "✓ Entfolgt"


def test_cli_json_output(cli, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_load_settings", lambda: {})
    rc = cli.main(["demo", "--token", "t", "--json"], client_factory=CLIFakeClient)
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert data["not_following_back"] == ["dora"]
    assert data["fans"] == ["anna"]
    assert data["followers"] == 3


def test_cli_unfollow_respects_whitelist(cli, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_load_settings", lambda: {"whitelist": ["dora"]})
    monkeypatch.setattr(cli, "ACTION_DELAY", 0)
    rc = cli.main(
        ["demo", "--token", "t", "--unfollow", "--yes"], client_factory=CLIFakeClient
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "🛡 dora" in out
    assert "Niemand zu entfolgen" in out


def test_cli_unfollow_yes(cli, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_load_settings", lambda: {})
    monkeypatch.setattr(cli, "ACTION_DELAY", 0)
    rc = cli.main(
        ["demo", "--token", "t", "--unfollow", "--yes", "--quiet"],
        client_factory=CLIFakeClient,
    )
    assert rc == 0
    assert "Fertig: 1 entfolgt, 0 Fehler." in capsys.readouterr().out


def test_cli_requires_token(cli, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    rc = cli.main(["demo"], client_factory=CLIFakeClient)
    assert rc == 2
    assert "Kein Token" in capsys.readouterr().err


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


class ImmediateCtrlThread:
    """Thread-Ersatz: führt das Target synchron aus (für Controller-Tests)."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


class _ImmediateThreadingModule:
    """threading-Ersatz nur für gfc_controller (Thread → ImmediateCtrlThread).

    Patcht die Namensbindung `controller_mod.threading` statt das echte
    threading-Modul zu mutieren (monkeypatch.setattr(controller_mod.threading,
    "Thread", ...) würde sonst global threading.Thread ersetzen und damit
    auch threading.Timer kaputt machen, das die View fürs Profil-Panel-
    Debounce nutzt – Timer.__init__ ruft intern Thread.__init__ auf).
    """

    Thread = ImmediateCtrlThread


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
    monkeypatch.setattr(controller_mod, "threading", _ImmediateThreadingModule)
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
    assert '„bob“' in single
    many = controller_mod.AppController.selection_question([f"u{i}" for i in range(10)])
    assert "… und 2 weitere" in many


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


def test_view_end_to_end(viewmod, controller_mod, core, monkeypatch, tmp_path):
    """Portierung des alten Tk-Smoke-Tests: Analyse → Entfolgen → Undo."""
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(controller_mod, "threading", _ImmediateThreadingModule)
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


def test_view_menu_targets_union(viewmod, controller_mod, core, monkeypatch, tmp_path):
    """⋯-Menü wirkt auf Auswahl ∪ angeklickte Zeile, gefiltert nach Aktion."""
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(controller_mod, "threading", _ImmediateThreadingModule)
    monkeypatch.setattr(controller_mod, "ACTION_DELAY", 0)
    view = demo_view(viewmod, monkeypatch)
    monkeypatch.setattr(
        view, "_confirm", lambda title, q, label, on_confirm: on_confirm()
    )

    # Entfolgen: Auswahl {bob, carol} + Klickzeile erin → alle drei entfolgt
    view.on_tab("following")
    view.on_select_row("bob", True)
    view.on_select_row("carol", True)
    view.on_menu_unfollow("erin")
    assert not {"bob", "carol", "erin"} & view.controller.following
    assert "frank" in view.controller.following

    # Folgen: Auswahl {alice} + Klickzeile dave → beiden gefolgt (waren Fans)
    view.on_tab("fans")
    view.on_select_row("alice", True)
    view.on_menu_follow("dave")
    assert {"alice", "dave"} <= view.controller.following


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


def test_filepicker_save_file_is_async():
    """Schutz: on_export awaitet save_file – bricht, falls flet die API ändert."""
    import inspect

    import flet as ft

    assert inspect.iscoroutinefunction(ft.FilePicker.save_file)


def test_view_language_switch_live(viewmod, core, monkeypatch):
    """Sprachwechsel wirkt sofort – ohne Neustart."""
    monkeypatch.setattr(core, "_LANG", core._LANG)  # Original nach Test wiederherstellen
    view = make_view(viewmod, monkeypatch)
    assert view.tab_labels["unfollower"].value == "Folgen nicht zurück"
    view.on_language(SimpleNamespace(control=SimpleNamespace(value="EN")))
    assert core._LANG == "en"
    assert view.tab_labels["unfollower"].value == "Don't follow back"
    assert view.settings["language"] == "en"
    view.on_language(SimpleNamespace(control=SimpleNamespace(value="DE")))
    assert view.tab_labels["unfollower"].value == "Folgen nicht zurück"
    view.on_language(SimpleNamespace(control=SimpleNamespace(value="EN")))
    assert view.status_text.value == "Ready. Enter your username and token."
    assert view.delta_text.value == "No comparison available yet."


def test_view_language_switch_after_analysis(viewmod, core, monkeypatch, tmp_path):
    """Auch Status- und Delta-Zeile wechseln sofort die Sprache."""
    monkeypatch.setattr(core, "HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(core, "_LANG", core._LANG)
    view = demo_view(viewmod, monkeypatch)
    view.on_language(SimpleNamespace(control=SimpleNamespace(value="EN")))
    assert "First analysis saved" in view.delta_text.value
    assert "2 users don't follow you back" in view.status_text.value


def test_candidates_language_independent(controller_mod, monkeypatch, core):
    """Bereits Entfolgte bleiben nach Sprachwechsel ausgeschlossen."""
    monkeypatch.setattr(core, "_LANG", core._LANG)
    ctrl, ui = make_controller(controller_mod, monkeypatch)
    ctrl.apply_results({"a"}, {"erin", "frank"})
    ctrl.mark_unfollowed("erin")
    ctrl.set_row_status("erin", "✓ Entfolgt")
    core.set_language("en")
    assert ctrl.compute_candidates() == ["frank"]


def test_controller_busy_guard(controller_mod, monkeypatch):
    """Während ein Worker läuft, starten start_* keine zweiten Worker."""
    ctrl, ui = make_controller(controller_mod, monkeypatch)
    ctrl.client = CtrlFakeClient()
    ctrl.busy = True
    ctrl.start_analysis("demo-user", "tok")
    ctrl.start_unfollow(["x"])
    ctrl.start_follow(["x"])
    assert ui.calls == []
