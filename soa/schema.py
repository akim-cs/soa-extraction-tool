"""Output schema definition and validation.

The structured representation the pipeline emits (DESIGN.md §5):

  document        file name + page count
  tables[]        one entry per located SoA
    location      page range + heading text (if any)
    column_headers[]  period > visit > day_week > window (nullable levels)
    rows[]        kind: category | assessment; label; sparse cells[]
      cells[]     column index, VERBATIM value, markers[], ambiguous flag
    footnotes[]   id, full text, attached_to[], source_pages, continuation
    warnings[]    paper trail of every interpretive decision
    locator_evidence[]  why the locator nominated this region

Design rule: ambiguity is represented, never resolved. Rationale lives in
DESIGN.md §5 and will be summarised in the README's schema section.
"""
