"""Phase 5 exit check: footnote extraction + marker binding on protocol1
p53-54 (legend style "X = ...", "X<sup>a</sup> = ...").

Verified by direct inspection of the pages on 2026-08-29:
  - legend/definition keys: Abbreviations, X, X^a, X^b, P
  - marker a sits on the HbA1c cell (row band 22, col band 2, p53)
  - marker b sits on NPI-X cells (p53 col 9; p54 cols 2-4)
  - the P definition continues over three printed lines on the same page
  - p54 repeats X / Xb definitions -> deduplicated with source_pages [53, 54]

Protocol PDFs are gitignored; tests skip when the corpus isn't present.
"""

from pathlib import Path

import pytest

from soa.extract import extract_grid, interpret_grid
from soa.footnotes import extract_footnotes
from soa.locate import Candidate

PROTOCOLS_DIR = Path(__file__).parent.parent / "protocols"
P1 = PROTOCOLS_DIR / "protocol1.pdf"


@pytest.fixture(scope="module")
def result():
    if not P1.exists():
        pytest.skip("protocol1.pdf not in protocols/")
    grids = extract_grid(str(P1), Candidate(pages=[53, 54], score=0.0))
    pages = [interpret_grid(g) for g in grids]
    notes = extract_footnotes(str(P1), grids, pages)
    return notes, {p.page_number: p for p in pages}


def test_definition_ids_present(result):
    notes, _ = result
    ids = {n.id for n in notes}
    assert {"X", "Xa", "Xb", "P"} <= ids


def test_marker_a_bound_to_hba1c_cell(result):
    notes, pages = result
    xa = next(n for n in notes if n.id == "Xa")
    assert xa.marker == "a"
    assert "insulin-dependent diabetic" in xa.text
    assert xa.attached_to == [{"row": 22, "column": 2, "page": 53}]
    row = next(r for r in pages[53].rows if r.index == 22)
    assert row.cells[2] == "X"
    assert row.markers[2] == ["a"]


def test_marker_b_bound_to_four_npix_cells(result):
    notes, _ = result
    xb = next(n for n in notes if n.id == "Xb")
    assert xb.marker == "b"
    assert xb.source_pages == [53, 54]
    assert sorted((t["page"], t["column"]) for t in xb.attached_to) == [
        (53, 9), (54, 2), (54, 3), (54, 4),
    ]
    assert all(t["row"] == 28 for t in xb.attached_to)


def test_three_line_continuation_joined(result):
    notes, _ = result
    p = next(n for n in notes if n.id == "P")
    assert "considered as study data" in p.text
    assert "CIBIC+, ADAS-Cog, DAD, and NPI-X" in p.text


def test_abbreviations_block_captured_inline(result):
    notes, _ = result
    abbrevs = [n for n in notes if n.id == "Abbreviations"]
    assert len(abbrevs) == 2  # p53 and p54 variants differ, both kept
    p54 = next(n for n in abbrevs if 54 in n.source_pages)
    assert "ET = Early Termination" in p54.text
    assert "RT = Retrieval" in p54.text


def test_legend_entries_have_no_attachments(result):
    notes, _ = result
    for note in notes:
        if note.id in {"X", "P", "Abbreviations"}:
            assert note.marker is None
            assert note.attached_to == []
