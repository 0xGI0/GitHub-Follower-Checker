#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub Follower Checker – CLI.

Analysiert Follower/Following über die GitHub REST API v3 und kann optional
allen Nutzern entfolgen, die nicht zurückfolgen. Das Token kommt per
--token, aus der Umgebungsvariable GITHUB_TOKEN oder wird sicher abgefragt –
es steht niemals im Quellcode. Die Whitelist der GUI (geschützte Nutzer)
wird beachtet. Die Ausgabesprache folgt der GUI-Einstellung bzw. der
Systemsprache (Deutsch/Englisch).
"""
import argparse
import getpass
import json
import os
import sys
import time

import requests

from gfc_core import (
    ACTION_DELAY,
    AuthError,
    GitHubClient,
    RateLimitError,
    __version__,
    _load_settings,
    tr,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github-follower-checker-cli",
        description=tr(
            "Analysiert GitHub-Follower/Following-Beziehungen und kann "
            "Nutzern entfolgen, die nicht zurückfolgen."
        ),
    )
    parser.add_argument("username", help=tr("GitHub-Username, der analysiert wird"))
    parser.add_argument(
        "--token",
        help=tr(
            "Personal Access Token (alternativ: Umgebungsvariable "
            "GITHUB_TOKEN oder sichere interaktive Abfrage)"
        ),
    )
    parser.add_argument(
        "--unfollow",
        action="store_true",
        help=tr(
            "entfolgt allen Nicht-Zurückfolgenden "
            "(die 🛡-Whitelist der GUI wird übersprungen)"
        ),
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help=tr("Sicherheitsabfrage beim Entfolgen überspringen (für Skripte)"),
    )
    parser.add_argument(
        "--json", action="store_true", help=tr("Analyse-Ergebnis als JSON ausgeben")
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true", help=tr("nur das Endergebnis ausgeben")
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def main(argv=None, client_factory=GitHubClient) -> int:
    args = build_parser().parse_args(argv)

    def say(message):
        if not args.quiet and not args.json:
            print(message)

    token = args.token or os.environ.get("GITHUB_TOKEN", "").strip()
    if not token and sys.stdin.isatty():
        token = getpass.getpass("Personal Access Token: ").strip()
    if not token:
        print(
            tr("Fehler: Kein Token – per --token oder GITHUB_TOKEN übergeben."),
            file=sys.stderr,
        )
        return 2

    client = client_factory(args.username, token)
    try:
        client.validate_credentials()
        say(tr("Lade Follower…"))
        followers = client.fetch_all_users(f"users/{args.username}/followers")
        say(tr("Lade Following…"))
        following = client.fetch_all_users(f"users/{args.username}/following")
    except AuthError:
        print(
            tr("Fehler: Token ungültig oder abgelaufen (Scope user:follow nötig)."),
            file=sys.stderr,
        )
        return 1
    except RateLimitError as err:
        when = (
            tr(" – frei ab {time}").format(time=f"{err.reset_time:%H:%M}")
            if err.reset_time
            else ""
        )
        print(
            tr("Fehler: GitHub-Rate-Limit erreicht{when}.").format(when=when),
            file=sys.stderr,
        )
        return 1
    except requests.HTTPError as err:
        code = err.response.status_code if err.response is not None else "?"
        hint = tr(" Existiert der Username?") if code == 404 else ""
        print(
            tr("Fehler: GitHub-API-Fehler (HTTP {code}).{hint}").format(
                code=code, hint=hint
            ),
            file=sys.stderr,
        )
        return 1
    except requests.RequestException:
        print(tr("Fehler: Keine Verbindung zur GitHub-API."), file=sys.stderr)
        return 1

    whitelist = set(_load_settings().get("whitelist", []))
    not_following_back = sorted(following - followers, key=str.lower)
    fans = sorted(followers - following, key=str.lower)
    candidates = [u for u in not_following_back if u not in whitelist]
    skipped = [u for u in not_following_back if u in whitelist]

    if args.json:
        print(
            json.dumps(
                {
                    "username": args.username,
                    "followers": len(followers),
                    "following": len(following),
                    "not_following_back": not_following_back,
                    "fans": fans,
                    "whitelist_skipped": skipped,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(
            tr(
                "{user}: {followers} Follower, {following} Following, "
                "{notback} folgen nicht zurück, {fans} Fans."
            ).format(
                user=args.username,
                followers=len(followers),
                following=len(following),
                notback=len(not_following_back),
                fans=len(fans),
            )
        )
        if not_following_back and not args.quiet:
            print(tr("\nFolgen nicht zurück:"))
            for user in not_following_back:
                marker = "  🛡 " if user in skipped else "  – "
                print(marker + user)

    if not args.unfollow:
        return 0

    if not candidates:
        say(tr("Niemand zu entfolgen.") + (tr(" (alle geschützt)") if skipped else ""))
        return 0
    if not args.yes:
        answer = input(
            tr(
                "\n{n} Nutzern wirklich entfolgen? "
                "Das kann nicht rückgängig gemacht werden. [ja/NEIN] "
            ).format(n=len(candidates))
        )
        if answer.strip().lower() not in ("ja", "j", "yes", "y"):
            print(tr("Abgebrochen."))
            return 0

    errors = 0
    for index, user in enumerate(candidates, 1):
        try:
            ok, status = client.unfollow(user)
        except RateLimitError as err:
            when = (
                tr(" – frei ab {time}").format(time=f"{err.reset_time:%H:%M}")
                if err.reset_time
                else ""
            )
            print(
                tr("Abbruch: GitHub-Rate-Limit erreicht{when}.").format(when=when),
                file=sys.stderr,
            )
            return 1
        except requests.RequestException:
            ok, status = False, tr("Netzwerkfehler")
        if not ok:
            errors += 1
        if not args.quiet:
            print(f"[{index}/{len(candidates)}] {user}: {status}")
        time.sleep(ACTION_DELAY)

    print(
        tr("Fertig: {ok} entfolgt, {errors} Fehler.").format(
            ok=len(candidates) - errors, errors=errors
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
