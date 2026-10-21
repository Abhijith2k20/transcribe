import gc
from dataclasses import dataclass


@dataclass
class TranscriptResult:
    text: str
    language: str | None = None          # detected or supplied language code
    segments: list[dict] | None = None   # [{start, end, text}] for future subtitle support


class LicenseError(Exception):
    """The user hasn't accepted the gated model's license on Hugging Face."""

    def __init__(self, repo: str):
        super().__init__(repo)
        self.repo = repo


class Engine:
    id = ""
    label = ""
    description = ""
    languages: list[str] = []   # "" means auto-detect allowed
    modes: list[str] = []
    gated_repo: str | None = None
    vram_gb = 0.0

    def load(self, device: str) -> None:
        raise NotImplementedError

    def unload(self) -> None:
        free_memory()

    def transcribe(self, wav_path: str, lang: str | None, mode: str) -> TranscriptResult:
        raise NotImplementedError


def free_memory():
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass


def is_license_error(e: Exception) -> bool:
    status = getattr(getattr(e, "response", None), "status_code", None)
    return type(e).__name__ == "GatedRepoError" or status in (401, 403)
