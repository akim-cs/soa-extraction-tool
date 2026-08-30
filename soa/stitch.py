"""Stage 5 — Cross-page stitching.

Merge per-page InterpretedPage fragments into one StitchedTable. SoA tables
span 2-4 pages in TWO orientations, handled differently:

  * column continuation — the same activity rows repeat with new visit
    columns (protocol1: visits 1-8 then 9-13/ET/RT). Rows are matched by
    normalised label and the new columns are appended to the table.
  * row continuation — new activity rows continue downward under the same
    columns (protocol9 p26-29, protocol5 p50-51). Rows are appended.

Column identity comes from the deepest header level present (visit, else
week/day, else window, else period). When a page has no unique textual
keys (protocol9's banner spans, protocol15's number-only headers) its
columns are positional: pages of the same table rows-continue under
shared positional keys, while a sub-table whose rows overlap but whose
columns share nothing (protocol5 p51's sampling appendix) gets its own
positional scope instead of silently corrupting the parent table.

Sniff pages (extracted one page past a candidate range to catch
continuations the locator didn't score) are admitted only if they share
structure (>=2 row labels or >=1 textual column key) with the table so
far; footer pages with ruler lines but no relationship are excluded —
see docs/break-log.md ("token fallback fabricates a pseudo-grid").

    stitch(pages: list[InterpretedPage], sniff_pages: set[int] = frozenset())
        -> StitchedTable
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from soa.extract import InterpretedPage

MIN_DATA_ROWS = 2
MIN_DATA_COLS = 2
MIN_LABEL_OVERLAP = 0.6
MIN_SHARED_FOR_SNIFF = 2


@dataclass
class StitchedRow:
    index: int
    kind: str
    label: str
    ambiguous: bool = False
    cells: dict[int, str] = field(default_factory=dict)      # global column -> text
    markers: dict[int, list[str]] = field(default_factory=dict)
    source_pages: list[int] = field(default_factory=list)


@dataclass
class StitchedColumn:
    index: int
    period: str | None = None
    visit: str | None = None
    day_week: str | None = None
    window: str | None = None
    extra: dict[int, str] = field(default_factory=dict)
    void: bool = False


@dataclass
class StitchedTable:
    pages: list[int]
    columns: list[StitchedColumn]
    rows: list[StitchedRow]
    warnings: list[str] = field(default_factory=list)
    row_map: dict[tuple[int, int], int] = field(default_factory=dict)
    col_map: dict[tuple[int, int], int] = field(default_factory=dict)


def _normalised_label(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", label.lower())


AXIS_WORDS_STITCH = {
    "VISIT", "VISITS", "WEEK", "DAY", "WINDOW", "PERIOD", "PHASE",
    "ACTIVITY", "ASSESSMENT", "ASSESSMENTS", "PROCEDURE", "STUDY",
}


def _column_is_axis_label(page: InterpretedPage, col_index: int) -> bool:
    col = page.columns[col_index]
    values = ([v for v in (col.period, col.visit, col.day_week, col.window) if v]
              + list(col.extra.values()))
    return bool(values) and all(
        all(w in AXIS_WORDS_STITCH for w in re.sub(r"[^A-Z ]", "", v.upper()).split())
        for v in values
    )


def _column_is_void(page: InterpretedPage, col_index: int) -> bool:
    col = page.columns[col_index]
    if any([col.period, col.visit, col.day_week, col.window, col.extra]):
        return False
    return not any(col_index in row.cells for row in page.rows)


def _is_structural(page: InterpretedPage) -> bool:
    return (page.source == "rules"
            and len(page.rows) >= MIN_DATA_ROWS
            and len(page.columns) - 1 >= MIN_DATA_COLS)


def _page_keys(page: InterpretedPage) -> dict[int, tuple]:
    """Column identity keys for a page's data columns.

    Deepest textual level wins (visit > day_week > window > period). Pages
    whose keys repeat (spanning banners) or are absent fall back to
    positional keys — shared across pages of the same table, and scoped
    per page later when a page proves to be a distinct sub-table.
    """
    keys: dict[int, tuple] = {}
    ordinal = 0
    seen_values: dict[str, int] = {}
    raw: dict[int, str | None] = {}
    for ci in range(1, len(page.columns)):
        col = page.columns[ci]
        deep = col.visit or col.day_week or col.window or col.period
        raw[ci] = deep
        if deep:
            seen_values[deep] = seen_values.get(deep, 0) + 1
    for ci in range(1, len(page.columns)):
        deep = raw[ci]
        if deep is None or seen_values.get(deep, 0) > 1:
            keys[ci] = ("pos", ordinal)
        else:
            keys[ci] = ("val", deep)
        ordinal += 1
    return keys


def stitch(pages: list[InterpretedPage],
           sniff_pages: set[int] | frozenset[int] = frozenset()) -> StitchedTable:
    """Merge one candidate region's page fragments into a single table."""
    structural = sorted((p for p in pages if _is_structural(p)),
                        key=lambda p: p.page_number)
    table = StitchedTable(pages=[p.page_number for p in pages],
                          columns=[], rows=[])
    if not structural:
        table.warnings.append(
            "no page carried a ruled grid; candidate emitted as empty table")
        return table

    key_to_global: dict[tuple, int] = {}
    global_keys: set[tuple] = set()
    label_to_row: dict[str, StitchedRow] = {}
    table_positional = False

    for page in structural:
        page_labels = [_normalised_label(r.label) for r in page.rows if r.label]
        if page.page_number in sniff_pages:
            shared_labels = sum(1 for l in page_labels if l in label_to_row)
            if shared_labels < MIN_SHARED_FOR_SNIFF:
                table.warnings.append(
                    f"page {page.page_number}: sniffed page shares no structure "
                    f"with the candidate table ({shared_labels} shared labels) "
                    "— excluded")
                continue

        col_keys_full = _page_keys(page)
        overlap = sum(1 for l in page_labels if l in label_to_row)
        row_overlap = bool(label_to_row) and overlap >= max(
            MIN_SHARED_FOR_SNIFF, MIN_LABEL_OVERLAP * len(page_labels))
        shared_keys = set(col_keys_full.values()) & global_keys

        # A page whose rows heavily overlap but whose columns share nothing
        # with the table (both positional, no shared keys) is a distinct
        # sibling sub-table (protocol5 p51's sampling appendix): give its
        # columns a fresh positional scope so they never merge.
        page_positional = all(k[0] == "pos" for k in col_keys_full.values())
        sibling_scope = (
            page_positional and table_positional
            and not shared_keys and row_overlap
        )

        page_col_map: dict[int, int] = {}
        ordinal = 0
        for ci in range(1, len(page.columns)):
            col = page.columns[ci]
            if _column_is_axis_label(page, ci) and not any(
                    ci in r.cells for r in page.rows):
                table.warnings.append(
                    f"page {page.page_number}: level-label column {ci} folded "
                    "into header levels (axis words, no cell data)")
                table.col_map[(page.page_number, ci)] = -1
                continue
            if _column_is_void(page, ci):
                table.columns.append(StitchedColumn(index=len(table.columns), void=True))
                page_col_map[ci] = len(table.columns) - 1
                table.warnings.append(
                    f"page {page.page_number}: empty ruled column {ci} kept verbatim")
            else:
                key = col_keys_full.get(ci)
                if key is None:
                    continue
                scoped = ("scope", page.page_number, key[1]) if (
                    sibling_scope and key[0] == "pos") else key
                if scoped in key_to_global:
                    page_col_map[ci] = key_to_global[scoped]
                else:
                    table.columns.append(StitchedColumn(
                        index=len(table.columns),
                        period=col.period, visit=col.visit,
                        day_week=col.day_week, window=col.window,
                        extra=dict(col.extra),
                    ))
                    page_col_map[ci] = len(table.columns) - 1
                    key_to_global[scoped] = page_col_map[ci]
                    global_keys.add(scoped)
                if key[0] == "pos":
                    table_positional = True
            ordinal += 1
        for ci, gi in page_col_map.items():
            table.col_map[(page.page_number, ci)] = gi

        if page_positional and not sibling_scope:
            table.warnings.append(
                f"page {page.page_number}: no unique textual column keys; "
                "columns aligned by position — cross-page identity is approximate")

        column_continuation = row_overlap and (bool(shared_keys) or not page_positional)

        for row in page.rows:
            if row.ambiguous:
                table.warnings.append(
                    f"page {page.page_number} row {row.index} "
                    f"({row.label[:40]!r}): label with no marks and no "
                    "spanning geometry — kept as assessment, ambiguous")
            cells: dict[int, str] = {}
            markers: dict[int, list[str]] = {}
            for ci, text in row.cells.items():
                gi = page_col_map.get(ci, table.col_map.get((page.page_number, ci), -1))
                if gi == -1:
                    if text:
                        table.warnings.append(
                            f"page {page.page_number} row {row.index}: text {text!r} "
                            f"in unaligned column {ci} kept only in warnings")
                    continue
                cells[gi] = text
            for ci, glyphs in row.markers.items():
                gi = page_col_map.get(ci, table.col_map.get((page.page_number, ci), -1))
                if gi != -1:
                    markers.setdefault(gi, []).extend(glyphs)

            norm = _normalised_label(row.label)
            if column_continuation and norm and norm in label_to_row:
                target = label_to_row[norm]
                for gi, text in cells.items():
                    if gi in target.cells and target.cells[gi] != text:
                        table.warnings.append(
                            f"page {page.page_number} row {row.index}: conflicting "
                            f"text {text!r} vs {target.cells[gi]!r} in column {gi}; "
                            "first kept, second logged")
                    else:
                        target.cells[gi] = text
                for gi, glyphs in markers.items():
                    target.markers.setdefault(gi, []).extend(glyphs)
                if page.page_number not in target.source_pages:
                    target.source_pages.append(page.page_number)
                table.row_map[(page.page_number, row.index)] = target.index
            else:
                global_row = StitchedRow(
                    index=len(table.rows), kind=row.kind, label=row.label,
                    ambiguous=row.ambiguous, cells=cells, markers=markers,
                    source_pages=[page.page_number],
                )
                table.rows.append(global_row)
                if norm:
                    label_to_row[norm] = global_row
                table.row_map[(page.page_number, row.index)] = global_row.index
    return table
