"""Output schema (frozen at 1.0 for the take-home submission).

The structured representation the pipeline emits (DESIGN.md §5), consumed
by the UI and graders:

  document        file name + page count
  tables[]        one entry per located SoA candidate
    location      page list for the candidate region
    column_headers[]  period > visit > day_week > window (nullable levels)
                      + extra (unassigned header text) + void flag
    rows[]        kind: category | assessment; label; sparse cells[];
                  ambiguous flag
      cells[]     column index, VERBATIM value, markers[], ambiguous flag
    footnotes[]   id, full text, marker key, attached_to[] (global row/
                  column indexes + page), source_pages, continued_on_page
    warnings[]    paper trail of every interpretive decision
    locator_evidence[]  why the locator nominated this region

Design rule: ambiguity is represented, never resolved. Rationale lives in
DESIGN.md §5 and in the README's schema section.
"""

from __future__ import annotations

SCHEMA_VERSION = "1.0"


def _column_headers(table) -> list[dict]:
    return [{
        "index": col.index,
        "period": col.period,
        "visit": col.visit,
        "day_week": col.day_week,
        "window": col.window,
        "extra": col.extra if col.extra else {},
        "void": col.void,
    } for col in table.columns]


def _rows(table) -> list[dict]:
    rows = []
    for row in table.rows:
        cells = []
        for gi in sorted(set(row.cells) | set(row.markers)):
            cells.append({
                "column": gi,
                "column_index": gi,
                "value": row.cells.get(gi, ""),
                "markers": row.markers.get(gi, []),
                "ambiguous": False,
            })
        rows.append({
            "index": row.index,
            "kind": row.kind,
            "label": row.label,
            "ambiguous": row.ambiguous,
            "cells": cells,
            "source_pages": row.source_pages,
        })
    return rows


def _footnotes(notes: list, table) -> list[dict]:
    """Remap marker attachments from page+local-band coordinates to the
    stitched global row/column indexes. Targets with no structural mapping
    keep their page reference so linkage is never dropped."""
    out = []
    for note in notes:
        attached = []
        for target in note.attached_to:
            mapped: dict = {}
            if "row" in target:
                gi = table.row_map.get((target["page"], target["row"]))
                if gi is not None:
                    mapped["row"] = gi
            if "column" in target:
                gci = table.col_map.get((target["page"], target["column"]))
                if gci is not None and gci != -1:
                    mapped["column"] = gci
            if "row" not in mapped and "column" not in mapped:
                mapped = {"page": target.get("page")}
            else:
                mapped["page"] = target.get("page")
            if mapped not in attached:
                attached.append(mapped)
        out.append({
            "id": note.id,
            "text": note.text,
            "marker": note.marker,
            "attached_to": attached,
            "source_pages": note.source_pages,
            "continued_on_page": note.continued_on_page,
        })
    return out


def table_dict(document_file: str, document_pages: int,
               tables: list[tuple]) -> dict:
    """Assemble the final JSON-serialisable document dict.

    tables = list of (stitched_table, footnotes, locator_evidence) tuples,
    one per located SoA candidate.
    """
    out_tables = []
    for i, (table, notes, evidence) in enumerate(tables, 1):
        out_tables.append({
            "id": i,
            "location": {"pages": table.pages},
            "column_headers": _column_headers(table),
            "rows": _rows(table),
            "footnotes": _footnotes(notes, table),
            "warnings": table.warnings,
            "locator_evidence": evidence,
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "document": {"file": document_file, "pages": document_pages},
        "tables": out_tables,
    }
