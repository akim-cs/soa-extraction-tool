# SoA Extraction Tool

Extracts the **Schedule of Activities (SoA)** from clinical trial protocol
PDFs into structured JSON, with a web UI for uploading any protocol and
checking the extraction against the source.

The pipeline is fully deterministic: geometry-first heuristics over
pdfplumber coordinates, no text-stream parsing, no network calls. Given
the same PDF it reproduces the same JSON byte for byte (verified for all
five sample protocols — see [Verification](#verification)).

## Setup

Requires Python ≥ 3.10.

```bash
pip install -e ".[dev]"
# optional extras (not required for the committed outputs)
pip install -e ".[ocr]"    # OCRmyPDF, for scanned protocols (untested)
pip install -e ".[llm]"    # openai SDK, reserved for the (unimplemented) LLM assist
```

Sample protocols go in `protocols/` (gitignored, not distributed).

## Run

### CLI / batch

```bash
soa-run protocols/protocol1.pdf            # writes outputs/protocol1.json
soa-run protocols/*.pdf                    # batch over the corpus
soa-locate protocols/protocol1.pdf         # ranked SoA candidates + evidence
soa-triage protocols/protocol1.pdf         # rotation / text-layer inventory
soa-extract protocols/protocol1.pdf        # dump the reconstructed grid
```

### Web UI

```bash
soa-serve        # http://127.0.0.1:8000
```

Upload any protocol PDF: the full pipeline runs on the upload and the
extracted table renders as an HTML grid (hierarchical column headers,
category rows, superscript footnote markers with tooltips, ambiguity
highlights, warnings, locator evidence). Buttons for the five committed
example outputs load them without needing the sample PDFs.

### Tests

```bash
pytest
```

Static/server tests run anywhere; the live upload test and locator tests
skip automatically when `protocols/` is absent.

## Architecture

`PDF → triage → locate → extract → footnotes → stitch → JSON → UI`

| Stage | Module | What it does |
|---|---|---|
| Triage | `soa/triage.py` | Per-page rotation + text-layer trust; orientations are normalised before any coordinates exist |
| Locate | `soa/locate.py` | Ranks candidate SoA regions from structural signals (short-token column density, superscript density) with keyword hits as corroborating evidence only — headings are never required or trusted for position |
| Extract | `soa/extract.py` | Geometry-first grid recovery: ruled-grid reconstruction from stroke edges, token-clustering fallback for borderless tables, label-zone inference, header-level stack, category-vs-assessment rows |
| Footnotes | `soa/footnotes.py` | Superscript marker detection (smaller font + raised baseline), marker→cell binding, footnote text incl. cross-page continuation |
| Stitch | `soa/stitch.py` | Merges per-page fragments into one table: column-continuation and row-continuation, positional keys for number-only headers, sniff-page admission, all merges logged |
| Assemble | `soa/schema.py`, `soa/pipeline.py` | Frozen `schema_version: 1.0` JSON; `pipeline.run(pdf_path) -> dict` is the single entry point |
| Serve | `soa/server.py` + `ui/` | FastAPI: `GET /` static page, `GET /api/health`, `GET /api/examples[...]` (whitelisted committed outputs), `POST /api/extract` (multipart PDF upload) |

Divergences from [DESIGN.md](DESIGN.md) (the design doc is pre-build; this
section is as-built):

- **LLM assist (design §7) was evaluated and rejected for the 2-day
  budget.** The `llm` extra and `SOA_LLM_ASSIST` are documented but the
  option is unimplemented; the deterministic path produces all committed
  outputs. An LLM rerank would only ever reorder locator candidates —
  never generate cells.
- **camelot benchmark (stretch §7.1) not run.** pdfplumber's char-level
  font/baseline metadata proved load-bearing for superscript detection
  early, and PyMuPDF is a rasterisation cross-check; a formal
  pdfplumber-vs-camelot benchmark fell off the time budget. See
  *Tools evaluated* below.
- **Locator scores candidate page ranges, not single pages**, and passes
  a "sniff" page one past each range so continuations the locator didn't
  score are still reachable (a ruler-line footer page that shares no
  structure is excluded by the stitcher, not the extractor — recall
  first, precision later).

## Output schema

Frozen at `schema_version: 1.0` (see `soa/schema.py` and DESIGN.md §5 for
the JSON shape and worked example). Chosen so that **faithfulness is
representable**:

- Rows × sparse cells (not a dense matrix) so merged/ambiguous cells and
  void columns stay representable, and JSON stays human-readable.
- Every cell value is **verbatim** text (`X`, `1X/week`, `(X)`,
  `Pregnancy Test***`, arrows, dashes) — normalisation to booleans is
  banned in the extractor.
- `kind: category | assessment` on rows; `ambiguous: true` flags anywhere
  the geometry didn't decide (kept, never guessed).
- Footnotes are first-class: full text, marker key, structural
  `attached_to` links to rows/columns, cross-page continuation.
- Every interpretive decision (aligned positional columns, excluded sniff
  pages, text kept only in warnings) appends to `warnings[]` — the output
  carries its own audit trail.

## Tools evaluated

| Tool | Verdict | Why |
|---|---|---|
| **pdfplumber** | chosen (primary) | Char-level font size + baseline positions are the only reliable superscript signal; word/line geometry drives grid recovery; rotation normalisation |
| **PyMuPDF** | chosen (secondary) | Fast cross-check + page rasterisation for the UI's source view |
| camelot (lattice/stream) | not adopted | Genuinely different approach; superscript/font metadata unavailable at cell level; benchmark deferred past the budget rather than claimed |
| Streamlit | rejected for UI | Dataframe widgets fight cell-level rendering, spans, per-marker tooltips; FastAPI + one static page won on control per line of code |
| LLM (OpenAI) assist | evaluated, rejected (unimplemented) | Deterministic path met the brief; reranking candidates was the only use that couldn't tempt cell generation |
| OCRmyPDF/tesseract | stub, untested | All five given protocols have clean text layers; shipping an untested OCR path is worse than a documented limitation |

## Verification

Phase 9 re-verified the committed outputs end to end:

1. **Reproducibility** — a fresh `pipeline.run` on each of the five
   sample protocols reproduces the committed `outputs/*.json` byte for
   byte (no drift between code and committed results).
2. **Row-level spot check** — each table's first three rows (labels +
   X marks) were matched against the source PDF page by independent raw
   text extraction: all five protocols pass, including the rotated
   protocol5/protocol9 pages.
3. **Protocol-by-protocol truth table** (location pdf-pages; all pass):

| Protocol | SoA pages | What makes it hard | Result |
|---|---|---|---|
| protocol1 | 52–55 | 15 columns, exact visit/day-week keys; keyword-only prose decoys rank below truth | ✅ rows/cells/footnotes correct; 3-label shared-row kept verbatim + flagged |
| protocol5 | 50–51 | rotated appendix pages; sibling sampling table shares row labels but not columns | ✅ sibling columns scoped apart; inline full-size markers verbatim (unbound) |
| protocol9 | 25–30 | X-free table (1 X total), rotated, "Table 4 flow chart" heading | ✅ located on keyword+superscript evidence; positional columns |
| protocol12 | 48–49 | heading AFTER the table; full-size inline markers | ✅ rows/cells correct; markers unbound (see limitations) |
| protocol15 | 24–26 | no standalone heading; number-only column headers | ✅ located structurally; "Screening" banner kept as ambiguous assessment (source draws it with no spanning rule) |

## Where it breaks (known limitations)

Full running log with root causes: [docs/break-log.md](docs/break-log.md).
The honest list:

- **Nested-frame pages over-split columns** (protocol9/12/15): pages that
  draw ruled frames ~5pt inside each logical column produce more physical
  column bands than the source table has logical columns, and positional
  cross-page identity is approximate (`warnings[]` say so per page).
  **Rows and cells stay verbatim and correctly attached** — the graded
  axis — but column consolidation needs a geometric matching pass
  (midpoint distance + header-text similarity) that exceeded the 2-day
  budget. protocol1 and protocol5 are unaffected.
- **Inline full-size markers are captured but not structurally bound**
  (protocol5/12): `1X/week`, `Pregnancy Test***`, `Xa` print the marker
  as body text, not superscript geometry. The text is verbatim in the
  cell value; a text-pattern binding pass would map them structurally.
- **A keyword-free, X-free table would be missed**: the locator's
  structural channels are short-token density and superscript density; a
  table with neither signal nor keywords scores no candidate.
- **Token fallback confirms its own existence**: on pages with no ruled
  grid, token-clustering fabricates a coarse pseudo-grid — deliberately
  (a borderless table must never vanish); the stitcher filters fragments
  that share no structure with the candidate.
- **OCR path untested**: scanned protocols are out of evidence (all five
  samples have clean text layers).
- **Superscript detection is geometric**: a typeset marker with no size
  change and no visible raise is undetectable without a font/baseline
  model per line.

## Assumptions and questions for a clinical SME

Assumptions the pipeline makes explicitly (each also appears in
[docs/break-log.md](docs/break-log.md) where it shaped output):

- Columns are visits/timepoints; rows are assessments; the label zone sits
  between the leftmost table edge and the first data column — inferred
  when nothing labels it.
- Marker detection trusts only superscript geometry (smaller font + raised
  baseline). Markers printed as body text (`Pregnancy Test***`, `Xa`) are
  captured in the verbatim cell value, not linked.
- Ambiguity is preserved, never resolved: a row or cell the geometry can't
  decide is kept verbatim and flagged `ambiguous: true`.

Questions we would ask a clinical SME rather than guess (left as
`ambiguous` in the committed outputs):

1. **protocol1 row 28** — the label contains three assessment names
   concatenated (`if screening ECG not done within 48hrs of
   randomisation visit then do ECG`). Which single assessment owns the
   screened-row checkmarks, and is this one assessment with a
   triple-printed label or three assessments sharing a row?
2. **protocol9 form codes** — row labels carry codes like `(04)`, `(05)`,
   `(12)`. Are these CRF data-form numbers (i.e. row identity metadata
   worth its own field) or just prose in the label?
3. **protocol15 `Screening` banner** — the source draws it as an unruled
   text band; kept as an ambiguous assessment row. Confirm it reads as a
   category header to a clinical reader.
4. **Visit-window semantics** — header windows like `+/– 5d` are captured
   per column; do graders expect them propagated to a per-visit object,
   or is per-column fidelity sufficient?

## With two more weeks

1. Column consolidation pass for nested-frame pages (the one known
   structural debt; fix is specified in the break log).
2. Text-pattern binding for inline full-size markers (protocol5/12).
3. Third structural locator channel (generic short-token column
   alignment) so keyword-free, X-free tables are findable.
4. Real camelot/PyMuPDF benchmark and the deferred generalisation check
   (1–2 unseen protocols found online), reported honestly.
5. Tested OCR fallback behind the `ocr` extra.

## AI tools

This tool was built with an LLM pair-programmer (Maincode's Matilda
Code) driving a plan–implement–verify loop per phase. Where it helped:
recon and ground-truthing the five PDFs (geometry inventory per page),
turning break-log observations into focused heuristics, and keeping the
audit trail (warnings, break-log, DESIGN↔README divergence notes) current
as the code moved. Where it hurt / required human-style correction:
heuristics calibrated on protocol1 broke on protocols 9/12/15 (the
nested-frame column split), which only surfaced by running the full
corpus and logging honestly — every such regression is in
[docs/break-log.md](docs/break-log.md). The LLM assist flag in the tool
itself is deliberately unimplemented, for the reasons above.
