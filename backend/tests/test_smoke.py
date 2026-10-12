"""Baseline smoke tests: the app imports, health responds, auth is enforced."""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_endpoints_require_auth(client):
    assert client.get("/api/v1/journal-entries").status_code == 401
    assert client.get("/api/v1/reports").status_code == 401
    assert client.get("/api/v1/budget-years").status_code == 401


def test_list_fiscal_years(client, auth, fy2025):
    r = client.get("/api/v1/fiscal-years", headers=auth("viewer"))
    assert r.status_code == 200
    assert [fy["label"] for fy in r.json()] == ["2025"]
