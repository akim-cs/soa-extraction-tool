"""Phase 4 exit check: hierarchical column headers + category/assessment
row typing on protocol1 p53-54.

Verified by direct inspection of the page geometry on 2026-08-29:
  p53: header rows are the VISIT row and the WEEK row; visit 6's column is
       ruled but empty -> ColumnMeta with all levels None must survive.
       All 28 data rows are assessments (this protocol has no category
       header rows).
  p54: visits 9-13 plus ET/RT with no week header on the last two.

Protocol PDFs are gitignored; tests skip when the corpus isn't present.
"""

from pathlib import Path

import pytest

from soa.extract import extract_grid, interpret_grid
from soa.locate import Candidate

PROTOCOLS_DIR = Path(__file__).parent.parent / "protocols"
P1 = PROTOCOLS_DIR / "protocol1.pdf"


@pytest.fixture(scope="module")
def pages():
    if not P1.exists():
        pytest.skip("protocol1.pdf not in protocols/")
    grids = extract_grid(str(P1), Candidate(pages=[53, 54], score=0.0))
    return {g.page_number: interpret_grid(g) for g in grids}


def test_header_row_count_and_row_kind(pages):
    for pageno in (53, 54):
        page = pages[pageno]
        assert page.header_rows == 2
        assert len(page.rows) == 28
        assert {r.kind for r in page.rows} == {"assessment"}


def test_empty_rows_flagged_ambiguous_never_guessed(pages):
    # protocol1 has no category rows; rows that carry marks must never be
    # flagged, and label-only rows (TTS Survey on p53, most rows on p54)
    # are kept as assessments and flagged ambiguous.
    for pageno in (53, 54):
        page = pages[pageno]
        for row in page.rows:
            if row.cells:
                assert not row.ambiguous, f"{row.label!r} carries marks"
            else:
                assert row.ambiguous, f"{row.label!r} is label-only"


def test_visit_level_headers(pages):
    cols = {c.index: c for c in pages[53].columns}
    assert cols[2].visit == "1"
    assert cols[3].visit == "2"
    assert cols[9].visit == "8"
    # Visit 6 is skipped: column 7 is ruled but header-less on every level.
    assert cols[7].visit is None
    assert cols[7].day_week is None
    assert cols[7].window is None


def test_day_week_level_headers_verbatim(pages):
    cols = {c.index: c for c in pages[53].columns}
    assert cols[2].day_week == "-2"
    assert cols[3].day_week == "-.3"  # present verbatim in the text layer
    assert cols[9].day_week == "8"


def test_continuation_page_visit_headers(pages):
    cols = {c.index: c for c in pages[54].columns}
    assert cols[2].visit == "9"
    assert cols[6].visit == "13"
    assert cols[7].visit == "ET"
    assert cols[8].visit == "RT"
    assert cols[7].day_week is None
    assert cols[8].day_week is None


def test_row_labels_and_cells(pages):
    rows = pages[53].rows
    assert rows[0].label == "Informed consent"
    assert rows[0].cells == {2: "X"}
    hemoglobin = next(r for r in rows if r.label.startswith("Hemoglobin"))
    assert hemoglobin.label == "Hemoglobin A1C"
    assert hemoglobin.cells == {2: "Xa"}
