"""Stage 5 — Cross-page stitching.

Merge per-page RawGrid fragments into one table. SoA tables routinely span
2-4 pages; continuation pages may repeat the header (exact or abbreviated),
omit it, or be rotated (rotation is already normalised by triage).

Alignment is by column anchors (x-position, then header text where present).
Rows must never be silently dropped: every merge decision that discards or
merges content (e.g. a repeated header row) appends to `warnings[]` so the
output keeps a paper trail of interpretation vs. source.

Planned interface:
    stitch(fragments: list[RawGrid]) -> RawGrid + warnings
"""
