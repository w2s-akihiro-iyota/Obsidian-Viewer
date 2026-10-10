"""CSRF 対策のミドルウェア（app/main.py の reject_cross_site_writes）の契約テスト

書き込み系メソッド（POST・PUT・PATCH・DELETE）は、Origin（無ければ Referer）が自サイトと違えば 403（E102）。
ルーティングより前に効くことを確かめるため、存在しないパスへ送る（通れば 404、止まれば 403）。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.utils.messages import get_error

ADMIN = "http://localhost:8001"
PROBE = "/__csrf_probe__"   # どのルートにも当たらないパス


@pytest.fixture
def client():
    return TestClient(app, base_url=ADMIN)


def _is_rejected(res) -> bool:
    return res.status_code == 403 and res.json() == {"status": "error", "message": get_error("E102")}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_別サイトのOriginからの書き込みは403(client, method):
    res = client.request(method, PROBE, headers={"Origin": "http://evil.example"})
    assert _is_rejected(res)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_自サイトのOriginからの書き込みは通す(client, method):
    res = client.request(method, PROBE, headers={"Origin": ADMIN})
    assert res.status_code == 404


def test_OriginもRefererも無い書き込みは通す(client):
    assert client.post(PROBE).status_code == 404


def test_Originが無ければRefererで判定する(client):
    assert client.post(PROBE, headers={"Referer": f"{ADMIN}/editor"}).status_code == 404
    assert _is_rejected(client.post(PROBE, headers={"Referer": "http://evil.example/page"}))


def test_ポートが違うOriginは別サイトとして拒否する(client):
    # 公開用ポート（8000）のページから管理用ポート（8001）への書き込みを通さない
    assert _is_rejected(client.post(PROBE, headers={"Origin": "http://localhost:8000"}))


def test_Originがnullなら拒否する(client):
    assert _is_rejected(client.post(PROBE, headers={"Origin": "null"}))


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_読み取り系のメソッドは別サイトからでも止めない(client, method):
    res = client.request(method, PROBE, headers={"Origin": "http://evil.example"})
    assert res.status_code != 403


def test_拒否するとルートの処理は動かない(client):
    # 実在の書き込み API でも、管理者判定やルートの処理より前に止まる
    res = client.post("/api/editor/save", json={"filename": "x", "content": "y"},
                      headers={"Origin": "http://evil.example"})
    assert _is_rejected(res)
