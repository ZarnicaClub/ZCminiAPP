import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.s3 import build_s3_key, sha256_hex


def test_sha256_hex():
    data = b"hello"
    assert sha256_hex(data) == hashlib.sha256(data).hexdigest()
    assert len(sha256_hex(data)) == 64


def test_build_s3_key():
    h = "a" * 64
    assert build_s3_key(h) == f"calls/{h[:2]}/{h}.mp3"
    try:
        build_s3_key("")
        assert False, "expected ValueError"
    except ValueError:
        pass


if __name__ == "__main__":
    test_sha256_hex()
    test_build_s3_key()
    print("test_s3: OK")
