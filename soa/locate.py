"""Stage 2 — SoA candidate locator.

Find candidate SoA table regions anywhere in the document. Heading wording
is unreliable (may be absent, non-standard, or appear after the table), so
two independent signal sets are merged into a ranked list:

  * keyword signals  — known heading variants, evidence only, never required
  * structural signals — short repeated cell-mark tokens in aligned columns,
    superscript density, grid-like x-position occupancy; penalties for
    ToC/abbreviation pages that mimic table density

Must return MORE THAN ONE candidate: a protocol can contain several SoAs
(main schedule, sub-study, PK sub-schedule, long-term extension). Recall
over precision — downstream stages tolerate extra candidates.

Planned interface:
    locate(page_infos) -> list[Candidate]

Candidate carries: page range, score, and a human-readable evidence list
(logged into the output for the README's tool narrative).
"""
