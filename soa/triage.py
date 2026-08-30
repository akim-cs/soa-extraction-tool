"""Stage 1 — Page/document triage.

Per page: assess whether the embedded text layer is trustworthy (character
count, replacement-glyph ratio) or whether OCR is needed, and record page
rotation. pdfplumber reports rotated pages in their VISUAL coordinate
space (a 90-degree-rotated letter page reports 792x612), so downstream
geometry needs no manual transform — only the rotation flag itself is
carried forward.

Trust heuristic (a starting point, tuned against real corpora): a page is
trusted when it has a plausible character count and almost no U+FFFD
replacement glyphs (the signature of a broken CMap). Pages failing either
check are OCR candidates; the OCR fallback itself is a stub behind the
`ocr` extra until it can be tested against a scanned protocol.

    triage(pdf_path) -> list[PageInfo]

CLI: python -m soa.triage <pdf> [<pdf> ...] — prints the page inventory.
"""

from __future__ import annotations

from dataclasses import dataclass

import pdfplumber

MIN_CHARS_TRUSTWORTHY = 50
MAX_REPLACEMENT_RATIO = 0.01


@dataclass
class PageInfo:
    page_number: int  # 1-based
    rotation: int
    width: float
    height: float
    char_count: int
    replacement_chars: int
    text_trustworthy: bool

    @property
    def needs_ocr(self) -> bool:
        return not self.text_trustworthy


def triage(pdf_path: str) -> list[PageInfo]:
    infos = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            chars = page.chars
            count = len(chars)
            replacements = sum(1 for c in chars if c["text"] == "�")
            trustworthy = (
                count >= MIN_CHARS_TRUSTWORTHY
                and (replacements / count if count else 1.0) < MAX_REPLACEMENT_RATIO
            )
            infos.append(
                PageInfo(
                    page_number=page.page_number,
                    rotation=page.rotation,
                    width=page.width,
                    height=page.height,
                    char_count=count,
                    replacement_chars=replacements,
                    text_trustworthy=trustworthy,
                )
            )
    return infos


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="soa-triage",
        description="Per-page rotation and text-layer trust inventory",
    )
    parser.add_argument("pdfs", nargs="+", help="protocol PDF(s) to inspect")
    args = parser.parse_args()

    for pdf_path in args.pdfs:
        infos = triage(pdf_path)
        rotated = [i for i in infos if i.rotation]
        ocr = [i for i in infos if i.needs_ocr]
        print(f"{pdf_path}: {len(infos)} pages")
        if rotated:
            listing = ", ".join(f"p{i.page_number} ({i.rotation}deg)" for i in rotated)
            print(f"  rotated pages: {listing}")
        else:
            print("  rotated pages: none")
        if ocr:
            listing = ", ".join(f"p{i.page_number} ({i.char_count} chars)" for i in ocr)
            print(f"  untrusted text (OCR candidates): {listing}")
        else:
            print("  untrusted text (OCR candidates): none")


if __name__ == "__main__":
    main()
