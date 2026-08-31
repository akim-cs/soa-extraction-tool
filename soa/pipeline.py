"""Pipeline orchestration: PDF -> triage -> locate -> extract ->
footnotes -> stitch -> JSON.

    run(pdf_path, *, llm_assist=False) -> dict   (schema: soa/schema.py)
    main()                                       (CLI/batch, writes outputs/)

The deterministic path is the default and produces the committed outputs.
LLM assist (the `llm` extra, env SOA_LLM_ASSIST=1) is a documented but
UNIMPLEMENTED option (evaluated and rejected for the 2-day budget — see
README): it would only rerank locator candidates, never generate cells.
"""

from __future__ import annotations

import json
from pathlib import Path

from soa.extract import extract_grid, interpret_grid
from soa.footnotes import extract_footnotes
from soa.locate import Candidate, locate
from soa.schema import table_dict
from soa.stitch import stitch
from soa.triage import triage


def run(pdf_path: str) -> dict:
    """Run the full deterministic pipeline on one protocol PDF."""
    pages_info = triage(pdf_path)
    candidates = locate(pdf_path)
    if not candidates:
        candidates = [Candidate(pages=[], score=0.0, evidence=["no candidate scored above threshold"])]

    tables = []
    for cand in candidates:
        if not cand.pages:
            continue
        sniff = cand.pages[-1] + 1
        wanted = cand.pages + ([sniff] if sniff <= len(pages_info) else [])
        grids = extract_grid(pdf_path, Candidate(pages=wanted, score=0.0))
        interpreted = [interpret_grid(g) for g in grids]
        notes = extract_footnotes(pdf_path, grids, interpreted)
        table = stitch(interpreted, sniff_pages={sniff})
        if not table.rows:
            # Keyword-only false candidates (prose pages that mention the
            # schedule) assemble no grid rows — the natural self-filter,
            # see docs/break-log.md (keyword-only paragraphs, protocol1).
            continue
        tables.append((table, notes, cand.evidence))

    return table_dict(
        document_file=Path(pdf_path).name,
        document_pages=len(pages_info),
        tables=tables,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="soa-run",
        description="Run the full SoA extraction pipeline and write JSON outputs",
    )
    parser.add_argument("pdfs", nargs="+", help="protocol PDFs to process")
    parser.add_argument("-o", "--outdir", default="outputs",
                        help="output directory (default: outputs/)")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(exist_ok=True)
    for pdf_path in args.pdfs:
        result = run(pdf_path)
        out_path = outdir / f"{Path(pdf_path).stem}.json"
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        n_tables = len(result["tables"])
        n_rows = sum(len(t["rows"]) for t in result["tables"])
        print(f"{pdf_path} -> {out_path} ({n_tables} tables, {n_rows} rows)")


if __name__ == "__main__":
    main()
