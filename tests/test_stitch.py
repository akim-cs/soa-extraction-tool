"""Phase 6 exit check: cross-page stitching on all five protocols.

Verified counts come from direct geometry probes on 2026-08-29:
  protocol1:  15 columns (visits 1-5, ghost, 7-8, 9-13, ET, RT) x 28 rows
  protocol5:  row-continuation from sniffed rotated p51 lands in one table
  protocol9:  rotated p26-28 merge by row continuation
  protocol12: label zone splits marks from labels on nested-frame ruling
  protocol15: category row + sniff-page exclusion of the prose p26

Protocol PDFs are gitignored; tests skip when the corpus isn't present.
"""

from pathlib import Path

import pytest

from soa.extract import extract_grid, interpret_grid
from soa.locate import Candidate, locate
from soa.stitch import stitch

PROTOCOLS_DIR = Path(__file__).parent.parent / "protocols"


@pytest.fixture(scope="module")
def tables():
    tables = {}
    for name in ["protocol1", "protocol5", "protocol9", "protocol12", "protocol15"]:
        path = PROTOCOLS_DIR / f"{name}.pdf"
        if not path.exists():
            continue
        cand = locate(str(path))[0]
        sniff = cand.pages[-1] + 1
        grids = extract_grid(str(path), Candidate(pages=cand.pages + [sniff], score=0.0))
        pages = [interpret_grid(g) for g in grids]
        tables[name] = stitch(pages, sniff_pages={sniff})
    if not tables:
        pytest.skip("no protocol PDFs in protocols/")
    return tables


def _require(tables, name):
    if name not in tables:
        pytest.skip(f"{name}.pdf not in protocols/")
    return tables[name]


def test_protocol1_golden(tables):
    table = _require(tables, "protocol1")
    assert len(table.columns) == 15
    assert len(table.rows) == 28
    visits = [c.visit for c in table.columns if not c.void]
    assert visits == ["1", "2", "3", "4", "5", "7", "8",
                      "9", "10", "11", "12", "13", "ET", "RT"]
    day_weeks = [c.day_week for c in table.columns if not c.void]
    assert day_weeks[:5] == ["-2", "-.3", "0", "2", "4"]
    consent = table.rows[0]
    assert consent.label == "Informed consent"
    assert consent.cells and set(consent.cells.values()) == {"X"}
    used = {p for r in table.rows for p in r.source_pages}
    assert used == {53, 54}


def test_protocol5_rotated_continuation_lands_in_one_table(tables):
    table = _require(tables, "protocol5")
    p51_rows = [r for r in table.rows if 51 in r.source_pages]
    assert p51_rows, "rotated continuation page 51 contributed no rows"
    assert any("approximate" in w for w in table.warnings)


def test_protocol9_row_continuation_across_rotated_pages(tables):
    table = _require(tables, "protocol9")
    used = {p for r in table.rows for p in r.source_pages}
    assert used == {26, 27, 28}
    assert len(table.rows) >= 60


def test_protocol12_label_zone_splits_marks_from_labels(tables):
    table = _require(tables, "protocol12")
    consent = next(r for r in table.rows if r.label.startswith("Informed consent"))
    assert not consent.label.rstrip().endswith("X")
    assert any(v.strip() == "X" for v in consent.cells.values())


def test_protocol15_category_row_and_sniff_exclusion(tables):
    table = _require(tables, "protocol15")
    screening = next(r for r in table.rows if r.label.lower().startswith("screening"))
    assert screening.ambiguous, "label-only row without span must be flagged ambiguous"
    assert screening.cells == {}
    used = {p for r in table.rows for p in r.source_pages}
    assert used == {25}
