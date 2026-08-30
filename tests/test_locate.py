"""Phase 2 exit check: the true SoA pages rank in the top-3 candidates
for every given protocol.

True regions verified by direct inspection (2026-08-29 recon):
  protocol1: heading p52, table p53-54
  protocol5: table p50 + continuation p51 (rotated appendix pages)
  protocol9: table p26-29 (rotated) — X-free cells, keyword-carried
  protocol12: table p48, footnotes + heading AFTER on p49
  protocol15: intro sentence p24, table p25

Protocol PDFs are gitignored; tests skip when the corpus isn't present.
"""

from pathlib import Path

import pytest

from soa.locate import locate

PROTOCOLS_DIR = Path(__file__).parent.parent / "protocols"

TRUE_PAGES = {
    "protocol1.pdf": [52, 53, 54],
    "protocol5.pdf": [50, 51],
    "protocol9.pdf": [26, 27, 28, 29],
    "protocol12.pdf": [48, 49],
    "protocol15.pdf": [24, 25],
}


def _require(name):
    path = PROTOCOLS_DIR / name
    if not path.exists():
        pytest.skip(f"{name} not in protocols/")
    return str(path)


@pytest.mark.parametrize("name", sorted(TRUE_PAGES))
def test_true_soa_in_top3_candidates(name):
    candidates = locate(_require(name))[:3]
    covered = sorted({p for c in candidates for p in c.pages})
    assert set(TRUE_PAGES[name]) & set(covered), (
        f"{name}: no true SoA page in top-3 candidates {covered}"
    )


@pytest.mark.parametrize("name", sorted(TRUE_PAGES))
def test_candidates_are_nonempty_and_descending(name):
    candidates = locate(_require(name))
    assert len(candidates) >= 1
    scores = [c.score for c in candidates]
    assert scores == sorted(scores, reverse=True)
