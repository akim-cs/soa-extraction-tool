# SoA Extraction Tool — Design Document

Take-home 1b: locate, extract, and display the Schedule of Activities (SoA)
from clinical trial protocol PDFs. Working brief: `1b_plan.txt` (assignment
context, verified facts about the five protocols, grading emphasis).

This document is the build plan and the architecture reference. It is written
*before* implementation; `README.md` will later describe the system **as
built** and where reality diverged from this design.

---

## 1. Problem summary

Inside an 80–250 page protocol PDF, the SoA is a single large table: rows are
assessments (grouped under category header rows), columns are visits/timepoints
(grouped under study periods, with day/week and visit windows), cells say
whether/how an activity occurs at a visit, and footnotes below the table
qualify what cells mean. The tool has three parts:

1. **Locator** — find the SoA(s) anywhere in the document. No hardcoded page
   numbers, heading wording is unreliable, there may be more than one SoA.
2. **Extractor** — produce a faithful, structured, machine-readable
   representation: row × column × cell structure, grouping hierarchy on both
   axes, visit windows, footnotes bound to the things they modify.
3. **UI** — upload ANY protocol PDF and see the extracted SoA rendered in a
   form checkable against the source. Visual polish is not graded.

Grading emphasis that shapes every design decision:

- **Recall > precision.** Dropped rows/columns are the worst failure.
- **Cells are verbatim text**, not booleans (`"3X"`, `"2X/day"`, `"(X)"`,
  `"X (if applicable)"`, superscript markers, arrows, dashes).
- **Footnotes graded on three axes:** full text of every footnote; marker →
  cell/row/column/header linkage (a cell can carry multiple markers);
  continuation of footnote text onto following pages with no header.
- Tables span 2–4 pages; headers may repeat, abbreviate, or vanish;
  continuation pages may be rotated.
- Column and row headers are both hierarchical.
- **Be faithful, not clever** — represent ambiguity, don't resolve it.
- Benchmarking multiple approaches and honest limitation reporting are
  explicitly rewarded.

## 2. Verified facts about the given protocols (grounding, not assumptions)

From the brief — useful for testing, but the tool must not depend on them:

| Protocol | Pages | Heading situation |
|---|---|---|
| protocol1.pdf | 97 | "Schedule of Events" |
| protocol5.pdf | 61 | "Time and Events Schedule", in an appendix; rotated pages |
| protocol9.pdf | 57 | Introduced as "Table 4 … flow chart", labelled "Schedule of Measures and Data" inside the table area; rotated pages |
| protocol12.pdf | 97 | "Schedule of Assessments" — heading AFTER the table, on the footnotes page |
| protocol15.pdf | 61 | No standalone heading; referenced in a sentence above "Table 1" |

All five have a genuine text layer on every page (no OCR needed for these
five). protocol5 and protocol9 have rotation-flagged pages — geometry must
be rotation-normalised before analysis. Flattening a SoA page to a 1-D text
stream demonstrably destroys the grid (verified on protocol12): column
headers land hundreds of lines from their values and superscript markers
detach from the things they annotate.

## 3. Architecture

One pipeline, five stages. Deterministic heuristics are the core; an optional
LLM assist (§7) sits beside specific stages behind a flag and is never
required.

```
PDF → [1. Triage] → [2. Locate] → [3. Extract grid] → [4. Footnotes] → [5. Stitch] → JSON → UI
```

### 3.1 Triage (`soa/triage.py`)

Per page: does it have a trustworthy embedded text layer, and what is its
orientation?

- Text-layer trust: character count, glyph sanity (replacement chars,
  garbage CMaps). Untrustworthy → mark page for OCR fallback.
- Rotation normalisation: read the page rotation flag; all downstream
  coordinates are expressed in the page's *visual* coordinate space so
  protocol5/9 continuation pages behave like portrait pages.
- Interface: `triage(pdf_path) -> list[PageInfo]` where `PageInfo` carries
  page number, rotation, text-layer trust flag, and pdfplumber page handle.

### 3.2 Locate (`soa/locate.py`)

Find candidate SoA regions. Two independent signal sets, merged into a
ranked list of candidates (multiple SoAs per document are in scope):

- **Keyword signals** — heading variants seen in the wild: *Schedule of
  Activities/Events/Assessments/Measures*, *Time and Events*, *Table of
  Events*, *flow chart*, *Study Flow Chart*. Located by regex over per-page
  text. A keyword match contributes evidence but is **not required** and is
  trusted neither for position (protocol12's heading is after the table)
  nor for existence (protocol15 has none).
- **Structural signals** — per-page scoring that does not depend on wording:
  - density of short repeated tokens (`X`, `Y`, `•`, numbers) arranged in
    aligned columns;
  - superscript-character density;
  - many distinct column x-positions with repeated occupancy across rows
    (a grid, not prose);
  - lines of tabular whitespace-separated runs.
  Penalties for page types that mimic density: table of contents (leaders
  of dots ending in page numbers), lists of abbreviations, synopses.
- Candidate = (page range, score, evidence list). Evidence is logged so the
  README can show *why* a page was nominated.
- Interface: `locate(page_infos) -> list[Candidate]`, ranked, thresholded to
  keep recall high; downstream stages tolerate extra candidates (precision
  matters less).

### 3.3 Extract (`soa/extract.py`)

Geometry-first grid recovery on one candidate page range. Never parse a
text stream.

1. Collect words/chars with coordinates from pdfplumber.
2. **Column clustering** — x-positions of cell-mark tokens form clusters;
   clusters become column anchors.
3. **Row clustering** — y-positions of all tokens form baselines; nearby
   baselines merge into logical rows (multi-line row labels).
4. **Header hierarchy (columns)** — header rows above the first data row
   stack into period > visit > day/week > window; spanning headers attach
   to the columns they geometrically cover.
5. **Row-kind classification** — a row whose cell range is empty and whose
   label spans the table width is a *category* row; otherwise an
   *assessment* row. Ambiguous rows are flagged, never guessed.
6. **Cell values** — verbatim text of tokens landing in each row×column
   box, including multi-token values and arrows. No normalisation.
- Interface: `extract_grid(page_infos, candidate) -> RawGrid` (rows, column
  anchors, header stack, per-cell tokens + coordinates).

### 3.4 Footnotes (`soa/footnotes.py`)

- **Marker detection** — characters whose font size is smaller than body
  text and whose baseline sits raised (superscripts), plus an explicit
  glyph set (letters, digits, `†`, `*`, parenthesised letters). pdfplumber
  char-level metadata (size, baseline) is the signal; this is why
  pdfplumber and not a text-stream tool is the primary library.
- **Binding** — a superscript adjacent to a cell token binds to that cell;
  adjacent to a row label → row; to a header → column. One cell can carry
  several markers.
- **Footnote text** — blocks below the table matching marker glyphs,
  collected in full, **including continuation onto the following page**
  even with no header or visual link. Continuation heuristic: page within
  the candidate region whose top-of-page text starts mid-sentence or with
  the next expected marker, before any new section heading.
- Interface: `extract_footnotes(page_infos, grid) -> list[Footnote]` with
  `attached_to` references into the grid.

### 3.5 Stitch (`soa/stitch.py`)

Merge per-page `RawGrid` fragments into one table:

- Align continuation-page columns to first-page column anchors (by x and by
  header text where repeated).
- Detect and discard repeated header rows on continuation pages (exact or
  abbreviated duplicates of the first-page header stack).
- Pages with no headers at all continue the previous page's columns.
- Rotated pages arrive pre-normalised from triage.
- Every merge decision that drops or merges content appends to `warnings[]`
  in the output — faithfulness requires a paper trail.

### 3.6 Output (`soa/schema.py`, `soa/pipeline.py`)

`pipeline.run(pdf_path) -> dict` produces the schema in §5, written as
pretty-printed JSON to `outputs/<name>.json`.

## 4. Technology decisions

### UI: FastAPI + vanilla-JS (recommended) vs Streamlit

| Criterion | FastAPI + vanilla JS | Streamlit |
|---|---|---|
| Cell-level rendering control | Full — custom HTML table, spans, tooltips | Limited — dataframe/table widgets |
| Footnote hover / marker highlight | Straightforward | Awkward |
| Side-by-side source view (stretch) | Straightforward (serve page PNGs) | Awkward |
| Setup effort | One small static page + ~4 endpoints | One file, least code |
| Dependency weight | fastapi + uvicorn | streamlit (heavy) |

**Decision: FastAPI + a single static JS page.** "Checkable against the
source" is graded; that means cell-level interactions Streamlit fights you
on, and the JS needed is small (render JSON → HTML table, superscript
markers with tooltips). Streamlit is the documented fallback if the UI
phase is time-pressed.

### PDF libraries

- **pdfplumber** (primary) — chars with font size and baseline position are
  required for superscript detection; word/line geometry suits §3.3.
- **PyMuPDF** — cross-check and page rasterisation for the UI's source view.
- **camelot** — benchmark comparator only (§8). Its lattice/stream modes are
  a genuinely different approach worth reporting against.
- **OCRmyPDF/tesseract** — behind the `ocr` extra; interface stubbed in
  Phase 1, implemented when tested against a scanned protocol (not among
  the five).

### LLM assist (`llm` extra, `SOA_LLM_ASSIST=1`)

Deliberately small: (a) optional rerank of locator candidates, (b) optional
post-extraction sanity reviewer that flags suspicious empty columns/rows.
The deterministic path is the default and produces the committed outputs.

## 5. Output schema

```json
{
  "schema_version": "1.0",
  "document": {"file": "protocol1.pdf", "pages": 97},
  "tables": [
    {
      "id": 1,
      "location": {"pages": [12, 13, 14], "heading": "Schedule of Events"},
      "column_headers": [
        {"index": 0, "period": "Screening", "visit": null, "day_week": null, "window": null},
        {"index": 1, "period": "Treatment", "visit": "Visit 2", "day_week": "Week 1", "window": "±3 days"}
      ],
      "rows": [
        {"index": 0, "kind": "category", "label": "Safety Assessments"},
        {"index": 1, "kind": "assessment", "label": "Vital signs",
         "cells": [
           {"column": 0, "column_index": 0, "value": "X", "markers": ["a"], "ambiguous": false},
           {"column": 1, "column_index": 1, "value": "3X", "markers": [], "ambiguous": true,
            "note": "value spans two column anchors; arrow?"}
         ]}
      ],
      "footnotes": [
        {"id": "a", "text": "Full footnote text, preserved across pages.",
         "attached_to": [{"row": 1, "column": 0}],
         "source_pages": [13, 14], "continued_on_page": 14}
      ],
      "warnings": ["page 13: 1 ambiguous row classification (log id row_7)"],
      "locator_evidence": ["keyword 'Schedule of Events' p12", "x-mark column density 0.81"]
    }
  ]
}
```

Rationale (feeds the README "why this schema" section):

- Rows × sparse cells (not a dense matrix) keeps merged/ambiguous cells
  representable and JSON readable.
- `kind` on rows encodes the category-vs-assessment distinction graders
  check for.
- Cells carry `value` **verbatim** plus `markers`, so footnote linkage is
  structural, not re-parseable text.
- `ambiguous`/`note`/`warnings` are first-class: faithfulness requires a
  place to put uncertainty.
- Header hierarchy is four labelled levels, matching how SoAs are actually
  authored (period > visit > day/week > window), each nullable for columns
  that only populate some levels.

## 6. Build phases

Each phase ends at a verifiable checkpoint. Order is chosen so the riskiest
assumptions (geometry-first extraction, heading unreliability) are tested
earliest against the real documents.

| Phase | Deliverable | Exit check |
|---|---|---|
| 0 | Repo scaffold, corpus config, design docs | `pytest` green: `tests/test_imports.py` imports every stage module |
| 1 | Triage: rotation-normalised page inventory CLI (`soa-triage`) | Rotated pages of protocol5/9 reported correctly; trust flags sane on all five |
| 2 | Locator: ranked candidate list, multiple per doc, evidence log | True SoA pages in top-3 for all five protocols — incl. protocol12 (heading after), protocol15 + protocol9 (no usable heading) |
| 3 | Grid extraction on ONE SoA region (easiest protocol) | Cells verbatim, grid shape visually checked against the page; no flattening |
| 4 | Header hierarchies + category-vs-assessment rows | Column header stack and category rows correct on that protocol |
| 5 | Footnotes: marker detection, binding, cross-page continuation | Superscript markers bound to exact cells; a continuation-with-no-header case captured |
| 6 | Cross-page stitching, rotated continuation pages | protocol5/9 fragments merge into single tables |
| 7 | Schema freeze + batch run (`soa-run --all`) | `outputs/protocol{1,5,9,12,15}.json` committed |
| 8 | UI: upload → pipeline → rendered table with footnote tooltips | Works end-to-end on a PDF never seen before |
| 9 | Verification pass: break log current, README written from evidence | Per-protocol manual verification table complete |

Phase 2 depends only on Phase 1; Phases 3–5 iterate protocol-by-protocol
(get it right on one, then run all five and log breaks). Nothing in
Phases 6–8 requires reworking 3–5 interfaces — stitching consumes
`RawGrid`, the UI consumes JSON.

## 7. Stretch features (strictly optional, in grading-value order)

1. **Benchmark write-up** (`docs/benchmark.md`) — run pdfplumber-geometry
   vs PyMuPDF vs camelot on the same SoA pages; record exactly where each
   broke. Explicitly rewarded by the grading text; cheap.
2. **Batch mode CLI** — `soa-run --all` over the corpus producing the
   committed output set. Nearly free once Phase 7 exists.
3. **Side-by-side UI** — rendered table next to the source page image with
   the located region highlighted. Makes manual verification fast.
4. **Confidence flags in UI** — surface `ambiguous`/`warnings` distinctly
   rather than hiding them.
5. **OCR fallback implementation** — only once a scanned protocol is
   available to test against; untested OCR code is worse than a documented
   limitation.

Explicitly **out of scope**: editing/correction UI, visual polish, user
accounts, deployment, supporting non-PDF inputs.

## 8. Likely break cases (seed for `docs/break-log.md`)

The running log lives in `docs/break-log.md`; this table seeds it. Each
entry: what, why it breaks naive approaches, design mitigation.

| # | Break case | Mitigation |
|---|---|---|
| 1 | Heading wording varies ("Schedule of Events/Assessments/Measures…", "Time and Events", "flow chart") | Locator: keywords are evidence, never a requirement (§3.2) |
| 2 | Heading appears AFTER the table (protocol12) | No positional assumption between heading and grid |
| 3 | No standalone heading at all (protocol15, protocol9) | Structural signals must nominate the region alone |
| 4 | 1-D text flattening destroys the grid (verified, protocol12) | Geometry-first extraction; no text-stream parsing anywhere |
| 5 | Rotated/landscape continuation pages (protocol5/9) | Triage normalises rotation before coordinates exist |
| 6 | Footnote text continues onto next page, no header | Dedicated continuation rule (§3.4) |
| 7 | Multiple markers per cell; styles vary (a/b/c, ¹²³, †, \*) | Font-size/baseline signal + glyph set; markers as a list |
| 8 | Category rows misread as assessments (or vice versa) | "Empty cells + spanning label" heuristic; ambiguous → flagged |
| 9 | Non-boolean cells ("3X/2 weeks", "Q2W", "(X)", arrows, dashes) | Verbatim value capture; normalisation banned in extractor |
| 10 | Merged/spanned cells; arrows crossing columns | Represent as `ambiguous: true` with note; never guess |
| 11 | Multiple SoAs per document (main + sub-study/PK/extension) | Locator returns all candidates; schema is a list of tables |
| 12 | ToC / abbreviations pages mimic table density | Structural penalties for leader-dots and two-column glossaries |
| 13 | OCR path untested by the five given PDFs (all clean text layers) | Documented limitation until tested on a scanned protocol |
| 14 | Any heuristic that silently merges/repairs rows or columns | Every silent merge logs to `warnings[]` |

## 9. Verification approach

- **Unit tests** per phase (pytest), tiny fixtures; geometry helpers are
  pure functions and easy to test.
- **Import smoke test** is Phase 0's check — every stage module imports.
- **Manual per-protocol verification** (Phase 9): for each of the five,
  fill a checklist — all rows present? all columns? verbatim cell spot
  checks? every footnote's text? every marker linked? continuations
  captured? Results go in the README **from the break log, honestly**,
  including what's wrong.
- **Generalisation evidence** (Phase 9): run against 1–2 protocols found
  online, not among the five; record the honest result in the README.

## 10. Repo layout

```
soa-extraction-tool/
├── DESIGN.md            ← this document
├── README.md            ← setup + architecture-as-built + verification + limitations
├── pyproject.toml       ← deps, pytest config, [llm]/[ocr] extras
├── soa/                 ← pipeline package (docstring-only modules at Phase 0)
│   ├── triage.py  locate.py  extract.py  footnotes.py  stitch.py
│   ├── schema.py  pipeline.py
├── tests/
├── protocols/           ← sample PDFs (gitignored, not distributed)
├── outputs/             ← committed extraction results for the five protocols
├── ui/                  ← static page served by FastAPI (Phase 8)
└── docs/
    ├── break-log.md     ← running failure-mode log
    └── benchmark.md     ← stretch: tool comparison write-up
```
