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
