import hashlib
import hmac
import urllib.parse as urlparse


def verify_init_data(init_data: str, bot_token: str) -> bool:
    """
    Validate Telegram WebApp initData signed with the bot token.
    init_data should be the raw tg.initData string (location.hash without '#').
    """
    params = dict(urlparse.parse_qsl(init_data, keep_blank_values=True))
    received_hash = params.pop("hash", None)
    if not received_hash:
        return False
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated, received_hash)
