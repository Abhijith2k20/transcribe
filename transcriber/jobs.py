import os
import queue
import shutil
import tempfile
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field

from .audio import AudioError, to_wav
from .engines.base import LicenseError, free_memory

ACTIVE = ("queued", "loading_model", "transcribing")
NO_SPEECH = "(No speech found in this recording.)"


@dataclass
class Job:
    name: str
    engine: str
    lang: str
    mode: str
    src: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = "queued"
    text: str = ""
    language: str | None = None
    error: str | None = None
    started: float | None = None
    audio_seconds: float | None = None


def is_oom(e: Exception) -> bool:
    return "out of memory" in str(e).lower()


class JobStore:
    """Holds every job for the session and runs them one at a time on a single worker thread (one GPU)."""

    def __init__(self, engines: dict, device: str, default: str):
        self.engines, self.device, self.default = engines, device, default
        self.jobs: dict[str, Job] = {}
        self.order: list[str] = []
        self.loaded = None             # the Engine currently in memory
        self.unavailable: set[str] = set()   # gated engines whose license isn't accepted yet
        self.locked: set[str] = set()        # gated engines with no Hugging Face token at all
        self.tmp = tempfile.mkdtemp(prefix="transcriber-")
        self.q: queue.Queue[Job] = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

    def new_upload_path(self, filename: str) -> str:
        return os.path.join(self.tmp, uuid.uuid4().hex + os.path.splitext(filename)[1][:10])

    def submit(self, name, engine, lang, mode, src) -> Job:
        job = Job(name, engine, lang, mode, src)
        self.jobs[job.id] = job
        self.order.append(job.id)
        self.q.put(job)
        return job

    def ahead(self, job: Job) -> int:
        if job.status != "queued":
            return 0
        i = self.order.index(job.id)
        return sum(self.jobs[j].status in ACTIVE for j in self.order[:i])

    def ensure_loaded(self, engine_id: str, job: Job | None = None):
        eng = self.engines[engine_id]
        if self.loaded is eng:
            return eng
        if job:
            job.status, job.started = "loading_model", time.time()
        if self.loaded:
            self.loaded.unload()
            self.loaded = None
        try:
            eng.load(self.device)
        except LicenseError:
            self.unavailable.add(engine_id)
            raise
        self.unavailable.discard(engine_id)
        self.loaded = eng
        return eng

    def _worker(self):
        while True:
            job = self.q.get()
            try:
                self._run(job)
            except AudioError:
                job.error = "This file couldn't be read as audio. Try mp3, wav or m4a."
            except LicenseError as e:
                job.error = f"Accept the license at huggingface.co/{e.repo}, then try again."
            except Exception as e:
                traceback.print_exc()
                job.error = ("The GPU ran out of memory on this file. Try a shorter recording."
                             if is_oom(e) else f"Transcription failed: {e}")
            finally:
                job.status = "failed" if job.error else "done"
                shutil.rmtree(job.src + ".d", ignore_errors=True)
                if os.path.exists(job.src):
                    os.remove(job.src)

    def _run(self, job: Job):
        os.makedirs(job.src + ".d")
        wav = os.path.join(job.src + ".d", "audio.wav")
        job.audio_seconds = to_wav(job.src, wav)
        eng = self.ensure_loaded(job.engine, job)
        job.status, job.started = "transcribing", time.time()
        try:
            res = eng.transcribe(wav, job.lang or None, job.mode)
        except Exception as e:
            if not is_oom(e):
                raise
            # Retry once with a clean GPU.
            eng.unload()
            self.loaded = None
            free_memory()
            eng = self.ensure_loaded(job.engine)
            res = eng.transcribe(wav, job.lang or None, job.mode)
        job.text = res.text.strip() or NO_SPEECH
        job.language = res.language
