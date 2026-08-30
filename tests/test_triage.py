"""Phase 1 tests: triage against the five given protocols.

Ground truth comes from the verified facts in the assignment brief —
checked empirically when this test was written. Protocol PDFs are
gitignored, so these tests skip when the corpus isn't present.
"""

from pathlib import Path

import pytest

from soa.triage import triage

PROTOCOLS_DIR = Path(__file__).parent.parent / "protocols"

EXPECTED = {
    "protocol1.pdf": {"pages": 97, "rotated": []},
    "protocol5.pdf": {"pages": 61, "rotated": [50, 51]},
    "protocol9.pdf": {"pages": 57, "rotated": [26, 27, 28, 29]},
    "protocol12.pdf": {"pages": 97, "rotated": []},
    "protocol15.pdf": {"pages": 61, "rotated": []},
}


def _require(name):
    path = PROTOCOLS_DIR / name
    if not path.exists():
        pytest.skip(f"{name} not in protocols/")
    return str(path)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_page_counts_and_rotation(name):
    infos = triage(_require(name))
    assert len(infos) == EXPECTED[name]["pages"]
    rotated = [i.page_number for i in infos if i.rotation]
    assert rotated == EXPECTED[name]["rotated"]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_all_text_layers_trusted(name):
    infos = triage(_require(name))
    untrusted = [i.page_number for i in infos if i.needs_ocr]
    assert untrusted == []
