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

*(found while building; one section per entry)*

### 2026-08-29 — locator: X-mark signal misses X-free tables (protocol9)
- **What happened:** protocol9's SoA (p26-29, rotated) contains essentially
  no `X` cell marks (1 found) — its grid uses other glyphs. An X-density
  locator cannot see this table at all.
- **Root cause:** cell-mark glyph variety across sponsors; "X" is common
  but not universal.
- **Status:** known limitation — protocol9 is still located via
  keyword + superscript signals (score 8.0 region), but a keyword-free,
  X-free table would be missed.
- **Real fix:** a third structural channel — generic short-token column
  alignment (tokens ≤3 chars of any kind clustered into ≥4 aligned
  columns). Deferred; noted as generalisation risk.

### 2026-08-29 — locator: superscript density inverts on table pages (protocol1)
- **What happened:** prose pages in protocol1 report ~120 superscript
  chars; the actual SoA table pages report 0. Page-median font size is
  body font on prose pages (so small header/footer text reads as
  "superscript") but the table cell font on table pages (so nothing reads
  as superscript).
- **Root cause:** superscript detection relative to page-median font size.
- **Status:** fixed in locator scoring — superscripts now corroborate
  X-mark grids, never nominate a page alone. Still open for Phase 5:
  per-footnote-marker detection must be line-relative (raised baseline vs
  neighbouring text), not page-median-relative.

### 2026-08-29 — locator: keyword-only paragraphs surface as a false candidate (protocol1)
- **What happened:** protocol1 pages 35–36 mention "schedule of events" in
  body paragraphs (no table), scoring 4.0 and surfacing as candidate #2 —
  behind the true table region at 12.0, but still on the candidate list.
- **Root cause:** keyword hits are evidence-only by design, but two
  adjacent keyword pages can sum over the candidate threshold.
- **Status:** accepted — ranked below truth, and the extractor will find
  no grid on those pages, so the pipeline filters it naturally. Multiple
  candidates are a feature (protocols may contain more than one SoA).
- **Real fix (if it ever ranks first):** require each candidate to carry
  at least one structural-signal page before ranking.

<!--
Template:

### YYYY-MM-DD — short title (protocol, page)
- **What happened:**
- **Root cause:**
- **Status:** fixed / known limitation
- **Real fix:**
-->
