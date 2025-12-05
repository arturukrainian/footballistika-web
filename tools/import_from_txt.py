from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import storage

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def parse_matches():
    path = DATA_DIR / "matches.txt"
    if not path.exists():
        print("matches.txt not found, skipping")
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 6:
                continue
            match_id = int(parts[0])
            team1, team2 = parts[1], parts[2]
            score1 = None if parts[3] in {"", "-"} else int(parts[3])
            score2 = None if parts[4] in {"", "-"} else int(parts[4])
            status_raw = parts[5].lower()
            status = "scheduled" if status_raw == "pending" else status_raw
            storage.upsert_match(match_id, team1, team2, status, score1, score2)
            print(f"Upserted match {match_id}")


def parse_predictions():
    path = DATA_DIR / "predictions.txt"
    if not path.exists():
        print("predictions.txt not found, skipping")
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 6:
                continue
            match_id = int(parts[0])
            user_id = int(parts[1])
            username = parts[2]
            pred1 = int(parts[3])
            pred2 = int(parts[4])
            try:
                storage.append_prediction(match_id, user_id, username, pred1, pred2)
                print(f"Inserted prediction user {user_id} match {match_id}")
            except ValueError:
                print(f"Skipping existing prediction user {user_id} match {match_id}")


def main():
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is not set")
    parse_matches()
    parse_predictions()
    storage.refresh_leaderboard()
    print("Done.")


if __name__ == "__main__":
    main()
