"""Phase 3 exit check: grid extraction on protocol1 p53-54 (the easiest SoA —
ruled cells, dense aligned X columns).

Verified by direct inspection of the page geometry on 2026-08-29:
  p53: 30 row bands x 10 col bands (an EMPTY ruled column for the skipped
       visit 6 must be preserved verbatim); 28 activity rows under
       VISIT/WEEK header rows.
  p54: 30 row bands x 9 col bands; visits 9-13 + ET/RT with no week for ET/RT.

Protocol PDFs are gitignored; tests skip when the corpus isn't present.
"""

from pathlib import Path

import pytest

from soa.extract import extract_grid
from soa.locate import Candidate

PROTOCOLS_DIR = Path(__file__).parent.parent / "protocols"
P1 = PROTOCOLS_DIR / "protocol1.pdf"


@pytest.fixture(scope="module")
def grids():
    if not P1.exists():
        pytest.skip("protocol1.pdf not in protocols/")
    return {g.page_number: g for g in
            extract_grid(str(P1), Candidate(pages=[53, 54], score=0.0))}


def _row_labels(grid):
    labels = {}
    for box in grid.boxes:
        if box.col_index == 0 and box.text:
            labels[box.row_index] = box.text
    return labels


def _cells_in_row(grid, row_index):
    return {b.col_index: b.text for b in grid.boxes
            if b.row_index == row_index and b.col_index > 0}


def test_pages_use_ruled_path_with_expected_bands(grids):
    assert grids[53].source == "rules"
    assert grids[54].source == "rules"
    assert len(grids[53].row_boundaries) - 1 == 30
    assert len(grids[53].col_boundaries) - 1 == 10
    assert len(grids[54].row_boundaries) - 1 == 30
    assert len(grids[54].col_boundaries) - 1 == 9


def test_verbatim_header_cells_preserved(grids):
    # Including the odd-but-verbatim "-.3" week value present in the text layer.
    header_text = {b.text for b in grids[53].boxes if b.row_index == 1}
    assert "-.3" in header_text
    visit_text = {b.text for b in grids[53].boxes if b.row_index == 0}
    assert {"1", "2", "3", "4", "5", "7", "8"} <= visit_text


def test_multiline_label_joined_verbatim(grids):
    labels = _row_labels(grids[53])
    ct_labels = [v for v in labels.values() if v.startswith("CT Scan")]
    assert ct_labels == ["CT Scan (if not within last year and patient "
                         "passes all other screens)"]


def test_empty_ruled_column_for_skipped_visit_preserved(grids):
    grid = grids[53]
    # Band c7 (between week columns 4 and 6) is ruled but has no content:
    # the protocol skips visit 6. An empty column must not vanish.
    c7_boxes = [b for b in grid.boxes if b.col_index == 7]
    assert c7_boxes, "empty ruled column was dropped"
    assert all(not b.text for b in c7_boxes)


def test_dense_row_marks(grids):
    labels = _row_labels(grids[53])
    vital_row = next(r for r, v in labels.items() if v == "Vital signs/Temperature")
    cells = _cells_in_row(grids[53], vital_row)
    assert "WEEK" not in cells
    marked = [c for c, text in cells.items() if text]
    assert len(marked) == 7


def test_empty_row_on_continuation_page_preserved(grids):
    labels = _row_labels(grids[54])
    consent_row = next(r for r, v in labels.items() if v == "Informed consent")
    cells = _cells_in_row(grids[54], consent_row)
    assert all(not text for text in cells.values())


def test_marker_chars_stay_fused_for_now(grids):
    # Phase 3 captures verbatim text; Phase 5 splits 'Xa' -> X + marker a.
    labels = _row_labels(grids[53])
    hba1c_row = next(r for r, v in labels.items() if v.startswith("Hemoglobin"))
    cells = _cells_in_row(grids[53], hba1c_row)
    assert "Xa" in cells.values()
