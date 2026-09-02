"""Phase 8 tests: FastAPI backend for the web UI.

Static endpoints (page, health, committed examples) are tested directly;
the live upload path runs the full pipeline on protocol9 (smallest, 57pp)
and checks the returned schema shape. Protocol PDFs are gitignored; the
upload test skips when the corpus isn't present.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from soa.server import app

ROOT = Path(__file__).parent.parent
PROTOCOLS_DIR = ROOT / "protocols"
OUTPUTS_DIR = ROOT / "outputs"

client = TestClient(app)


def test_index_serves_static_page():
    res = client.get("/")
    assert res.status_code == 200
    assert "SoA Extraction Tool" in res.text


def test_health():
    assert client.get("/api/health").json() == {"ok": True}


def test_examples_list_matches_committed_outputs():
    committed = {p.stem for p in OUTPUTS_DIR.glob("*.json")}
    res = client.get("/api/examples")
    assert res.status_code == 200
    assert committed and committed <= set(res.json()["examples"])


def test_example_serves_committed_json():
    expected = json.loads((OUTPUTS_DIR / "protocol1.json").read_text())
    res = client.get("/api/examples/protocol1.json")
    assert res.status_code == 200
    body = res.json()
    assert body["schema_version"] == expected["schema_version"]
    assert body["document"]["file"] == "protocol1.pdf"
    assert body["tables"], "expected at least one table"


@pytest.mark.parametrize("name", [
    "protocol9",  # stem without .json also serves
    "does-not-exist",
    "..%2FDESIGN",
    "..%2F..%2FDESIGN.md",
    "static%2Findex",
])
def test_example_lookup_is_whitelisted(name):
    res = client.get(f"/api/examples/{name}")
    if name == "protocol9":
        assert res.status_code == 200
    else:
        assert res.status_code == 404


def test_extract_rejects_non_pdf():
    res = client.post(
        "/api/extract",
        files={"file": ("notes.txt", b"not a pdf", "text/plain")},
    )
    assert res.status_code == 400


@pytest.mark.skipif(
    not (PROTOCOLS_DIR / "protocol9.pdf").exists(),
    reason="protocol9.pdf not in protocols/",
)
def test_extract_runs_pipeline_on_upload():
    pdf = (PROTOCOLS_DIR / "protocol9.pdf").read_bytes()
    res = client.post(
        "/api/extract",
        files={"file": ("protocol9.pdf", pdf, "application/pdf")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["schema_version"] == "1.0"
    assert body["document"]["file"] == "protocol9.pdf"  # not the temp name
    assert body["document"]["pages"] > 0
    assert body["tables"], "expected at least one located table"
    assert all(t["rows"] for t in body["tables"])
