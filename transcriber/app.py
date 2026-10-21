import io
import os
import shutil
import time
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .jobs import JobStore

WEB = Path(__file__).resolve().parent.parent / "web"
MAX_BYTES = 100 * 1024 * 1024  # Cloudflare quick tunnels cap uploads around here


def gpu_info():
    try:
        import torch
        if torch.cuda.is_available():
            return True, torch.cuda.get_device_name(0)
    except Exception:
        pass
    return False, None


def create_app(store: JobStore) -> FastAPI:
    app = FastAPI(title="Indic Transcriber")
    app.mount("/static", StaticFiles(directory=WEB), name="static")
    gpu, gpu_name = gpu_info()

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")

    @app.get("/api/health")
    def health():
        return {"ok": True, "gpu": gpu, "gpu_name": gpu_name,
                "loaded_engine": store.loaded.id if store.loaded else None}

    @app.get("/api/engines")
    def engines():
        return [{"id": e.id, "label": e.label, "description": e.description, "languages": e.languages,
                 "modes": e.modes, "available": e.id not in store.unavailable and e.id not in store.locked,
                 "locked": e.id in store.locked, "gated_repo": e.gated_repo,
                 "loaded": store.loaded is e, "default": e.id == store.default}
                for e in store.engines.values()]

    @app.post("/api/jobs")
    def create_job(file: UploadFile = File(...), engine: str = Form(...), lang: str = Form(""),
                   mode: str = Form("")):
        eng = store.engines.get(engine)
        if not eng:
            raise HTTPException(400, f"Unknown engine: {engine}")
        if engine in store.locked:
            raise HTTPException(400, f"{eng.label} needs a Hugging Face token. Add HF_TOKEN in Colab and run all again.")
        if lang not in eng.languages:
            raise HTTPException(400, f"{eng.label} doesn't support language '{lang}'.")
        mode = mode or eng.modes[0]
        if mode not in eng.modes:
            raise HTTPException(400, f"{eng.label} doesn't support output style '{mode}'.")
        path = store.new_upload_path(file.filename or "")
        with open(path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        if os.path.getsize(path) > MAX_BYTES:
            os.remove(path)
            raise HTTPException(413, "This file is over 100 MB. Convert it to mp3 and try again.")
        return {"id": store.submit(file.filename or "recording", engine, lang, mode, path).id}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = store.jobs.get(job_id)
        if not job:
            raise HTTPException(404, "No such job. The Colab session may have restarted.")
        return {"status": job.status, "name": job.name, "engine": job.engine, "text": job.text,
                "language": job.language, "error": job.error, "ahead": store.ahead(job),
                "elapsed_seconds": round(time.time() - job.started) if job.started else 0,
                "audio_seconds": job.audio_seconds}

    @app.get("/api/zip")
    def zip_(ids: str = Query("")):
        buf, used = io.BytesIO(), set()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for job_id in filter(None, ids.split(",")):
                job = store.jobs.get(job_id)
                if not job or job.status != "done":
                    continue
                stem, name, n = Path(job.name).stem or "transcript", "", 1
                while not name or name in used:
                    name = f"{stem}.txt" if n == 1 else f"{stem} ({n}).txt"
                    n += 1
                used.add(name)
                z.writestr(name, job.text + "\n")
        return Response(buf.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="transcripts.zip"'})

    return app
