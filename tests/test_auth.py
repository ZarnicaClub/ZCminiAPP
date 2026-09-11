import hashlib
import hmac
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crm.auth import validate_init_data


def _sign(params, token):
    data_check = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    return hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()


def test_validate_init_data():
    token = "12345:TEST_BOT_TOKEN"
    params = {"user": '{"id":1,"first_name":"A"}', "auth_date": "1720000000", "query_id": "q1"}
    h = _sign(params, token)
    init_data = "&".join(f"{k}={v}" for k, v in params.items()) + f"&hash={h}"
    assert validate_init_data(init_data, token) is True


def test_validate_init_data_rejects_tamper():
    token = "12345:TEST_BOT_TOKEN"
    params = {"auth_date": "1720000000"}
    h = _sign(params, token)
    init_data = "auth_date=1720000001&hash=" + h
    assert validate_init_data(init_data, token) is False


def test_validate_init_data_missing_hash():
    assert validate_init_data("auth_date=1", "token") is False
    assert validate_init_data("", "token") is False


if __name__ == "__main__":
    test_validate_init_data()
    test_validate_init_data_rejects_tamper()
    test_validate_init_data_missing_hash()
    print("test_auth: OK")
