"""The worker refuses every request without the Kairos gateway secret, and runs open when no secret is configured."""
from fastapi.testclient import TestClient

from qc import api

SECRET_HEADER = "X-Kairos-Gateway-Secret"


def test_with_no_secret_configured_the_api_stays_open(monkeypatch):
    monkeypatch.delenv("CATALYST_GATEWAY_SECRET", raising=False)
    assert TestClient(api.app).get("/api/config").status_code == 200


def test_with_a_secret_only_the_matching_header_gets_through(monkeypatch):
    monkeypatch.setenv("CATALYST_GATEWAY_SECRET", "s3cret")
    client = TestClient(api.app)
    assert client.get("/api/config").status_code == 403
    assert client.get("/api/config", headers={SECRET_HEADER: "wrong"}).status_code == 403
    assert client.get("/api/config", headers={SECRET_HEADER: "s3cret"}).status_code == 200


def test_masks_are_behind_the_guard_and_cannot_leave_their_folder(monkeypatch):
    monkeypatch.setenv("CATALYST_GATEWAY_SECRET", "s3cret")
    client = TestClient(api.app)
    assert client.get("/api/masks/anything.png").status_code == 403
    assert client.get("/api/masks/anything.png", headers={SECRET_HEADER: "s3cret"}).status_code == 404
    escape = client.get("/api/masks/..%2F..%2Fconfig%2Fdecision.yaml", headers={SECRET_HEADER: "s3cret"})
    assert escape.status_code == 404
