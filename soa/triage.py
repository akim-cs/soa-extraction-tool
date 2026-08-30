"""Stage 1 — Page/document triage.

Per page: assess whether the embedded text layer is trustworthy (character
count, glyph sanity) or whether OCR is needed, and normalise page
rotation/orientation so downstream geometry works in a single coordinate
space (the page's visual space).

Planned interface:
    triage(pdf_path) -> list[PageInfo]

PageInfo carries: page number, rotation flag, text-layer trust flag, and a
handle to the (rotation-normalised) pdfplumber page.

OCR fallback is a stub behind the `ocr` extra until it can be tested
against a scanned protocol.
"""
