"""管理者判定・CSRF 判定の部品（app/utils/helpers.py）の契約テスト

- _host_name: Host ヘッダからポートを外す。管理者判定（ADMIN_ALLOWED_HOSTS との照合）に使う
- is_same_origin_request: 書き込み系リクエストの送り元が自サイトか（CSRF 対策のミドルウェアが使う）
"""
import pytest
from starlette.requests import Request

from app.config import ADMIN_ALLOWED_HOSTS
from app.utils.helpers import _host_name, is_same_origin_request


# ---------- _host_name ----------

@pytest.mark.parametrize("host, expected", [
    ("localhost:8001", "localhost"),
    ("localhost", "localhost"),
    ("127.0.0.1:8001", "127.0.0.1"),
    ("[::1]:8001", "[::1]"),
    ("[::1]", "[::1]"),
    ("  LocalHost:8001 ", "localhost"),
    ("example.com:8001", "example.com"),
    ("", ""),
])
def test_Hostからポートを外して小文字にする(host, expected):
    assert _host_name(host) == expected


@pytest.mark.parametrize("host", ["localhost:8001", "127.0.0.1:8001", "[::1]:8001", "LOCALHOST"])
def test_localhost系のHostは管理者として許すホストになる(host):
    assert _host_name(host) in ADMIN_ALLOWED_HOSTS


@pytest.mark.parametrize("host", [
    "localhost.evil.example:8001",   # DNS リバインディングで使われる形
    "127.0.0.1.nip.io",
    "[::2]:8001",
    "evil.example",
])
def test_localhostに似たHostは許さない(host):
    assert _host_name(host) not in ADMIN_ALLOWED_HOSTS


# ---------- is_same_origin_request ----------

def _request(**headers: str) -> Request:
    raw = [(k.replace("_", "-").encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": "POST", "path": "/", "headers": raw})


def test_OriginもRefererも無ければ通す():
    # ブラウザは別サイトからの POST に必ず Origin を付けるので、無いのはブラウザ以外（curl 等）
    assert is_same_origin_request(_request(host="localhost:8001")) is True


@pytest.mark.parametrize("origin", ["http://localhost:8001", "https://LOCALHOST:8001"])
def test_OriginのホストとポートがHostと同じなら通す(origin):
    assert is_same_origin_request(_request(host="localhost:8001", origin=origin)) is True


@pytest.mark.parametrize("origin", [
    "http://evil.example",
    "http://localhost:8000",          # ポート違い（公開用ポートのページから管理用ポートへ）
    "http://localhost",
    "http://localhost:8001.evil.example",
])
def test_OriginがHostと違えば拒否する(origin):
    assert is_same_origin_request(_request(host="localhost:8001", origin=origin)) is False


def test_Originがnullなら拒否する():
    # サンドボックスの iframe やファイルから送ると Origin: null になる
    assert is_same_origin_request(_request(host="localhost:8001", origin="null")) is False


def test_Originが無ければRefererで判定する():
    assert is_same_origin_request(_request(host="localhost:8001", referer="http://localhost:8001/view/a")) is True
    assert is_same_origin_request(_request(host="localhost:8001", referer="http://evil.example/page")) is False


def test_OriginがあればRefererより優先する():
    req = _request(host="localhost:8001", origin="http://localhost:8001", referer="http://evil.example/")
    assert is_same_origin_request(req) is True
    req = _request(host="localhost:8001", origin="http://evil.example", referer="http://localhost:8001/")
    assert is_same_origin_request(req) is False


def test_Hostが無ければOriginがあっても拒否する():
    assert is_same_origin_request(_request(origin="http://localhost:8001")) is False
