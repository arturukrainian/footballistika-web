from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
MATCHES_FILE = DATA_DIR / "matches.txt"
PREDICTIONS_FILE = DATA_DIR / "predictions.txt"
LEADERBOARD_FILE = DATA_DIR / "leaderboard.txt"
PREDICTION_RESULT_ACCURACY_FILE = DATA_DIR / "prediction_result_accuracy.txt"
PREDICTION_GOAL_ACCURACY_FILE = DATA_DIR / "prediction_goal_accuracy.txt"


def _ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not MATCHES_FILE.exists():
        MATCHES_FILE.write_text(
            "# match_id|team1|team2|score1|score2|status\n",
            encoding="utf-8",
        )
    if not PREDICTIONS_FILE.exists():
        PREDICTIONS_FILE.write_text(
            "# match_id|user_id|username|pred_score1|pred_score2|timestamp|points_awarded\n",
            encoding="utf-8",
        )
    if not LEADERBOARD_FILE.exists():
        LEADERBOARD_FILE.write_text(
            "# user_id|username|points\n",
            encoding="utf-8",
        )
    if not PREDICTION_RESULT_ACCURACY_FILE.exists():
        PREDICTION_RESULT_ACCURACY_FILE.write_text(
            "# user_id|username|predictions|result_accuracy_percent\n",
            encoding="utf-8",
        )
    if not PREDICTION_GOAL_ACCURACY_FILE.exists():
        PREDICTION_GOAL_ACCURACY_FILE.write_text(
            "# user_id|username|predictions|goal_accuracy_percent\n",
            encoding="utf-8",
        )


_ensure_storage()


def _parse_line(line: str) -> Optional[List[str]]:
    if not line.strip() or line.startswith("#"):
        return None
    return [part.strip() for part in line.strip().split("|")]


def _dump_line(parts: List[str]) -> str:
    return "|".join(parts) + "\n"


def read_matches() -> List[Dict]:
    matches: List[Dict] = []
    with MATCHES_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            parts = _parse_line(line)
            if not parts:
                continue
            match_id = int(parts[0])
            score1 = None if parts[3] in {"-", ""} else int(parts[3])
            score2 = None if parts[4] in {"-", ""} else int(parts[4])
            matches.append(
                {
                    "id": match_id,
                    "team1": parts[1],
                    "team2": parts[2],
                    "score1": score1,
                    "score2": score2,
                    "status": parts[5],
                }
            )
    matches.sort(key=lambda item: item["id"])
    return matches


def write_matches(matches: List[Dict]) -> None:
    lines = [
        "# match_id|team1|team2|score1|score2|status\n",
    ]
    for match in sorted(matches, key=lambda item: item["id"]):
        score1 = "-" if match.get("score1") is None else str(match["score1"])
        score2 = "-" if match.get("score2") is None else str(match["score2"])
        lines.append(
            _dump_line(
                [
                    str(match["id"]),
                    match["team1"],
                    match["team2"],
                    score1,
                    score2,
                    match.get("status", "pending"),
                ]
            )
        )
    MATCHES_FILE.write_text("".join(lines), encoding="utf-8")


def add_match(team1: str, team2: str) -> Dict:
    matches = read_matches()
    next_id = max([match["id"] for match in matches], default=0) + 1
    new_match = {
        "id": next_id,
        "team1": team1,
        "team2": team2,
        "score1": None,
        "score2": None,
        "status": "pending",
    }
    matches.append(new_match)
    write_matches(matches)
    return new_match


def find_match(match_id: int) -> Optional[Dict]:
    for match in read_matches():
        if match["id"] == match_id:
            return match
    return None


def update_match_result(match_id: int, score1: int, score2: int) -> Optional[Dict]:
    matches = read_matches()
    updated: Optional[Dict] = None
    for match in matches:
        if match["id"] == match_id:
            match["score1"] = score1
            match["score2"] = score2
            match["status"] = "finished"
            updated = match
            break
    if updated is None:
        return None
    write_matches(matches)
    return updated


def read_predictions() -> List[Dict]:
    records: List[Dict] = []
    with PREDICTIONS_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            parts = _parse_line(line)
            if not parts:
                continue
            records.append(
                {
                    "match_id": int(parts[0]),
                    "user_id": int(parts[1]),
                    "username": parts[2],
                    "pred_score1": int(parts[3]),
                    "pred_score2": int(parts[4]),
                    "timestamp": parts[5],
                    "points_awarded": int(parts[6]),
                }
            )
    return records


def write_predictions(predictions: List[Dict]) -> None:
    lines = [
        "# match_id|user_id|username|pred_score1|pred_score2|timestamp|points_awarded\n",
    ]
    for entry in predictions:
        lines.append(
            _dump_line(
                [
                    str(entry["match_id"]),
                    str(entry["user_id"]),
                    entry["username"],
                    str(entry["pred_score1"]),
                    str(entry["pred_score2"]),
                    entry["timestamp"],
                    str(entry.get("points_awarded", 0)),
                ]
            )
        )
    PREDICTIONS_FILE.write_text("".join(lines), encoding="utf-8")


def get_user_prediction(match_id: int, user_id: int) -> Optional[Dict]:
    for entry in read_predictions():
        if entry["match_id"] == match_id and entry["user_id"] == user_id:
            return entry
    return None


def append_prediction(match_id: int, user_id: int, username: str, score1: int, score2: int) -> None:
    timestamp = datetime.utcnow().isoformat()
    predictions = read_predictions()
    predictions.append(
        {
            "match_id": match_id,
            "user_id": user_id,
            "username": username,
            "pred_score1": score1,
            "pred_score2": score2,
            "timestamp": timestamp,
            "points_awarded": 0,
        }
    )
    write_predictions(predictions)


def read_leaderboard() -> Dict[int, Dict[str, int]]:
    table: Dict[int, Dict[str, int]] = {}
    with LEADERBOARD_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            parts = _parse_line(line)
            if not parts:
                continue
            user_id = int(parts[0])
            table[user_id] = {
                "username": parts[1],
                "points": int(parts[2]),
            }
    return table


def write_leaderboard(table: Dict[int, Dict[str, int]]) -> None:
    lines = ["# user_id|username|points\n"]
    for user_id, data in sorted(table.items(), key=lambda item: item[1]["points"], reverse=True):
        lines.append(
            _dump_line([str(user_id), data["username"], str(data["points"])])
        )
    LEADERBOARD_FILE.write_text("".join(lines), encoding="utf-8")


def ensure_user_record(user_id: int, username: str) -> None:
    table = read_leaderboard()
    existing = table.get(user_id)
    if existing and existing.get("username") == username:
        return
    table[user_id] = {
        "username": username,
        "points": existing.get("points", 0) if existing else 0,
    }
    write_leaderboard(table)


def add_points(user_id: int, username: str, points: int) -> None:
    if points == 0:
        return
    table = read_leaderboard()
    current = table.get(user_id, {"username": username, "points": 0})
    current["username"] = username
    current["points"] = current.get("points", 0) + points
    table[user_id] = current
    write_leaderboard(table)


def settle_match_points(match_id: int, score1: int, score2: int) -> List[Tuple[int, str, int]]:
    predictions = read_predictions()
    updated = False
    awarded: List[Tuple[int, str, int]] = []
    for entry in predictions:
        if entry["match_id"] != match_id:
            continue
        points = _calculate_points(score1, score2, entry["pred_score1"], entry["pred_score2"])
        delta = points - entry.get("points_awarded", 0)
        if delta != 0:
            entry["points_awarded"] = points
            add_points(entry["user_id"], entry["username"], delta)
            awarded.append((entry["user_id"], entry["username"], points))
            updated = True
    if updated:
        write_predictions(predictions)
    recalculate_prediction_quality()
    return awarded


def _calculate_points(real1: int, real2: int, pred1: int, pred2: int) -> int:
    if real1 == pred1 and real2 == pred2:
        return 5
    real_result = _result_type(real1, real2)
    pred_result = _result_type(pred1, pred2)
    return 1 if real_result == pred_result else 0


def _result_type(score1: int, score2: int) -> str:
    if score1 == score2:
        return "draw"
    return "win1" if score1 > score2 else "win2"


def get_next_match_for_prediction(user_id: int) -> Optional[Dict]:
    matches = [match for match in read_matches() if match["status"] == "pending"]
    predictions = read_predictions()
    predicted_ids = {
        (entry["match_id"], entry["user_id"]) for entry in predictions
    }
    for match in matches:
        if (match["id"], user_id) not in predicted_ids:
            return match
    return None


def get_next_pending_match_for_result() -> Optional[Dict]:
    matches = read_matches()
    for match in matches:
        if match["status"] == "pending":
            return match
    return None


def leaderboard_rows() -> List[Tuple[int, str, int]]:
    table = read_leaderboard()
    ordered = sorted(
        ((user_id, data["username"], data["points"]) for user_id, data in table.items()),
        key=lambda entry: entry[2],
        reverse=True,
    )
    return ordered


def average_predictions_per_match(include_finished: bool = True) -> List[Dict]:
    matches = {match["id"]: match for match in read_matches()}
    stats: Dict[int, Dict[str, float]] = {}
    for entry in read_predictions():
        match_id = entry["match_id"]
        match = matches.get(match_id)
        if not match:
            continue
        if not include_finished and match.get("status") == "finished":
            continue
        data = stats.setdefault(match_id, {"sum1": 0.0, "sum2": 0.0, "count": 0})
        data["sum1"] += entry["pred_score1"]
        data["sum2"] += entry["pred_score2"]
        data["count"] += 1
    rows: List[Dict] = []
    for match_id, data in stats.items():
        match = matches.get(match_id)
        if not match or data["count"] == 0:
            continue
        rows.append(
            {
                "match": match,
                "avg1": data["sum1"] / data["count"],
                "avg2": data["sum2"] / data["count"],
                "count": data["count"],
            }
        )
    rows.sort(key=lambda item: item["match"]["id"])
    return rows


def recalculate_prediction_quality() -> None:
    matches = {match["id"]: match for match in read_matches()}
    stats: Dict[int, Dict[str, float]] = {}
    for entry in read_predictions():
        match = matches.get(entry["match_id"])
        if not match or match.get("status") != "finished":
            continue
        score1 = match.get("score1")
        score2 = match.get("score2")
        if score1 is None or score2 is None:
            continue
        user_id = entry["user_id"]
        record = stats.setdefault(
            user_id,
            {
                "username": entry["username"],
                "predictions": 0,
                "correct_outcomes": 0,
                "goal_accuracy_sum": 0.0,
            },
        )
        if entry["username"]:
            record["username"] = entry["username"]
        record["predictions"] += 1
        if _result_type(score1, score2) == _result_type(
            entry["pred_score1"], entry["pred_score2"]
        ):
            record["correct_outcomes"] += 1
        record["goal_accuracy_sum"] += _goal_accuracy_percent(
            score1,
            score2,
            entry["pred_score1"],
            entry["pred_score2"],
        )
    _write_prediction_result_accuracy(stats)
    _write_prediction_goal_accuracy(stats)


def _write_prediction_result_accuracy(stats: Dict[int, Dict[str, float]]) -> None:
    lines = [
        "# user_id|username|predictions|result_accuracy_percent\n"
    ]
    for user_id in sorted(stats):
        data = stats[user_id]
        predictions = int(data.get("predictions", 0))
        result_accuracy = (
            data.get("correct_outcomes", 0) / predictions * 100.0 if predictions else 0.0
        )
        lines.append(
            _dump_line(
                [
                    str(user_id),
                    data.get("username") or "",
                    str(predictions),
                    f"{result_accuracy:.2f}",
                ]
            )
        )
    PREDICTION_RESULT_ACCURACY_FILE.write_text("".join(lines), encoding="utf-8")


def _write_prediction_goal_accuracy(stats: Dict[int, Dict[str, float]]) -> None:
    lines = [
        "# user_id|username|predictions|goal_accuracy_percent\n"
    ]
    for user_id in sorted(stats):
        data = stats[user_id]
        predictions = int(data.get("predictions", 0))
        goal_accuracy = (
            data.get("goal_accuracy_sum", 0.0) / predictions if predictions else 0.0
        )
        lines.append(
            _dump_line(
                [
                    str(user_id),
                    data.get("username") or "",
                    str(predictions),
                    f"{goal_accuracy:.2f}",
                ]
            )
        )
    PREDICTION_GOAL_ACCURACY_FILE.write_text("".join(lines), encoding="utf-8")


def read_prediction_result_accuracy() -> List[Dict]:
    rows: List[Dict] = []
    if not PREDICTION_RESULT_ACCURACY_FILE.exists():
        return rows
    with PREDICTION_RESULT_ACCURACY_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            parts = _parse_line(line)
            if not parts:
                continue
            rows.append(
                {
                    "user_id": int(parts[0]),
                    "username": parts[1],
                    "predictions": int(parts[2]),
                    "result_accuracy_percent": float(parts[3]),
                }
            )
    return rows


def read_prediction_goal_accuracy() -> List[Dict]:
    rows: List[Dict] = []
    if not PREDICTION_GOAL_ACCURACY_FILE.exists():
        return rows
    with PREDICTION_GOAL_ACCURACY_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            parts = _parse_line(line)
            if not parts:
                continue
            rows.append(
                {
                    "user_id": int(parts[0]),
                    "username": parts[1],
                    "predictions": int(parts[2]),
                    "goal_accuracy_percent": float(parts[3]),
                }
            )
    return rows


def _goal_accuracy_percent(real1: int, real2: int, pred1: int, pred2: int) -> float:
    acc1 = _single_score_accuracy(real1, pred1)
    acc2 = _single_score_accuracy(real2, pred2)
    return (acc1 + acc2) / 2 * 100.0


def _single_score_accuracy(real: int, predicted: int) -> float:
    if real == predicted:
        return 1.0
    denominator = max(real, predicted)
    if denominator == 0:
        return 1.0
    diff = abs(real - predicted)
    accuracy = 1.0 - (diff / denominator)
    return max(0.0, accuracy)


def get_user_prediction_stats(user_id: int) -> Dict[str, float]:
    recalculate_prediction_quality()
    result_accuracy = 0.0
    goal_accuracy = 0.0
    predictions = 0

    for row in read_prediction_result_accuracy():
        if row["user_id"] == user_id:
            result_accuracy = row["result_accuracy_percent"]
            predictions = row["predictions"]
            break

    for row in read_prediction_goal_accuracy():
        if row["user_id"] == user_id:
            goal_accuracy = row["goal_accuracy_percent"]
            break

    return {
        "predictions": predictions,
        "result_accuracy_percent": result_accuracy,
        "goal_accuracy_percent": goal_accuracy,
    }


# Підтримуємо файл статистики у синхронному стані при імпорті модуля.
recalculate_prediction_quality()
