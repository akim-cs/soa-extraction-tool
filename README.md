# SoA Extraction Tool

Finds the **Schedule of Activities (SoA)** in a clinical trial protocol
PDF — wherever in the document it happens to be — extracts the table into
structured JSON, and serves a web UI where you can upload any protocol and
check the result against the source.

The pipeline is fully deterministic: same PDF in, same JSON out, byte for
byte (verified on all five sample protocols — see
[Verification](#verification)). No OCR, no LLM, no network calls.

## Setup

Requires Python ≥ 3.10.

```bash
pip install -e ".[dev]"
# optional extras (not needed for the committed outputs)
pip install -e ".[ocr]"    # OCRmyPDF, for scanned protocols (untested)
pip install -e ".[llm]"    # openai SDK, reserved for the unimplemented LLM assist
```

Sample protocols go in `protocols/` (gitignored; they ship with the
assignment, not with this repo).

## Running it

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
extracted table renders as an HTML grid — hierarchical column headers,
category rows, superscript footnote markers with tooltips, ambiguity
highlights, warnings, and locator evidence. The five committed example
outputs load from buttons without needing the sample PDFs.

### Tests

```bash
pytest
```

Static and server tests run anywhere; tests that need the sample PDFs
(the live upload test, locator tests) skip automatically when `protocols/`
is absent.

## How it works

`PDF → triage → locate → extract → footnotes → stitch → JSON → UI`

| Stage | Module | What it does |
|---|---|---|
| Triage | `soa/triage.py` | Per-page rotation and text-layer trust; orientations are normalised before any coordinates exist |
| Locate | `soa/locate.py` | Ranks candidate SoA regions. Structural signals (short-token columns, superscript density) nominate; keyword hits only corroborate. Headings are evidence, never position |
| Extract | `soa/extract.py` | Geometry-first grid recovery: ruled-grid reconstruction from stroke edges, token-clustering fallback for borderless tables, label-zone inference, header-level stack, category-vs-assessment rows |
| Footnotes | `soa/footnotes.py` | Superscript markers found by smaller font + raised baseline, bound to their cells; footnote text collected in full, including cross-page continuation |
| Stitch | `soa/stitch.py` | Merges per-page fragments into one table: column/row continuation, positional keys for number-only headers, sniff-page admission. Every merge is logged |
| Assemble | `soa/schema.py`, `soa/pipeline.py` | Frozen `schema_version: 1.0` JSON. `pipeline.run(pdf_path) -> dict` is the single entry point |
| Serve | `soa/server.py` + `ui/` | FastAPI: `GET /` static page, `GET /api/health`, `GET /api/examples[...]` (whitelisted committed outputs), `POST /api/extract` (multipart PDF upload) |

### Divergences from DESIGN.md

[DESIGN.md](DESIGN.md) is the pre-build plan; the three places reality
departed from it:

- **LLM assist (design §7) — evaluated, not built.** The deterministic
  path met the brief inside the 2-day budget, so the `llm` extra and the
  `SOA_LLM_ASSIST` flag are documented but inert. The one use that would
  make sense — reranking locator candidates — never touches cells anyway.
- **camelot benchmark (stretch §7.1) — not run.** pdfplumber's
  char-level font and baseline metadata turned out to be load-bearing
  for superscript detection, and PyMuPDF covers the cross-check role, so
  a formal benchmark fell off the time budget rather than being half-run
  and over-claimed. See *Tools evaluated* below.
- **The locator scores page ranges, not single pages**, and passes a
  "sniff" page one past each range so continuations it didn't score stay
  reachable. A page that shares no structure with its neighbours is then
  excluded downstream by the stitcher — recall first, precision later.

## Output schema

Frozen at `schema_version: 1.0` — [DESIGN.md §5](DESIGN.md) has the JSON
shape and a worked example. One design goal: **faithfulness must be
representable**. In practice:

- Rows × sparse cells, not a dense matrix, so merged, spanned and void
  cells stay representable and the JSON stays readable in a diff.
- Cell values are **verbatim** text — `X`, `1X/week`, `(X)`,
  `Pregnancy Test***`, arrows, dashes. Reducing them to booleans is
  banned in the extractor.
- Rows are classified `category | assessment`; anything the geometry
  can't decide is kept and flagged `ambiguous: true`, never guessed.
- Footnotes are first-class: full text, marker key, structural
  `attached_to` links into rows and columns, continuation across pages.
- Every interpretive decision appends to `warnings[]`, so the output
  carries its own audit trail.

## Tools evaluated

| Tool | Verdict | Why |
|---|---|---|
| **pdfplumber** | chosen (primary) | Char-level font size + baseline are the only reliable superscript signal; word/line geometry drives grid recovery |
| **PyMuPDF** | chosen (secondary) | Fast cross-check |
| camelot (lattice/stream) | not adopted | Superscript/font metadata unavailable at cell level; benchmark deferred past the budget rather than half-run |
| Streamlit | rejected for UI | Dataframe widgets fight cell spans and per-marker tooltips; FastAPI + one static page gives more control per line of code |
| LLM (OpenAI) assist | evaluated, not implemented | Deterministic path met the brief; reranking locator candidates was the one use that couldn't tempt cell generation |
| OCRmyPDF/tesseract | stub, untested | All five sample protocols have clean text layers; shipping an untested OCR path is worse than a documented limitation |

## Verification

Phase 9 re-checked the committed outputs end to end:

1. **Reproducibility.** A fresh `pipeline.run` on each protocol
   reproduces the committed `outputs/*.json` byte for byte — the
   committed results are exactly what the current code emits.
2. **Row-level spot checks.** Every table's first three rows (labels +
   X marks) were matched against raw text extracted independently from
   the source PDF page. All five protocols pass, including the rotated
   pages in protocols 5 and 9.
3. **Per-protocol truth table** (location = pdf pages; all pass):

| Protocol | SoA pages | What makes it hard | Result |
|---|---|---|---|
| protocol1 | 52–55 | 15 columns, exact visit/day-week keys; keyword-only prose decoys rank below truth | ✅ rows/cells/footnotes correct; 3-label shared-row kept verbatim + flagged |
| protocol5 | 50–51 | rotated appendix pages; sibling sampling table shares row labels but not columns | ✅ sibling columns scoped apart; inline full-size markers verbatim (unbound) |
| protocol9 | 25–30 | X-free table (1 X total), rotated, "Table 4 flow chart" heading | ✅ located on keyword+superscript evidence; positional columns |
| protocol12 | 48–49 | heading AFTER the table; full-size inline markers | ✅ rows/cells correct; markers unbound (see limitations) |
| protocol15 | 24–26 | no standalone heading; number-only column headers | ✅ located structurally; "Screening" banner kept as ambiguous assessment (source draws it as an unruled text band) |

## Where it breaks (known limitations)

The running log with root causes is
[docs/break-log.md](docs/break-log.md). The honest shortlist:

- **Nested-frame pages over-split columns** (protocols 9/12/15). Where
  the source draws ruled frames just inside its logical columns, the
  grid recovery yields more physical column bands than there are logical
  columns, and column identity across pages is approximate (the
  `warnings[]` say so per page). Rows and cells stay verbatim and on the
  right row — the part the brief weights most — but folding the bands
  back into logical columns needs a geometric matching pass (midpoint
  distance + header-text similarity) that didn't fit in the budget.
  Protocols 1 and 5 are unaffected.
- **Inline full-size markers are captured, not linked** (protocols
  5/12). Some tables print markers as body text — `1X/week`,
  `Pregnancy Test***`, `Xa` — with no superscript geometry to detect.
  They survive verbatim in the cell value; a text-pattern pass would
  bind them structurally.
- **A keyword-free, X-free table would be missed.** The structural
  channels are short-token density and superscript density; a table with
  neither signal, and no keywords, nominates no candidate. None of the
  five samples is one — but I'd want to know before deploying this on a
  new sponsor's templates.
- **The token fallback confirms its own existence.** On pages with no
  ruled grid, token clustering fabricates a coarse pseudo-grid — by
  design, because a borderless table must never vanish. The stitcher
  filters fragments that share no structure with the candidate region.
- **The OCR path is untested**: every protocol I have has a clean text
  layer, so scanned protocols are out of evidence.
- **Superscript detection is geometric.** A typeset marker with no size
  change and no visible raise is undetectable without a font/baseline
  model per line.

## Assumptions and questions for a clinical SME

Assumptions the pipeline makes (each also shows up in
[docs/break-log.md](docs/break-log.md) where it shaped the output):

- Columns are visits/timepoints; rows are assessments. The label zone is
  everything between the leftmost table edge and the first data
  column — inferred when nothing labels it.
- Marker detection trusts only superscript geometry (smaller font +
  raised baseline). Markers printed as body text (`Pregnancy Test***`,
  `Xa`) are captured in the verbatim cell value but not linked.
- Ambiguity is preserved, never resolved: anything the geometry can't
  decide is kept verbatim and flagged `ambiguous: true`.

And the questions I'd ask a clinical SME rather than guess (each is left
as `ambiguous` in the committed outputs):

1. **protocol1 row 28** — the label contains three assessment names
   concatenated (`if screening ECG not done within 48hrs of
   randomisation visit then do ECG`). Which single assessment owns the
   screened-row checkmarks — and is this one assessment with a
   triple-printed label, or three assessments sharing a row?
2. **protocol9 form codes** — row labels carry codes like `(04)`,
   `(05)`, `(12)`. Are these CRF data-form numbers (row identity
   metadata worth its own field) or just prose in the label?
3. **protocol15 `Screening` banner** — the source draws it as an
   unruled text band; I kept it as an ambiguous assessment row. Does it
   read as a category header to a clinical eye?
4. **Visit-window semantics** — header windows like `+/− 5d` are
   captured per column. Would a downstream consumer want them propagated
   onto a per-visit object, or is per-column fidelity enough?

## With two more weeks

1. The column-consolidation pass for nested-frame pages — the one known
   structural debt; the fix is specified in the break log.
2. Text-pattern binding for inline full-size markers (protocols 5/12).
3. A third structural locator channel (generic short-token column
   alignment) so keyword-free, X-free tables are findable.
4. The real camelot/PyMuPDF benchmark and the deferred generalisation
   check (1–2 unseen protocols found online), reported honestly.
5. A tested OCR fallback behind the `ocr` extra.

## AI tools

I built this with an LLM pair-programmer (Maincode's Matilda Code),
working in a plan–implement–verify loop per phase. It earned its keep
ground-truthing the five PDFs (a geometry inventory per page), turning
break-log observations into focused heuristics, and keeping the audit
trail — warnings, break-log, the DESIGN↔README divergence notes —
current while the code moved. Its mistakes were just as educational:
heuristics calibrated on protocol1 broke on protocols 9/12/15 (the
nested-frame column split), which only surfaced because the full corpus
was run and every regression went into
[docs/break-log.md](docs/break-log.md). The LLM-assist flag inside the
tool itself is deliberately unimplemented, for the reasons under
[Divergences from DESIGN.md](#divergences-from-designmd).
