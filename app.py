import json
import logging
import os
import re
import time
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


@app.get("/api/webapp/ping")
def ping():
    return jsonify({"ok": True, "at": "railway", "origin": request.headers.get("Origin")})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
