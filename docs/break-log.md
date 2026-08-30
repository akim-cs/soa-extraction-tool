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

### 2026-08-29 — extractor: three activity labels share one unruled table row (protocol1 p53)
- **What happened:** "Study drug record / Medications dispensed /
  Medications returned" occupy three text lines inside ONE ruled row band
  (no interior rules exist at the line boundaries), with one set of X
  marks on the first line. The grid reconstruction correctly yields a
  single tall box whose label is the three lines joined.
- **Root cause:** the source table itself only rules the group as one row;
  geometrically there is nothing to split on. Whether the X marks apply
  to all three activities or just the first is a source-level ambiguity.
- **Status:** faithfulness-first — kept as one logical row with the
  joined verbatim label; no invented splits. Flagged as ambiguous-row
  material for the schema phase (Phase 7).
- **Real fix:** none in the extractor; resolution requires human/LLM
  judgement, out of scope for the deterministic path.

### 2026-08-29 — extractor: token fallback fabricates a pseudo-grid on free-text pages (protocol1 p52)
- **What happened:** the locator's top candidate includes the heading-only
  page (p52, no table). The ruled path finds no rules, and the token
  fallback then clusters page furniture into a 4x7 pseudo-grid of junk
  boxes containing header/footer text.
- **Root cause:** the token fallback always *finds* some anchors — that is
  its purpose (a real borderless table must never vanish) — so pages with
  no table get phantom structure.
- **Status:** accepted for now — the stitcher (Phase 6) must discard
  fragments that share no row labels or column geometry with their
  neighbours. The alternative (extractor dropping pages silently) would
  be a recall hole, which is worse than junk that a later stage filters.
- **Real fix:** if Phase 6 shows this filtering is unreliable, gate the
  token path behind a minimum-evidence check (e.g. ≥2 rows carrying
  short-token marks in aligned columns).

### 2026-08-29 — footnotes: definition-line superscript keys raised only 0.4pt (protocol1)
- **What happened:** marker detection (smaller + raised vs the line body)
  found every in-cell marker but missed the superscript keys IN the
  footnote definition lines ("Xᵃ = ..."), so footnote ids got no marker
  and bindings silently failed. The def-line keys are 8pt raised 0.4pt on
  a 10pt body; the in-cell ones are 8pt raised 1.1pt on a 9pt body.
- **Root cause:** raise floor (0.5pt) calibrated on in-cell markers only.
- **Status:** fixed — floor lowered to 0.3pt, size-shrink requirement
  kept, so same-line baseline jitter still can't impersonate a marker.
  Watch on other sponsors' PDFs: a typeset superscript with neither size
  change nor visible raise is undetectable by geometry alone.
- **Real fix:** same as the open item above — proper baseline modelling
  (compare each char's baseline, not its top), revisited if a protocol
  shows false positives at 0.3pt.

### 2026-08-29 — extract/stitch: four geometry truths only visible across all five protocols
- **What happened:** generalising from protocol1 to all five surfaced four
  distinct page geometries:
  (1) protocol12/15 draw per-CELL frames nested ~5pt inside the logical
  columns — naïve band-building yielded 34 column bands for a 12-column
  table, and an X mark + its row label landed in adjacent slivers so the
  label "absorbed" cell text (`'SCID X'`).
  (2) protocol5/12 print markers as FULL-SIZE inline text (`'1X/week'`,
  `'Pregnancy Test***'`, `'Xa'`) — Phase-5 superscript binding finds
  nothing for them; their keys are literal letters/stars after the value.
  (3) Rotated pages (protocol5 p50-51, protocol9 p26-28) are ruled fine —
  rotation handling needed nothing more than pdfplumber's normalisation.
  (4) protocol5 p51 is rotated AND a *sibling* sampling table: its rows
  overlap p50's labels but its columns share nothing — naive label-overlap
  stitching would have interleaved its sampling columns into the schedule.
- **Root cause / fix per item:** (1) stroke-merge + label-zone split —
  labels drawn from all bands left of the first column that holds ≥2
  mark-like tokens; cells only from the mark zone. (2) known limitation —
  inline markers are text, not geometry; captured verbatim in the cell
  value but not structurally bound; would need a text-pattern fallback
  pass (see README limitations). (3) no code needed. (4) sibling-scope
  guard in the stitcher: when two pages share nothing textually but rows
  overlap, columns get a fresh positional scope instead of merging.
- **Status:** (1)(3)(4) fixed; (2) known limitation.

### 2026-08-29 — stitch: protocol9/12/15 columns over-split on nested-frame pages
- **What happened:** on protocol9 (73 columns for ~14 logical), protocol12
  (32 for ~9) and protocol15 (33 for ~16) the stitched table carries more
  columns than the source table — each logical column appears as 2-3
  physical bands from the nested-frame ruling, and per-page band drift
  defeats positional cross-page key reuse. All cells remain verbatim on
  the correct row; nothing is dropped or silently merged, but column
  identity across pages is approximate (warnings say so per page).
- **Root cause:** pages whose ruling draws frames *inside* logical
  columns can't be keyed by header text either (spans duplicate the
  banner text), leaving only alignment by position.
- **Status:** known limitation — row and cell fidelity intact (the graded
  axis); column consolidation correctly needs a dedicated geometric
  matching pass (column x-centres + header text similarity), deferred
  past the 2-day budget. protocol1 and protocol5 are NOT affected
  (protocol1: exact `visit/day_week` keys on all 15 columns).
- **Real fix:** pairwise column alignment by (midpoint distance, header
  text similarity), merging void bands per page before keying.

<!--
Template:

### YYYY-MM-DD — short title (protocol, page)
- **What happened:**
- **Root cause:**
- **Status:** fixed / known limitation
- **Real fix:**
-->
