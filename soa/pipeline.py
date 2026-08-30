"""Pipeline orchestration: PDF -> triage -> locate -> extract ->
footnotes -> stitch -> JSON.

    run(pdf_path, *, llm_assist=False) -> dict   (schema: soa/schema.py)
    main()                                       (CLI entry, lands with Phase 7 batch mode)

The deterministic path is the default and produces the committed outputs.
LLM assist (the `llm` extra, env SOA_LLM_ASSIST=1) only reranks locator
candidates and adds a post-extraction sanity review — it never generates
cell content.
"""
