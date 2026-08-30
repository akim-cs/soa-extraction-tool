"""Stage 3 — Grid-structure extractor.

Geometry-first recovery of the true row x column x cell structure of one
located candidate region. NEVER parses a flattened text stream — on real
SoA pages that detaches column headers from cell values and superscript
markers from the values they annotate.

Two reconstruction paths, chosen per page:

  * ruled-grid path — table borders are drawn as thin rect strokes (e.g.
    protocol1: 972 rects on one SoA page). Row/column boundaries come from
    ruling edges; merged cells fall out naturally from *absent* interior
    edges (a cell spanning three text lines has no rules inside it).
  * token-clustering fallback — borderless tables: cluster token x0s into
    column anchors and token baselines into rows. Kept deliberately
    minimal; protocol1 exercises the ruled path, later protocols exercise
    this one. Gaps discovered there are logged in docs/break-log.md.

Cell values are VERBATIM text of everything inside the box (markers, arrows,
dashes included) — no normalisation to booleans, ever. Multi-line labels are
joined with spaces.

    extract_grid(pdf_path, candidate) -> list[PageGrid]
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pdfplumber

MERGE_TOL = 1.5
INTERIOR_EDGE_MAX = 0.35


@dataclass
class Box:
    row_index: int  # logical row band index (global h boundaries)
    col_index: int  # leftmost column band index (global v boundaries)
    top: float
    bottom: float
    x0: float
    x1: float
    text: str = ""


@dataclass
class PageGrid:
    page_number: int
    source: str  # "rules" or "tokens"
    row_boundaries: list[float]
    col_boundaries: list[float]
    boxes: list[Box] = field(default_factory=list)


def _merge_positions(positions: list[float], tol: float = MERGE_TOL) -> list[float]:
    """Cluster near-identical coordinates (stroke pairs, duplicate edges)."""
    merged: list[float] = []
    for pos in sorted(positions):
        if merged and pos - merged[-1] <= tol:
            continue
        merged.append(pos)
    return merged


def _band_of(position: float, boundaries: list[float]) -> int | None:
    """Index of the boundary pair containing position; None if outside."""
    for i in range(len(boundaries) - 1):
        if boundaries[i] - MERGE_TOL <= position < boundaries[i + 1] - MERGE_TOL:
            return i
    return None


def _edge_coverage(positions_spec, axis_pos: float, lo: float, hi: float) -> float:
    """Fraction of span [lo, hi] covered by edge segments placed at axis_pos."""
    span = hi - lo
    if span <= 0:
        return 1.0
    covered = 0.0
    for seg_axis, seg_lo, seg_hi in positions_spec:
        if abs(seg_axis - axis_pos) > MERGE_TOL:
            continue
        covered += max(0.0, min(seg_hi, hi) - max(seg_lo, lo))
    return min(covered / span, 1.0)


def _merge_adjacent_boxes(boxes: list[Box], v_segs, v_positions) -> list[Box]:
    """Join horizontally adjacent boxes sharing (top, bottom) when the vertical
    rule between them is absent over their shared span (a merged cell)."""
    by_rowspan: dict[tuple[float, float], list[Box]] = {}
    for box in boxes:
        by_rowspan.setdefault((box.top, box.bottom), []).append(box)

    merged: list[Box] = []
    for (_top, _bottom), row_boxes in by_rowspan.items():
        row_boxes.sort(key=lambda b: b.x0)
        current = row_boxes[0]
        for nxt in row_boxes[1:]:
            boundary = current.x1
            coverage = _edge_coverage(v_segs, boundary, current.top, current.bottom)
            if abs(nxt.x0 - boundary) <= MERGE_TOL and coverage < INTERIOR_EDGE_MAX:
                current = Box(
                    row_index=current.row_index,
                    col_index=current.col_index,
                    top=current.top,
                    bottom=current.bottom,
                    x0=current.x0,
                    x1=nxt.x1,
                )
            else:
                merged.append(current)
                current = nxt
        merged.append(current)
    merged.sort(key=lambda b: (b.top, b.x0))
    return merged


def _boxes_from_rules(page) -> PageGrid | None:
    edges = page.edges
    h_segs = [(e["top"], min(e["x0"], e["x1"]), max(e["x0"], e["x1"]))
              for e in edges if e["orientation"] == "h"]
    v_segs = [(e["x0"], min(e["top"], e["bottom"]), max(e["top"], e["bottom"]))
              for e in edges if e["orientation"] == "v"]
    if len(h_segs) < 3 or len(v_segs) < 3:
        return None

    row_boundaries = _merge_positions([s[0] for s in h_segs])
    col_boundaries = _merge_positions([s[0] for s in v_segs])
    if len(row_boundaries) < 3 or len(col_boundaries) < 3:
        return None

    boxes: list[Box] = []
    for ci in range(len(col_boundaries) - 1):
        cx0, cx1 = col_boundaries[ci], col_boundaries[ci + 1]
        # Row boundaries *local to this column*: only h-rules overlapping the
        # column span. Absent interior rules => one tall box (vertical merge).
        local = []
        for axis_pos, seg_lo, seg_hi in h_segs:
            overlap = min(seg_hi, cx1) - max(seg_lo, cx0)
            if overlap > 0.5 * (cx1 - cx0):
                local.append(axis_pos)
        local = _merge_positions(local)
        for ri in range(len(local) - 1):
            boxes.append(Box(
                row_index=_band_of(local[ri], row_boundaries) or 0,
                col_index=ci,
                top=local[ri],
                bottom=local[ri + 1],
                x0=cx0,
                x1=cx1,
            ))

    boxes = _merge_adjacent_boxes(boxes, v_segs, col_boundaries)
    return PageGrid(
        page_number=page.page_number,
        source="rules",
        row_boundaries=row_boundaries,
        col_boundaries=col_boundaries,
        boxes=boxes,
    )


def _midpoints(values: list[float]) -> list[float]:
    return [(a + b) / 2 for a, b in zip(values, values[1:])]


def _boxes_from_tokens(page) -> PageGrid:
    """Borderless fallback: infer the grid from token geometry alone.

    Columns = short-token x-anchors (cell marks line up by x); rows = top
    clusters of ALL tokens. Bands are midpoint-split so every token still
    lands in some box. Coarse by design — gaps found on later protocols
    belong in docs/break-log.md, but a *missing* page would violate recall.
    """
    words = page.extract_words()
    tops = _merge_positions([w["top"] for w in words], tol=3.0)
    anchors = _merge_positions(
        sorted({round(w["x0"], 1) for w in words if len(w["text"]) <= 3}),
        tol=4.0,
    )
    if len(tops) < 3 or len(anchors) < 3:
        return PageGrid(page_number=page.page_number, source="tokens",
                        row_boundaries=[], col_boundaries=[])

    label_left = min(w["x0"] for w in words)
    first_anchor_gap = (anchors[1] - anchors[0]) / 2 if len(anchors) > 1 else 20.0
    col_boundaries = (
        [max(0.0, label_left - 5.0), anchors[0] - first_anchor_gap]
        + _midpoints(anchors)
        + [anchors[-1] + (anchors[-1] - anchors[-2]) / 2]
    )
    row_boundaries = (
        [tops[0] - 4.0] + _midpoints(tops) + [tops[-1] + 14.0]
    )

    boxes = [
        Box(row_index=ri, col_index=ci,
            top=row_boundaries[ri], bottom=row_boundaries[ri + 1],
            x0=col_boundaries[ci], x1=col_boundaries[ci + 1])
        for ri in range(len(row_boundaries) - 1)
        for ci in range(len(col_boundaries) - 1)
    ]
    return PageGrid(
        page_number=page.page_number,
        source="tokens",
        row_boundaries=row_boundaries,
        col_boundaries=col_boundaries,
        boxes=boxes,
    )


def _text_in_reading_order(page, grid: PageGrid) -> None:
    words = page.extract_words()
    buckets: dict[int, list[dict]] = {id(box): [] for box in grid.boxes}
    for word in words:
        cx = (word["x0"] + word["x1"]) / 2
        cy = (word["top"] + word["bottom"]) / 2
        for box in grid.boxes:
            if box.x0 - 1 <= cx < box.x1 and box.top - 1 <= cy < box.bottom + 1:
                buckets[id(box)].append(word)
                break
    for box in grid.boxes:
        lines: dict[int, list[str]] = {}
        for word in sorted(buckets[id(box)], key=lambda w: (w["top"], w["x0"])):
            key = round(word["top"] / 6)
            lines.setdefault(key, []).append(word["text"])
        box.text = " ".join(" ".join(line) for line in lines.values()).strip()


def extract_page(page) -> PageGrid | None:
    """Reconstruct the grid on one page; None if the page has no usable grid."""
    grid = _boxes_from_rules(page)
    if grid is None:
        grid = _boxes_from_tokens(page)
    if not grid.boxes:
        return None
    _text_in_reading_order(page, grid)
    return grid


def extract_grid(pdf_path: str, candidate) -> list[PageGrid]:
    """Extract per-page RawGrid fragments for one located candidate region."""
    grids: list[PageGrid] = []
    with pdfplumber.open(pdf_path) as pdf:
        for pageno in candidate.pages:
            page = pdf.pages[pageno - 1]
            grid = extract_page(page)
            if grid is not None:
                grids.append(grid)
    return grids


def main() -> None:
    import argparse

    from soa.locate import locate

    parser = argparse.ArgumentParser(
        prog="soa-extract",
        description="Extract the grid structure of the top SoA candidate per PDF",
    )
    parser.add_argument("pdfs", nargs="+")
    args = parser.parse_args()

    for pdf_path in args.pdfs:
        candidates = locate(pdf_path)
        print(f"{pdf_path}: {len(candidates)} candidates; extracting top candidate pages {candidates[0].pages}")
        for grid in extract_grid(pdf_path, candidates[0]):
            print(f"  page {grid.page_number} [{grid.source}] "
                  f"{len(grid.row_boundaries) - 1} row bands x {len(grid.col_boundaries) - 1} col bands, "
                  f"{len(grid.boxes)} boxes")
            for box in grid.boxes:
                if box.text:
                    print(f"    r{box.row_index} c{box.col_index} "
                          f"({box.x0:.0f},{box.top:.0f})-({box.x1:.0f},{box.bottom:.0f}): {box.text!r}")


if __name__ == "__main__":
    main()
