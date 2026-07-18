# -*- coding: utf-8 -*-
"""Tests für den GitHub Follower Checker.

Die Logik-Tests laufen headless. Der GUI-Test benötigt ein Display –
lokal reicht DISPLAY=:0, in der CI läuft er unter xvfb-run.
"""
import importlib.util
import os
from pathlib import Path

import pytest
import requests

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def gui():
    spec = importlib.util.spec_from_file_location(
        "gui_under_test", REPO / "GitHubFollowerCheckerGUI.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def make_client(gui, responses):
    client = gui.GitHubClient("demo-user", "demo-token")
    client.session = FakeSession(responses)
    return client


# ------------------------------------------------------------ GitHubClient


def test_unfollow_success(gui):
    client = make_client(gui, [FakeResponse(204)])
    assert client.unfollow("foo") == (True, "✓ Entfolgt")
    assert client.session.calls == [("DELETE", f"{gui.BASE_URL}/user/following/foo")]


def test_unfollow_error(gui):
    client = make_client(gui, [FakeResponse(404)])
    assert client.unfollow("foo") == (False, "Fehler (HTTP 404)")


def test_follow_success(gui):
    client = make_client(gui, [FakeResponse(204)])
    assert client.follow("foo") == (True, "✓ Gefolgt")
    assert client.session.calls == [("PUT", f"{gui.BASE_URL}/user/following/foo")]


def test_rate_limit_raises(gui):
    limited = FakeResponse(
        403,
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1750000000"},
    )
    client = make_client(gui, [limited])
    with pytest.raises(gui.RateLimitError) as excinfo:
        client.unfollow("foo")
    assert excinfo.value.reset_time is not None


def test_fetch_all_users_paginates(gui):
    pages = [
        FakeResponse(200, json_data=[{"login": "a"}, {"login": "b"}]),
        FakeResponse(200, json_data=[{"login": "c"}]),
        FakeResponse(200, json_data=[]),
    ]
    client = make_client(gui, pages)
    assert client.fetch_all_users("users/demo-user/followers") == {"a", "b", "c"}
    assert len(client.session.calls) == 3


# ------------------------------------------------------- Verlauf & Delta


def test_compute_follower_delta(gui):
    gained, lost = gui.compute_follower_delta({"Alice", "bob"}, {"bob", "carol", "Zed"})
    assert gained == ["carol", "Zed"]
    assert lost == ["Alice"]


def test_compute_follower_delta_unchanged(gui):
    assert gui.compute_follower_delta({"a"}, {"a"}) == ([], [])


def test_history_roundtrip(gui, tmp_path, monkeypatch):
    monkeypatch.setattr(gui, "HISTORY_PATH", tmp_path / "history.json")
    data = {"demo-user": {"timestamp": "2026-07-18T06:00:00", "followers": ["a"]}}
    gui._save_history(data)
    assert gui._load_history() == data


def test_history_corrupt_file(gui, tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    path.write_text("kein json", encoding="utf-8")
    monkeypatch.setattr(gui, "HISTORY_PATH", path)
    assert gui._load_history() == {}


# ------------------------------------------------------------- GUI-Smoke


class FakeClient:
    username = "demo-user"

    def unfollow(self, user):
        return True, "✓ Entfolgt"

    def follow(self, user):
        return True, "✓ Gefolgt"


class ImmediateThread:
    """Thread-Ersatz: führt das Target synchron im Main-Thread aus.

    Ohne laufenden mainloop() darf kein Nebenthread after() aufrufen –
    synchron ausgeführt landen alle _ui-Aufrufe in der after-Queue des
    Main-Threads und werden per app.update() abgearbeitet.
    """

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


@pytest.mark.skipif(
    not os.environ.get("DISPLAY"),
    reason="Benötigt ein Display (lokal DISPLAY setzen, CI nutzt xvfb-run)",
)
def test_gui_end_to_end(gui, tmp_path, monkeypatch):
    monkeypatch.setattr(gui, "_load_settings", lambda: {"zoom": 1.0, "appearance": "Dark"})
    monkeypatch.setattr(gui, "_save_settings", lambda settings: None)
    monkeypatch.setattr(gui, "HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(gui, "ACTION_DELAY", 0.01)
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(gui.messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(gui.messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(gui.threading, "Thread", ImmediateThread)

    app = gui.FollowerCheckerApp()
    try:
        app.update()
        app.client = FakeClient()
        app._apply_results(
            {"alice", "bob", "carol", "dave"}, {"bob", "carol", "erin", "frank"}
        )
        app.update()

        # Statistiken inkl. neuem Fans-Wert
        assert app.stat_values["followers"].cget("text") == "4"
        assert app.stat_values["fans"].cget("text") == "2"
        assert sorted(app.rows["fans"], key=lambda r: r["user"])[0]["user"] == "alice"

        # Verlauf: erste Analyse angekündigt, Datei geschrieben
        assert "Erste Analyse" in app.delta_label.cget("text")
        assert "demo-user" in gui._load_history()

        # Zweite Analyse: Delta wird angezeigt
        app._apply_results(
            {"alice", "bob", "carol", "neu-nutzer"}, {"bob", "carol", "erin", "frank"}
        )
        app.update()
        assert "+1 Follower: neu-nutzer" in app.delta_label.cget("text")
        assert "−1 Follower: dave" in app.delta_label.cget("text")

        # Suche filtert die Tabelle
        app.segment.set("Following")
        app._on_tab_change("Following")
        app.search_entry.insert(0, "bo")
        app._populate_tree()
        assert list(app.tree.get_children()) == ["bob"]
        app.search_entry.delete(0, "end")
        app._populate_tree()
        assert len(app.tree.get_children()) == 4

        # Whitelist schützt vor dem Bulk-Entfolgen
        app._set_protected(["erin"], True)
        assert app.unfollow_candidates == ["frank"]
        assert app.tree.set("erin", "user").startswith("🛡 ")
        app._set_protected(["erin"], False)
        assert sorted(app.unfollow_candidates) == ["erin", "frank"]

        # Auswahl entfolgen (zwei Mutuals)
        app.tree.selection_set(["bob", "carol"])
        app.update()
        assert "(2)" in app.unfollow_selected_button.cget("text")
        app.confirm_unfollow_selection()
        app.update()
        assert "Fertig: 2 entfolgt." in app.status_label.cget("text")
        assert "bob" not in app.following
        assert app.tree.set("bob", "status") == "✓ Entfolgt"
        assert app.tree.set("bob", "you_follow") == "–"
        assert app.undo_button.winfo_ismapped()
        assert "(2)" in app.undo_button.cget("text")

        # Rückgängig folgt beiden wieder
        app.undo_unfollow()
        app.update()
        assert "Fertig: 2 gefolgt." in app.status_label.cget("text")
        assert {"bob", "carol"} <= app.following
        assert app.tree.set("bob", "status") == "✓ Gefolgt"
        assert app.tree.set("bob", "you_follow") == "✓"
        app.update()
        assert not app.undo_button.winfo_ismapped()
    finally:
        app.destroy()
