import json
import logging
import os
import re
import time
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
from urllib.parse import parse_qs

from flask import Flask, jsonify, request
from flask_cors import CORS

import storage
from utils.telegram_webapp import verify_init_data

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
MAX_AGE = 24 * 60 * 60  # 24h
KYIV_TZ = ZoneInfo("Europe/Kyiv")
PREDICTION_DEADLINE = dt_time(17, 59)

app = Flask(__name__)
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "https://footballistika-web.vercel.app",
                re.compile(r"https://footballistika-web-git-.*\\.vercel\\.app"),
            ],
            "supports_credentials": True,
        }
    },
)


def _verify_and_extract_user(init_data: str):
    if not verify_init_data(init_data, BOT_TOKEN):
        return None, None, "invalid_signature"

    params = {k: v[0] for k, v in parse_qs(init_data).items()}
    auth_date = int(params.get("auth_date", "0"))
    if abs(time.time() - auth_date) > MAX_AGE:
        return None, None, "expired"

    if "user" not in params:
        return None, None, "missing_user"

    try:
        user = json.loads(params["user"])
    except json.JSONDecodeError:
        return None, None, "bad_user_json"

    return user, params, None


def _get_init_data_from_request():
    if request.form:
        raw = request.form.get("initData", "")
        if raw:
            return raw
    if request.is_json:
        data = request.get_json(silent=True) or {}
        return data.get("initData", "")
    return ""


def _is_prediction_window_open(now=None) -> bool:
    now_kyiv = now or datetime.now(KYIV_TZ)
    if now_kyiv.tzinfo is None:
        now_kyiv = now_kyiv.replace(tzinfo=KYIV_TZ)
    else:
        now_kyiv = now_kyiv.astimezone(KYIV_TZ)
    deadline = datetime.combine(now_kyiv.date(), PREDICTION_DEADLINE, KYIV_TZ)
    return now_kyiv <= deadline


def _top_with_user(rows, user_id, limit=10):
    top = []
    user_row = None
    for idx, row in enumerate(rows, start=1):
        entry = {**row, "rank": idx}
        if idx <= limit:
            top.append(entry)
        if row.get("user_id") == user_id and user_row is None:
            user_row = entry
    return top, user_row


@app.post("/api/webapp/login")
def webapp_login():
    init_data = request.form.get("initData", "")
    user, params, error = _verify_and_extract_user(init_data)
    if error:
        return jsonify({"ok": False, "error": error}), 401
    return jsonify({"ok": True, "user": {"id": user["id"], "username": user.get("username")}})


@app.post("/api/webapp/profile")
def webapp_profile():
    init_data = _get_init_data_from_request()
    logging.info(
        "profile: origin=%s ua=%s len(initData)=%s",
        request.headers.get("Origin"),
        request.headers.get("User-Agent"),
        len(init_data or ""),
    )
    user, params, error = _verify_and_extract_user(init_data)
    if error:
        logging.warning("profile: verify failed: %s", error)
        return jsonify({"ok": False, "error": error}), 401

    stats = storage.get_user_prediction_stats(int(user["id"])) or {}
    logging.info("profile: user_id=%s stats_keys=%s", user["id"], list(stats.keys()))
    return jsonify(
        {
            "ok": True,
            "user": {
                "id": user["id"],
                "username": user.get("username"),
                "first_name": user.get("first_name"),
                "last_name": user.get("last_name"),
                "photo_url": user.get("photo_url"),
            },
            "stats": stats,
        }
    )


@app.post("/api/webapp/matches")
def webapp_matches():
    init_data = _get_init_data_from_request()
    user, params, error = _verify_and_extract_user(init_data)
    if error:
        return jsonify({"ok": False, "error": error}), 401
    user_id = int(user["id"])
    matches = storage.get_pending_matches_for_user(user_id)
    return jsonify(
        {
            "ok": True,
            "prediction_allowed": _is_prediction_window_open(),
            "deadline": "17:59 Europe/Kyiv",
            "matches": [
                {"id": m["id"], "team1": m["team1"], "team2": m["team2"]} for m in matches
            ],
        }
    )


@app.post("/api/webapp/prediction")
def webapp_prediction():
    init_data = _get_init_data_from_request()
    user, params, error = _verify_and_extract_user(init_data)
    if error:
        return jsonify({"ok": False, "error": error}), 401
    if not _is_prediction_window_open():
        return jsonify({"ok": False, "error": "deadline_passed"}), 400

    payload = request.get_json(silent=True) or request.form
    try:
        match_id = int(payload.get("match_id"))
        score1 = int(payload.get("score1"))
        score2 = int(payload.get("score2"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "bad_payload"}), 400

    if not (0 <= score1 <= 99 and 0 <= score2 <= 99):
        return jsonify({"ok": False, "error": "scores_out_of_range"}), 400

    match = storage.find_match(match_id)
    if not match or match.get("status") != "pending":
        return jsonify({"ok": False, "error": "match_not_available"}), 400

    user_id = int(user["id"])
    username = user.get("username") or user.get("first_name") or str(user_id)
    if storage.get_user_prediction(match_id, user_id):
        return jsonify({"ok": False, "error": "already_predicted"}), 409

    storage.append_prediction(match_id, user_id, username, score1, score2)
    return jsonify({"ok": True, "match_id": match_id, "score1": score1, "score2": score2})


@app.post("/api/webapp/leaderboard")
def webapp_leaderboard():
    init_data = _get_init_data_from_request()
    user, params, error = _verify_and_extract_user(init_data)
    if error:
        return jsonify({"ok": False, "error": error}), 401
    rows = [
        {"user_id": user_id, "username": username, "points": points}
        for user_id, username, points in storage.leaderboard_rows()
    ]
    top, user_row = _top_with_user(rows, int(user["id"]))
    return jsonify({"ok": True, "top": top, "user": user_row})


@app.post("/api/webapp/result-accuracy")
def webapp_result_accuracy():
    init_data = _get_init_data_from_request()
    user, params, error = _verify_and_extract_user(init_data)
    if error:
        return jsonify({"ok": False, "error": error}), 401
    rows = sorted(
        storage.read_prediction_result_accuracy(),
        key=lambda row: row["result_accuracy_percent"],
        reverse=True,
    )
    rows = [
        {
            "user_id": row["user_id"],
            "username": row.get("username") or "",
            "predictions": row["predictions"],
            "result_accuracy_percent": row["result_accuracy_percent"],
        }
        for row in rows
    ]
    top, user_row = _top_with_user(rows, int(user["id"]))
    return jsonify({"ok": True, "top": top, "user": user_row})


@app.post("/api/webapp/goal-accuracy")
def webapp_goal_accuracy():
    init_data = _get_init_data_from_request()
    user, params, error = _verify_and_extract_user(init_data)
    if error:
        return jsonify({"ok": False, "error": error}), 401
    rows = sorted(
        storage.read_prediction_goal_accuracy(),
        key=lambda row: row["goal_accuracy_percent"],
        reverse=True,
    )
    rows = [
        {
            "user_id": row["user_id"],
            "username": row.get("username") or "",
            "predictions": row["predictions"],
            "goal_accuracy_percent": row["goal_accuracy_percent"],
        }
        for row in rows
    ]
    top, user_row = _top_with_user(rows, int(user["id"]))
    return jsonify({"ok": True, "top": top, "user": user_row})


@app.get("/api/webapp/ping")
def ping():
    return jsonify({"ok": True, "at": "railway", "origin": request.headers.get("Origin")})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
