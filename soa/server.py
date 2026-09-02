"""Web UI backend (Phase 8): FastAPI app serving the static page and the pipeline.

    GET  /                        static page (ui/index.html)
    GET  /api/health              liveness
    GET  /api/examples            names of the committed outputs/*.json
    GET  /api/examples/{name}     one committed extraction, whitelist-validated
    POST /api/extract             upload a PDF, run the pipeline, return JSON

Uploads are handled via a temporary file and deleted after the run; nothing
is persisted. The pipeline runs synchronously — the static page shows a
loading state while it works.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from soa.pipeline import run

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UI_DIR = PROJECT_ROOT / "ui"
INDEX_HTML = UI_DIR / "index.html"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

app = FastAPI(title="SoA Extraction Tool")


def _example_files() -> dict[str, Path]:
    """Known committed extractions, keyed by file stem. The whitelist for
    /api/examples/{name} — only names found on disk are servable."""
    return {p.stem: p for p in sorted(OUTPUTS_DIR.glob("*.json"))}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX_HTML)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/examples")
def examples() -> dict:
    return {"examples": list(_example_files())}


@app.get("/api/examples/{name}")
def example(name: str) -> FileResponse:
    # Whitelist lookup: only stems found in outputs/ resolve. The filesystem
    # is never touched with the request's name, so traversal is impossible.
    path = _example_files().get(Path(name).stem)
    if path is None:
        raise HTTPException(status_code=404, detail="unknown example")
    return FileResponse(path, media_type="application/json")


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)) -> JSONResponse:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only .pdf files are accepted")
    data = await file.read()
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        result = run(str(tmp_path))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"extraction failed: {exc}") from exc
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
    # The pipeline names the temp file in document.file; restore the name
    # the user actually uploaded.
    result["document"]["file"] = Path(file.filename or "protocol.pdf").name
    return JSONResponse(result)


app.mount("/static", StaticFiles(directory=UI_DIR), name="static")


def main() -> None:
    import uvicorn

    uvicorn.run("soa.server:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
