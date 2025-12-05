import json
import os
import time
from urllib.parse import parse_qs

from flask import Flask, jsonify, request

import storage
from utils.telegram_webapp import verify_init_data

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
MAX_AGE = 24 * 60 * 60  # 24h

app = Flask(__name__)


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


@app.post("/api/webapp/login")
def webapp_login():
    init_data = request.form.get("initData", "")
    user, params, error = _verify_and_extract_user(init_data)
    if error:
        return jsonify({"ok": False, "error": error}), 401
    return jsonify({"ok": True, "user": {"id": user["id"], "username": user.get("username")}})


@app.post("/api/webapp/profile")
def webapp_profile():
    init_data = request.form.get("initData", "")
    user, params, error = _verify_and_extract_user(init_data)
    if error:
        return jsonify({"ok": False, "error": error}), 401

    stats = storage.get_user_prediction_stats(int(user["id"]))
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
