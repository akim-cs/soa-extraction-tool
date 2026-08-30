"""Stage 4 — Footnote extraction and binding.

Three graded axes, all required:

  1. full text of every footnote attached to the table
  2. marker -> target linkage: every marker glyph (superscript letters/
     numbers, daggers, asterisks, parenthesised letters — a cell may carry
     several) bound to the exact cell, row, column, or header it sits on;
     a detached footnote list does not count
  3. footnote text continuing onto the FOLLOWING PAGE with no header and
     no visual indicator must be captured

Marker detection uses char-level font metadata (size + raised baseline) —
the reason pdfplumber is the primary library — plus an explicit glyph set.

Planned interface:
    extract_footnotes(page_infos, grid) -> list[Footnote]

Footnote carries: id, full text (page-continuation joined), source_pages,
continued_on_page, and attached_to references into the grid.
"""
