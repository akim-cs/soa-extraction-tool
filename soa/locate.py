"""Stage 2 — SoA candidate locator.

Find candidate SoA table regions anywhere in the document. Heading wording
is unreliable (may be absent, non-standard, or appear after the table), so
two independent signal sets are merged into a ranked list:

  * keyword signals  — known heading variants, evidence only, never required
  * structural signals — X-mark token grids, superscript density, column
    alignment; penalties for table-of-contents pages that mimic density

Must return MORE THAN ONE candidate: a protocol can contain several SoAs
(main schedule, sub-study, PK sub-schedule, long-term extension). Recall
over precision — downstream stages tolerate extra candidates.

    locate(pdf_path) -> list[Candidate]

Candidate carries: page range (contiguous run), score, and a human-readable
evidence list (preserved into the output JSON as locator_evidence).

CLI: python -m soa.locate <pdf> [<pdf> ...]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pdfplumber

HEADING_PATTERNS = [
    re.compile(
        r"schedule\s+of\s+(study\s+)?(activities|assessments|events|measures"
        r"|procedures|evaluations|visits)",
        re.IGNORECASE,
    ),
    re.compile(r"time\s+and\s+events", re.IGNORECASE),
    re.compile(r"table\s+of\s+events", re.IGNORECASE),
    re.compile(r"(study\s+)?flow\s+chart", re.IGNORECASE),
]

TOC_LEADER = re.compile(r"\.{4,}\s*\d+")
XMARK = re.compile(r"[xX]+")

# Scoring weights (calibrated against the five given protocols).
W_KEYWORD = 2.0
W_KEYWORD_CAP = 6.0
W_XMARK = 2.0
XMARK_SATURATION = 30
W_SUPERSCRIPT = 1.5
SUPERSCRIPT_SATURATION = 50
W_COLUMNALIGN = 1.0
MIN_ALIGNED_COLUMNS = 4
TOC_PENALTY = 3.0

PAGE_SCORE_THRESHOLD = 2.0
CANDIDATE_SCORE_THRESHOLD = 3.0
PAGE_GAP_MERGE = 1


@dataclass
class PageSignals:
    page_number: int
    keywords: list[str]
    xmark_count: int
    aligned_columns: int
    superscript_count: int
    is_toc_like: bool
    score: float
    evidence: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    pages: list[int]
    score: float
    evidence: list[str] = field(default_factory=list)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def score_page(page) -> PageSignals:
    """Score one pdfplumber page for SoA-likeness. Purely from page content."""
    text = page.extract_text() or ""
    words = page.extract_words()

    keywords = sorted({m.group(0) for pat in HEADING_PATTERNS for m in pat.finditer(text)})

    xmarks = [w for w in words if XMARK.fullmatch(w["text"])]
    distinct_x = len({round(w["x0"]) for w in xmarks})

    median_size = _median([c["size"] for c in page.chars])
    superscripts = sum(
        1 for c in page.chars if median_size and c["size"] < 0.72 * median_size
    )

    toc_lines = sum(
        1 for line in text.splitlines() if TOC_LEADER.search(line)
    )
    is_toc = toc_lines >= 3

    evidence = []
    score = 0.0

    if keywords:
        kw_score = min(len(keywords) * W_KEYWORD, W_KEYWORD_CAP)
        score += kw_score
        evidence.append(f"keywords {keywords} (+{kw_score:.1f})")
    if xmarks:
        xm_score = min(len(xmarks) / XMARK_SATURATION, 1.0) * W_XMARK
        score += xm_score
        evidence.append(f"{len(xmarks)} x-marks (+{xm_score:.1f})")
        if distinct_x >= MIN_ALIGNED_COLUMNS:
            score += W_COLUMNALIGN
            evidence.append(f"x-marks in {distinct_x} aligned columns (+{W_COLUMNALIGN:.1f})")
        # Superscripts corroborate a grid but never nominate alone: prose
        # pages inflate the count via small header/footer fonts, and table
        # pages deflate it because the median font IS the small cell font.
        if superscripts:
            ss_score = min(superscripts / SUPERSCRIPT_SATURATION, 1.0) * W_SUPERSCRIPT
            score += ss_score
            evidence.append(f"{superscripts} superscript chars (+{ss_score:.1f})")
    if is_toc:
        score -= TOC_PENALTY
        evidence.append(f"table-of-contents look ({toc_lines} leader lines) (-{TOC_PENALTY:.1f})")

    return PageSignals(
        page_number=page.page_number,
        keywords=keywords,
        xmark_count=len(xmarks),
        aligned_columns=distinct_x,
        superscript_count=superscripts,
        is_toc_like=is_toc,
        score=score,
        evidence=evidence,
    )


def _group_candidates(signals: list[PageSignals]) -> list[Candidate]:
    """Merge pages above threshold (bridging small gaps) into candidate regions."""
    hits = [s for s in signals if s.score >= PAGE_SCORE_THRESHOLD]
    if not hits:
        return []

    groups: list[list[PageSignals]] = [[hits[0]]]
    for sig in hits[1:]:
        if sig.page_number - groups[-1][-1].page_number <= PAGE_GAP_MERGE + 1:
            groups[-1].append(sig)
        else:
            groups.append([sig])

    candidates = []
    for group in groups:
        first, last = group[0].page_number, group[-1].page_number
        pages = list(range(first, last + 1))
        score = sum(s.score for s in group)
        evidence = []
        for s in group:
            for ev in s.evidence:
                evidence.append(f"p{s.page_number}: {ev}")
        candidates.append(Candidate(pages=pages, score=score, evidence=evidence))
    return candidates


def locate(pdf_path: str) -> list[Candidate]:
    """Rank candidate SoA regions for a protocol PDF. Best first."""
    with pdfplumber.open(pdf_path) as pdf:
        signals = [score_page(page) for page in pdf.pages]

    candidates = [c for c in _group_candidates(signals) if c.score >= CANDIDATE_SCORE_THRESHOLD]
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="soa-locate",
        description="Rank candidate Schedule-of-Activities regions in protocol PDF(s)",
    )
    parser.add_argument("pdfs", nargs="+")
    args = parser.parse_args()

    for pdf_path in args.pdfs:
        print(f"{pdf_path}")
        candidates = locate(pdf_path)
        if not candidates:
            print("  no candidates above threshold")
        for rank, cand in enumerate(candidates, 1):
            pages = f"p{cand.pages[0]}-{cand.pages[-1]}" if len(cand.pages) > 1 else f"p{cand.pages[0]}"
            print(f"  #{rank} {pages} (score {cand.score:.1f})")
            for ev in cand.evidence:
                print(f"      {ev}")


if __name__ == "__main__":
    main()
