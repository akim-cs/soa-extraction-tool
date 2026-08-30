"""Stage 3 — Grid-structure extractor.

Geometry-first recovery of the true row x column x cell structure of one
located candidate region. NEVER parses a flattened text stream — on real
SoA pages that detaches column headers from cell values and superscript
markers from the values they annotate.

Steps: cluster token x-positions into column anchors; cluster y-baselines
into logical rows (multi-line labels merge); build the hierarchical column
header stack (period > visit > day/week > window); classify rows as
category headers vs assessment rows (empty-cell spanning label = category,
ambiguous = flagged, never guessed); capture every cell value VERBATIM —
"3X", "(X)", "X (if applicable)", arrows, dashes — no normalisation to
booleans, ever.

Merged/spanned cells and arrows crossing columns are represented as
ambiguity (`ambiguous: true` + note), not resolved.

Planned interface:
    extract_grid(page_infos, candidate) -> RawGrid
"""
