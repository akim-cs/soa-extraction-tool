# Break Log

Running log of every failure mode found while building and testing the SoA
extraction tool. Format per entry: **what happened · root cause · status
(fixed / known limitation) · what a real fix requires.**

This log is the source material for the README's per-protocol verification,
"where it breaks", and "what next" sections — write those from here, not
from memory.

---

## Known break cases (from design — DESIGN.md §8, not yet observed in code)

| # | Case | Mitigation planned |
|---|---|---|
| 1 | Heading wording varies across documents | Locator keyword signals are evidence only, never required |
| 2 | Heading appears AFTER the table (protocol12) | No positional assumption heading↔grid |
| 3 | No standalone heading at all (protocol15, protocol9) | Structural signals must nominate region alone |
| 4 | 1-D text flattening destroys the grid (verified on protocol12 by brief author) | Geometry-first extraction only |
| 5 | Rotated/landscape continuation pages (protocol5/9) | Triage normalises rotation first |
| 6 | Footnote text continues onto next page with no header | Dedicated continuation rule |
| 7 | Multiple footnote markers per cell; styles vary (1/2/3, a/b/c, †, *) | Font-size/baseline detection + glyph set; marker lists |
| 8 | Category header rows vs assessment rows | Empty-cells + spanning-label heuristic; ambiguous → flagged |
| 9 | Non-boolean cells ("3X/2 weeks", "Q2W", "(X)", arrows, dashes) | Verbatim capture; normalisation banned |
| 10 | Merged/spanned cells; arrows crossing columns | `ambiguous: true` + note; never guess |
| 11 | Multiple SoAs per document | Locator returns all candidates; output is a list of tables |
| 12 | ToC/abbreviations pages mimic table density | Structural penalties (leader dots, glossaries) |
| 13 | OCR path untested — all five given PDFs have clean text layers | Known limitation until a scanned protocol is tested |
| 14 | Heuristics that silently merge/repair structure | Every silent merge logs to `warnings[]` |

## Observed failures

*(none yet — log entries here as they are found, one section per entry)*

<!--
Template:

### YYYY-MM-DD — short title (protocol, page)
- **What happened:**
- **Root cause:**
- **Status:** fixed / known limitation
- **Real fix:**
-->
