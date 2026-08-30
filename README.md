# SoA Extraction Tool

Extracts the **Schedule of Activities (SoA)** from clinical trial protocol
PDFs into structured JSON, with a web UI for uploading any protocol and
checking the extraction against the source.

> Status: scaffold. See [DESIGN.md](DESIGN.md) for the build plan and
> architecture. This README will be completed as phases land.

## Setup

```bash
pip install -e ".[dev]"
# optional extras
pip install -e ".[llm]"   # LLM-assisted locator rerank / sanity review
pip install -e ".[ocr]"   # OCR fallback for scanned protocols
```

Sample protocols go in `protocols/` (not committed; PDFs are gitignored).

## Run

```bash
# placeholder — CLI lands in Phase 1–7
# UI lands in Phase 8
pytest   # import smoke test
```

## Architecture

`PDF → triage → locate → extract → footnotes → stitch → JSON → UI`

See [DESIGN.md](DESIGN.md) §3 for the full description of each stage.

<!-- TO BE WRITTEN (Phase 9) — required README sections:
- Architecture of the locator and extractor (as built, vs. design)
- Output schema and why it was chosen
- Tools/APIs/models/services evaluated — chosen and rejected, and why
- Manual verification results per protocol (what was right/wrong/how)
- Where the tool breaks and what it does when it breaks (from docs/break-log.md)
- What you'd build next with two more weeks
- Which AI tools were used and where they helped or hurt
-->

## Output schema

See [DESIGN.md](DESIGN.md) §5. Structured outputs for the five sample
protocols are committed under `outputs/`.

## Failure modes

Running log: [docs/break-log.md](docs/break-log.md).
