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

__version__ = "2.0.0"

KEYRING_SERVICE = "github-follower-checker"

BASE_URL = "https://api.github.com"

# Pause zwischen Folgen/Entfolgen-Requests. Bewusst konservativ (30 Schreib-
# Aktionen pro Minute), um GitHubs Sekundär-Rate-Limits sicher zu unterschreiten.
ACTION_DELAY = 2.0

# Nur Darstellungs-Einstellungen (Zoom, Theme, Sprache, Fenster, Whitelist) –
# niemals Zugangsdaten!
SETTINGS_PATH = Path.home() / ".config" / "github-follower-checker" / "settings.json"

# Letzter Analyse-Stand pro Nutzer (nur Nutzernamen, kein Token)
HISTORY_PATH = SETTINGS_PATH.parent / "history.json"


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


# --------------------------------------------------------------- Sprache

def _detect_language(settings: dict) -> str:
    """Ermittelt die UI-Sprache: Einstellung > GFC_LANG > Systemsprache."""
    choice = str(settings.get("language", "auto")).lower()
    if choice in ("de", "en"):
        return choice
    env = os.environ.get("GFC_LANG", "").lower()
    if env in ("de", "en"):
        return env
    try:
        import locale

        system = locale.getlocale()[0] or os.environ.get("LANG", "")
    except Exception:
        system = os.environ.get("LANG", "")
    return "de" if str(system).lower().startswith("de") else "en"


# Deutsche Texte sind die Quelle; hier stehen die englischen Übersetzungen.
_EN = {
    "GitHub-Beziehungen analysieren": "Analyze your GitHub relationships",
    "ZUGANGSDATEN": "CREDENTIALS",
    "Token merken (Schlüsselbund)": "Remember token (keyring)",
    "Analyse starten": "Start analysis",
    "Bereit. Gib Username und Token ein.": "Ready. Enter your username and token.",
    "ERGEBNIS": "RESULTS",
    "SEIT LETZTER ANALYSE": "SINCE LAST ANALYSIS",
    "Noch kein Vergleich vorhanden.": "No comparison available yet.",
    "Folgen nicht zurück": "Don't follow back",
    "Fans": "Fans",
    "Follower": "Followers",
    "Following": "Following",
    "Verlauf": "History",
    "Folgt dir": "Follows you",
    "Du folgst": "You follow",
    "⬇  CSV exportieren": "⬇  Export CSV",
    "Noch keine Daten.\nStarte links eine Analyse.": "No data yet.\nStart an analysis on the left.",
    "Keine Treffer für „{term}“.": "No matches for “{term}”.",
    "🚫 Alle Nicht-Folgenden": "🚫 All non-followers",
    "Auswahl entfolgen": "Unfollow selected",
    "↩ Rückgängig": "↩ Undo",
    "API-Limit": "API limit",
    "Eingabe fehlt": "Missing input",
    "Bitte gib Username und Token ein.": "Please enter username and token.",
    "Validiere Zugangsdaten…": "Validating credentials…",
    "Lade Follower…": "Loading followers…",
    "Lade Follower… (Seite {page})": "Loading followers… (page {page})",
    "Lade Following…": "Loading following…",
    "Lade Following… (Seite {page})": "Loading following… (page {page})",
    "Analyse abgeschlossen: {n} Nutzer folgen dir nicht zurück.": "Analysis complete: {n} users don't follow you back.",
    "Analyse abgeschlossen: Alle folgen dir zurück. 🎉": "Analysis complete: everyone follows you back. 🎉",
    "Fehler": "Error",
    "Token ungültig oder abgelaufen. Prüfe auch den Scope „user:follow“.": "Token invalid or expired. Also check the “user:follow” scope.",
    "GitHub-API-Fehler (HTTP {code}).{hint}": "GitHub API error (HTTP {code}).{hint}",
    " Existiert der Username?": " Does the username exist?",
    "Keine Verbindung zur GitHub-API. Prüfe deine Internetverbindung.": "No connection to the GitHub API. Check your internet connection.",
    "GitHub-Rate-Limit": "GitHub rate limit",
    "Das GitHub-API-Limit ist erreicht.\n\nNeue Anfragen sind ab {time} Uhr möglich.": "The GitHub API limit has been reached.\n\nNew requests are possible from {time}.",
    "Das GitHub-API-Limit ist erreicht.\n\nBitte warte einige Minuten und versuche es erneut.": "The GitHub API limit has been reached.\n\nPlease wait a few minutes and try again.",
    "GitHub-Rate-Limit erreicht – bitte später erneut versuchen.": "GitHub rate limit reached – please try again later.",
    "Zugangsdaten aus dem Schlüsselbund geladen.": "Credentials loaded from the keyring.",
    "Entfolgen bestätigen": "Confirm unfollow",
    "Wirklich „{user}“ entfolgen (folgt dir nicht zurück)?": "Really unfollow “{user}” (doesn't follow you back)?",
    "Wirklich allen {n} Nutzern entfolgen, die dir nicht zurückfolgen?": "Really unfollow all {n} users who don't follow you back?",
    "Wirklich „{user}“ entfolgen?": "Really unfollow “{user}”?",
    "Wirklich {n} ausgewählten Nutzern entfolgen?\n\n{shown}": "Really unfollow {n} selected users?\n\n{shown}",
    " … und {n} weitere": " … and {n} more",
    "\n\nDiese Aktion kann nicht rückgängig gemacht werden.": "\n\nThis action cannot be undone.",
    "\n\n🛡 {n} geschützte Nutzer werden übersprungen.": "\n\n🛡 {n} protected users will be skipped.",
    "Nichts zu tun": "Nothing to do",
    "Es gibt keine Nutzer zum Entfolgen.": "There are no users to unfollow.",
    "Keine Analyse": "No analysis",
    "Starte zuerst eine Analyse.": "Run an analysis first.",
    "Keine Auswahl": "No selection",
    "Markiere in der Tabelle Nutzer, denen du aktuell folgst.": "Select users in the table that you currently follow.",
    "Entfolge Nutzer…": "Unfollowing users…",
    "Entfolge Nutzer… {idx}/{total}": "Unfollowing users… {idx}/{total}",
    "Folge Nutzern…": "Following users…",
    "Folge Nutzern… {idx}/{total}": "Following users… {idx}/{total}",
    "✓ Entfolgt": "✓ Unfollowed",
    "✓ Gefolgt": "✓ Followed",
    "Fehler (HTTP {code})": "Error (HTTP {code})",
    "Netzwerkfehler": "Network error",
    "Übersprungen (Rate-Limit)": "Skipped (rate limit)",
    "{n} entfolgt": "{n} unfollowed",
    "{n} gefolgt": "{n} followed",
    "{n} fehlgeschlagen": "{n} failed",
    "Fertig: ": "Done: ",
    "Erste Analyse gespeichert – Veränderungen siehst du beim nächsten Lauf.": "First analysis saved – you'll see changes on the next run.",
    "Keine Follower-Veränderung seit {when}.": "No follower changes since {when}.",
    "Seit {when}:": "Since {when}:",
    "+{n} Follower: {names}": "+{n} followers: {names}",
    "−{n} Follower: {names}": "−{n} followers: {names}",
    "+ folgt dir seit {when}": "+ follows you since {when}",
    "− entfolgte dich am {when}": "− unfollowed you on {when}",
    "unbekannt": "unknown",
    "letzter Analyse": "the last analysis",
    "Profil im Browser öffnen": "Open profile in browser",
    "dabei seit": "joined",
    "Keine Daten": "No data",
    "Starte zuerst eine Analyse – es gibt noch nichts zu exportieren.": "Run an analysis first – there is nothing to export yet.",
    "Ergebnis als CSV speichern": "Save results as CSV",
    "folgt_dir": "follows_you",
    "du_folgst": "you_follow",
    "ja": "yes",
    "nein": "no",
    "CSV gespeichert: {path}": "CSV saved: {path}",
    "Export fehlgeschlagen": "Export failed",
    "Datei konnte nicht gespeichert werden: {err}": "File could not be saved: {err}",
    "Abbrechen": "Cancel",
    "Folgen": "Follow",
    "Entfolgen": "Unfollow",
    "🛡 Schützen / Schutz aufheben": "🛡 Protect / unprotect",
    "Nutzer filtern…": "Filter users…",
    "Tipp: Checkboxen wählen mehrere Nutzer aus, ⋯ öffnet Aktionen.": "Tip: checkboxes select multiple users, ⋯ opens actions.",
    "➕ Fans zurückfolgen": "➕ Follow fans back",
    "Folgen bestätigen": "Confirm follow",
    "{n} Fans zurückfolgen, die dir bereits folgen?": "Follow back {n} fans who already follow you?",
    # CLI
    "Analysiert GitHub-Follower/Following-Beziehungen und kann Nutzern entfolgen, die nicht zurückfolgen.": "Analyzes GitHub follower/following relationships and can unfollow users who don't follow back.",
    "GitHub-Username, der analysiert wird": "GitHub username to analyze",
    "Personal Access Token (alternativ: Umgebungsvariable GITHUB_TOKEN oder sichere interaktive Abfrage)": "personal access token (alternatively: GITHUB_TOKEN environment variable or a secure interactive prompt)",
    "entfolgt allen Nicht-Zurückfolgenden (die 🛡-Whitelist der GUI wird übersprungen)": "unfollows everyone who doesn't follow back (users on the GUI's 🛡 whitelist are skipped)",
    "Sicherheitsabfrage beim Entfolgen überspringen (für Skripte)": "skip the unfollow confirmation (for scripts)",
    "Analyse-Ergebnis als JSON ausgeben": "print the analysis result as JSON",
    "nur das Endergebnis ausgeben": "only print the final result",
    "Fehler: Kein Token – per --token oder GITHUB_TOKEN übergeben.": "Error: no token – pass it via --token or GITHUB_TOKEN.",
    "Fehler: Token ungültig oder abgelaufen (Scope user:follow nötig).": "Error: token invalid or expired (user:follow scope required).",
    " – frei ab {time}": " – resets at {time}",
    "Fehler: GitHub-Rate-Limit erreicht{when}.": "Error: GitHub rate limit reached{when}.",
    "Fehler: GitHub-API-Fehler (HTTP {code}).{hint}": "Error: GitHub API error (HTTP {code}).{hint}",
    "Fehler: Keine Verbindung zur GitHub-API.": "Error: no connection to the GitHub API.",
    "{user}: {followers} Follower, {following} Following, {notback} folgen nicht zurück, {fans} Fans.": "{user}: {followers} followers, {following} following, {notback} don't follow back, {fans} fans.",
    "\nFolgen nicht zurück:": "\nDon't follow back:",
    "Niemand zu entfolgen.": "No one to unfollow.",
    " (alle geschützt)": " (all protected)",
    "\n{n} Nutzern wirklich entfolgen? Das kann nicht rückgängig gemacht werden. [ja/NEIN] ": "\nReally unfollow {n} users? This cannot be undone. [yes/NO] ",
    "Abgebrochen.": "Aborted.",
    "Abbruch: GitHub-Rate-Limit erreicht{when}.": "Aborted: GitHub rate limit reached{when}.",
    "Fertig: {ok} entfolgt, {errors} Fehler.": "Done: {ok} unfollowed, {errors} errors.",
}

_LANG = _detect_language(_load_settings())


def tr(text: str) -> str:
    """Übersetzt einen deutschen UI-Text in die aktive Sprache."""
    if _LANG == "en":
        return _EN.get(text, text)
    return text


def set_language(lang: str) -> None:
    """Schaltet die UI-Sprache zur Laufzeit um ("de"/"en")."""
    global _LANG
    if lang in ("de", "en"):
        _LANG = lang


# Anzahl gespeicherter Analyse-Stände pro Nutzer
HISTORY_LIMIT = 50


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
            return True, tr("✓ Entfolgt")
        return False, tr("Fehler (HTTP {code})").format(code=response.status_code)

    def follow(self, user: str) -> tuple:
        response = self.session.put(
            f"{BASE_URL}/user/following/{user}", timeout=10
        )
        self._raise_for_rate_limit(response)
        if response.status_code == 204:
            return True, tr("✓ Gefolgt")
        return False, tr("Fehler (HTTP {code})").format(code=response.status_code)

    def get_user(self, user: str) -> dict:
        response = self.session.get(f"{BASE_URL}/users/{user}", timeout=10)
        self._raise_for_rate_limit(response)
        response.raise_for_status()
        return response.json()
