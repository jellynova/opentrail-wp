import pytest

from app.models.report import Report
from tests.conftest import add_tb, classify, make_account, make_scheme, period_of

URL = "/api/v1/reports"

DEF = {
    "version": 2,
    "title": "Revenue summary",
    "columns": [{"key": "cy", "label": "{fiscal_year}", "source": "actual"}],
    "rows": [{"id": "rev", "type": "accounts", "label": "Taxation", "classifications": ["revenue*"], "sign": -1}],
}


@pytest.fixture()
def seeded(db, fy2025):
    psab = make_scheme(db)
    a = make_account(db, fy2025, "4-100", "Taxes")
    classify(db, psab, a, "revenue.taxation")
    add_tb(db, period_of(fy2025, 12), a, ytd=-1234)
    return fy2025


def _create(client, auth, definition=DEF):
    return client.post(URL, json={"name": "Rev", "report_type": "custom", "definition": definition},
                       headers=auth("officer"))


def test_create_rejects_invalid_definition(client, auth, seeded):
    bad = {**DEF, "rows": [{"id": "x", "type": "formula", "formula": "nope"}]}
    r = _create(client, auth, bad)
    assert r.status_code == 422
    assert "unknown row" in r.json()["detail"][0]


def test_generate_and_export(client, auth, seeded):
    rid = _create(client, auth).json()["id"]
    body = {"fiscal_year_id": seeded.id}
    r = client.post(f"{URL}/{rid}/generate", json=body, headers=auth("viewer"))
    assert r.status_code == 200, r.text
    row = r.json()["data"]["rows"][0]
    assert row["label"] == "Taxation" and float(row["values"]["cy"]) == 1234

    x = client.post(f"{URL}/{rid}/export/excel", json=body, headers=auth("viewer"))
    assert x.status_code == 200 and x.content[:2] == b"PK"
    assert 'filename="Rev.xlsx"' in x.headers["content-disposition"]


def test_pdf_export(client, auth, seeded):
    pytest.importorskip("weasyprint")
    rid = _create(client, auth).json()["id"]
    r = client.post(f"{URL}/{rid}/export/pdf", json={"fiscal_year_id": seeded.id}, headers=auth("viewer"))
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"


def test_preview_and_validate(client, auth, seeded):
    r = client.post(f"{URL}/preview", json={"fiscal_year_id": seeded.id, "definition": DEF}, headers=auth("viewer"))
    assert r.status_code == 200 and r.json()["title"] == "Revenue summary"
    v = client.post(f"{URL}/validate", json={"definition": {**DEF, "columns": []}}, headers=auth("viewer"))
    assert v.json()["valid"] is False


def test_generate_unknown_fiscal_year(client, auth, seeded):
    rid = _create(client, auth).json()["id"]
    assert client.post(f"{URL}/{rid}/generate", json={"fiscal_year_id": 999}, headers=auth("viewer")).status_code == 404


def test_protected_template_clone_update_delete(client, auth, db, users, seeded):
    tpl = Report(name="PSAB SO", report_type="psab_so", is_template=True, is_protected=True,
                 definition={**DEF, "template_key": "psab_so"}, created_by_user_id=users["admin"].id)
    db.add(tpl)
    db.commit()
    assert client.put(f"{URL}/{tpl.id}", json={"name": "x"}, headers=auth("officer")).status_code == 403
    assert client.delete(f"{URL}/{tpl.id}", headers=auth("officer")).status_code == 403

    c = client.post(f"{URL}/{tpl.id}/clone", headers=auth("officer"))
    assert c.status_code == 201
    copy = c.json()
    assert copy["is_protected"] is False and copy["is_template"] is False
    assert copy["definition"]["source_template_key"] == "psab_so"
    assert "template_key" not in copy["definition"]
    assert client.put(f"{URL}/{copy['id']}", json={"name": "Mine"}, headers=auth("officer")).json()["name"] == "Mine"
    assert client.delete(f"{URL}/{copy['id']}", headers=auth("officer")).status_code == 204

    templates = client.get(URL, params={"is_template": True}, headers=auth("viewer")).json()
    assert [t["id"] for t in templates] == [tpl.id]
