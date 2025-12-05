# utils/telegram_webapp.py
import hashlib
import hmac
from urllib.parse import parse_qsl


def verify_init_data(init_data: str, bot_token: str) -> bool:
    """
    Перевірка Telegram WebApp initData за офіційним алгоритмом:
    secret = HMAC_SHA256(key="WebAppData", msg=bot_token)
    hash   = HMAC_SHA256(key=secret, data=data_check_string)
    """
    if not init_data or not bot_token:
        return False

    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return False

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))

    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calc_hash = hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    return hmac.compare_digest(calc_hash, received_hash.lower())
