"""Stage 4 — Footnote extraction and binding.

Three graded axes, all required:

  1. full text of every footnote attached to the table
  2. marker -> target linkage: every marker glyph (superscript letters/
     numbers, daggers, asterisks, parenthesised letters — a cell may carry
     several) bound to the exact cell, row, column, or header it sits on;
     a detached footnote list does not count
  3. footnote text continuing onto the FOLLOWING PAGE with no header and
     no visual indicator must be captured

Marker detection is LINE-RELATIVE (see docs/break-log.md, 2026-08-29):
a marker is a char smaller than its own line's body font AND sitting on a
raised baseline — never the page median. A superscript adjacent to a cell
token binds to that cell; one below the table is a footnote key, not a
binding target.

Footnote-definition blocks are detected below (or, for continuation pages
with no table above them, above) the table region. Continuation heuristic:
a non-definition, non-heading, non-furniture line joins the currently open
footnote; the open footnote survives a page boundary only onto a page that
has no table above the incoming lines.

    extract_footnotes(pdf_path, grids, pages) -> list[Footnote]

Side effect: bound markers are written back onto the InterpretedPage rows
(markers stripped from the verbatim cell text into row.markers), so later
stages see value="X" + markers=["a"] instead of the fused "Xa".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pdfplumber

from soa.extract import InterpretedPage, PageGrid
from soa.locate import HEADING_PATTERNS

MARKER_CHARS = set("abcdefghijklmnpqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
                   "0123456789†‡§*¶#")
DEF_KEY = re.compile(r"^\s*[\(\[]?([A-Za-z0-9†‡§*¶#]{1,3})[\)\].:=]?\s")
BLOCK_OPENER = re.compile(r"^[A-Z][A-Za-z& /]{1,40}:")
FURNITURE_NUM = re.compile(r"\d")

SUPER_SIZE_RATIO = 0.95
SUPER_RAISE_MIN = 0.3  # protocol1 def-line keys are raised only 0.4pt (8pt on 10pt body)
MARKER_GAP_FACTOR = 3.0


@dataclass
class MarkerOccurrence:
    glyph: str
    page: int
    row: int | None      # band row index within the page grid
    column: int          # band column index


@dataclass
class Footnote:
    id: str
    text: str
    marker: str | None = None
    attached_to: list[dict] = field(default_factory=list)
    source_pages: list[int] = field(default_factory=list)
    continued_on_page: int | None = None

    @property
    def legend(self) -> bool:
        return self.marker is None


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _line_clusters(chars: list[dict], tol: float = 2.0) -> list[list[dict]]:
    """Cluster chars into text lines by baseline. A char joins the current
    line when its top sits within tol of the line's running mean — this is
    what lets a raised superscript stay on its own line."""
    chars = sorted(chars, key=lambda c: (c["top"], c["x0"]))
    lines: list[list[dict]] = []
    for char in chars:
        if lines and abs(char["top"] - _mean([c["top"] for c in lines[-1]])) <= tol:
            lines[-1].append(char)
        else:
            lines.append([char])
    return lines


def _line_text(line: list[dict]) -> str:
    parts = []
    prev = None
    for char in sorted(line, key=lambda c: c["x0"]):
        if prev is not None and char["x0"] - prev["x1"] > char["size"] * 0.25 and (not parts or parts[-1] != " "):
            parts.append(" ")
        parts.append(char["text"])
        prev = char
    return "".join(parts).strip()


def _line_body_size(line: list[dict]) -> float:
    return sorted(c["size"] for c in line)[len(line) // 2] if line else 0.0


def _super_runs(line: list[dict]) -> list[list[dict]]:
    body = _line_body_size(line)
    if not body:
        return []
    body_chars = [c for c in line if c["size"] >= body * SUPER_SIZE_RATIO]
    body_top = _mean([c["top"] for c in body_chars]) if body_chars else _mean(
        [c["top"] for c in line])
    supers = [
        c for c in line
        if c["size"] <= body * SUPER_SIZE_RATIO
        and c["top"] < body_top - SUPER_RAISE_MIN
        and c["text"].strip() in MARKER_CHARS
    ]
    supers.sort(key=lambda c: c["x0"])
    runs: list[list[dict]] = []
    for char in supers:
        if runs and char["x0"] - runs[-1][-1]["x1"] <= char["size"] * MARKER_GAP_FACTOR:
            runs[-1].append(char)
        else:
            runs.append([char])
    return runs


def _box_at(grid: PageGrid, x: float, y: float):
    for box in grid.boxes:
        if box.x0 - 1 <= x < box.x1 and box.top - 1 <= y < box.bottom + 1:
            return box
    return None


def _table_bounds(grid: PageGrid | None) -> tuple[float | None, float | None]:
    if grid is None or not grid.row_boundaries:
        return None, None
    return grid.row_boundaries[0], grid.row_boundaries[-1]


def _normalised(text: str) -> str:
    return re.sub(r"[\W0-9]+", "", text.lower())


def _furniture_lines(pdf, page_numbers: list[int]) -> dict[int, set[str]]:
    """Normalised text of lines that repeat across pages near page edges
    (running headers/footers) — excluded from footnote collection."""
    counts: dict[str, int] = {}
    per_page: dict[int, set[str]] = {}
    for pageno in page_numbers:
        page = pdf.pages[pageno - 1]
        texts = set()
        for line in _line_clusters(page.chars):
            top = min(c["top"] for c in line)
            if top < 90 or top > page.height - 90:
                texts.add(_normalised(_line_text(line)))
        per_page[pageno] = texts
        for text in texts:
            if text:
                counts[text] = counts.get(text, 0) + 1
    return {pageno: {t for t in texts if counts.get(t, 0) >= 2}
            for pageno, texts in per_page.items()}


def _parse_definitions(pdf, grids: dict[int, PageGrid], page_numbers: list[int]) -> list[Footnote]:
    furniture = _furniture_lines(pdf, page_numbers)
    footnotes: list[Footnote] = []
    open_note: Footnote | None = None
    prev_table_page = False

    def close_note():
        nonlocal open_note
        if open_note is not None:
            open_note.text = open_note.text.strip()
            if open_note.text:
                footnotes.append(open_note)
        open_note = None

    def start_note(note_id: str, marker: str | None, text: str, pageno: int):
        nonlocal open_note
        close_note()
        open_note = Footnote(id=note_id, text=text, marker=marker,
                             source_pages=[pageno])

    for pageno in page_numbers:
        grid = grids.get(pageno)
        table_top, table_bottom = _table_bounds(grid)
        page = pdf.pages[pageno - 1]
        this_table_page = grid is not None and grid.source == "rules"

        for line in _line_clusters(page.chars):
            top = min(c["top"] for c in line)
            text = _line_text(line)
            if not text or _normalised(text) in furniture.get(pageno, set()):
                continue
            if top > page.height - 60:
                continue
            above = table_top is not None and top < table_top - 2
            below = table_bottom is None or top >= table_bottom - 2
            if not (above or below):
                continue
            if any(pat.search(text) for pat in HEADING_PATTERNS):
                close_note()
                continue
            if above:
                # Above-table lines only continue an open footnote when there
                # is no table above them on this page and either this page or
                # the previous one has no table at all.
                if open_note is not None and (not this_table_page or not prev_table_page):
                    _continue_note(open_note, text, pageno)
                continue
            # below-table lines
            def match_block(text: str) -> bool:
                return bool(BLOCK_OPENER.match(text))

            if match_block(text):
                start_note(text.split(":", 1)[0].strip(), None, text, pageno)
                continue
            match = DEF_KEY.match(text)
            sep_x = min(
                (c["x0"] for c in line
                 if c["size"] >= _line_body_size(line) * SUPER_SIZE_RATIO
                 and c["text"] in "=:." and c["x0"] > line[0]["x0"]),
                default=None,
            )
            supers = [c for run in _super_runs(line) for c in run
                      if sep_x is None or c["x0"] < sep_x]
            markers = "".join(c["text"] for c in supers if c["text"] in MARKER_CHARS)
            if match and (markers or re.search(r"[\)\].:=]", text[: match.end() + 2])):
                key = re.sub(r"[\s\)\(\[\].:=]+", "", match.group(1))
                note_id = key + markers if markers and markers not in key else key
                start_note(note_id, markers or None, text, pageno)
                continue
            if open_note is not None:
                _continue_note(open_note, text, pageno)
        prev_table_page = this_table_page
    close_note()
    return footnotes


def _continue_note(note: Footnote, text: str, pageno: int) -> None:
    if note.text.endswith("-"):
        note.text = note.text + text
    else:
        note.text = f"{note.text} {text}"
    if pageno not in note.source_pages:
        note.source_pages.append(pageno)
    if pageno != note.source_pages[0]:
        note.continued_on_page = pageno


def _detect_occurrences(page, grid: PageGrid) -> list[MarkerOccurrence]:
    table_top, table_bottom = _table_bounds(grid)
    if table_top is None:
        return []
    region = [c for c in page.chars
              if table_top - 2 <= c["top"] < table_bottom]
    occurrences: list[MarkerOccurrence] = []
    for line in _line_clusters(region):
        for run in _super_runs(line):
            for char in run:
                if char["text"] not in MARKER_CHARS:
                    continue
                box = _box_at(grid, (char["x0"] + char["x1"]) / 2, char["top"])
                if box is None:
                    continue
                occurrences.append(MarkerOccurrence(
                    glyph=char["text"],
                    page=grid.page_number,
                    row=box.row_index,
                    column=box.col_index,
                ))
    return occurrences


def _bind(interpreted: dict[int, InterpretedPage], grid: PageGrid,
          occurrence: MarkerOccurrence, footnotes: list[Footnote]) -> None:
    page = interpreted.get(grid.page_number)
    if page is None or occurrence.row is None:
        return
    row = next((r for r in page.rows if r.index == occurrence.row), None)
    if row is not None and occurrence.column > 0:
        value = row.cells.get(occurrence.column, "")
        if value.endswith(occurrence.glyph):
            row.cells[occurrence.column] = value[: -len(occurrence.glyph)]
        row.markers.setdefault(occurrence.column, []).append(occurrence.glyph)
    for note in footnotes:
        if note.marker != occurrence.glyph:
            continue
        if occurrence.row is not None and occurrence.row < page.header_rows:
            target = {"column": occurrence.column, "page": grid.page_number}
        elif occurrence.column == 0:
            target = {"row": occurrence.row, "page": grid.page_number}
        else:
            target = {"row": occurrence.row, "column": occurrence.column,
                      "page": grid.page_number}
        if target not in note.attached_to:
            note.attached_to.append(target)


def _dedup(footnotes: list[Footnote]) -> list[Footnote]:
    seen: dict[tuple[str, str], Footnote] = {}
    for note in footnotes:
        key = (note.id, " ".join(note.text.split()))
        if key in seen:
            existing = seen[key]
            for pageno in note.source_pages:
                if pageno not in existing.source_pages:
                    existing.source_pages.append(pageno)
        else:
            seen[key] = note
    for note in footnotes:
        canonical = seen[(note.id, " ".join(note.text.split()))]
        if canonical is not note:
            canonical.attached_to.extend(
                t for t in note.attached_to if t not in canonical.attached_to)
    return list(seen.values())


def extract_footnotes(pdf_path: str, grids: list[PageGrid],
                      pages: list[InterpretedPage]) -> list[Footnote]:
    """Extract footnotes for one candidate region and bind markers to cells."""
    grids_by_page = {g.page_number: g for g in grids}
    interpreted = {p.page_number: p for p in pages}
    page_numbers = sorted(grids_by_page)
    with pdfplumber.open(pdf_path) as pdf:
        footnotes = _parse_definitions(pdf, grids_by_page, page_numbers)
        occurrences = []
        for pageno in page_numbers:
            grid = grids_by_page[pageno]
            if grid.source != "rules":
                continue
            occurrences.extend(_detect_occurrences(pdf.pages[pageno - 1], grid))
    footnotes = _dedup(footnotes)
    for occurrence in occurrences:
        _bind(interpreted, grids_by_page[occurrence.page], occurrence, footnotes)
    return footnotes
