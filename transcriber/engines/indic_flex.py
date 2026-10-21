import inspect
import sys

from .base import Engine, LicenseError, TranscriptResult, free_memory, is_license_error

CORE_LANGS = ["en", "as", "bn", "brx", "doi", "gu", "hi", "kn", "ks", "kok", "mai", "ml", "mni",
              "mr", "ne", "or", "pa", "sa", "sat", "sd", "ta", "te", "ur", "bho", "bhb"]


class IndicEngine(Engine):
    """Shared loader: the model code ships inside the HF repo."""
    vram_gb = 6.0
    pass_mode = True

    def __init__(self):
        self.asr = self.transcribe_long = self.path = None

    def load(self, device):
        from huggingface_hub import snapshot_download
        try:
            self.path = snapshot_download(self.gated_repo)
        except Exception as e:
            if is_license_error(e):
                raise LicenseError(self.gated_repo) from e
            raise
        # flex and core ship modules with the same names, so drop any copy from the other model
        for name in ("indic_transcribe", "long_form"):
            sys.modules.pop(name, None)
        sys.path.insert(0, self.path)
        from indic_transcribe import IndicTranscribe
        from long_form import transcribe_long
        # The model card shows from_pretrained(model_dir) only; pass device if it's accepted, else move after.
        if "device" in inspect.signature(IndicTranscribe.from_pretrained).parameters:
            self.asr = IndicTranscribe.from_pretrained(self.path, device=device)
        else:
            self.asr = IndicTranscribe.from_pretrained(self.path)
            if hasattr(self.asr, "to"):
                self.asr.to(device)
        self.transcribe_long = transcribe_long

    def unload(self):
        self.asr = self.transcribe_long = None
        if self.path in sys.path:
            sys.path.remove(self.path)
        free_memory()

    def transcribe(self, wav_path, lang, mode):
        kw = {"lang": lang} if lang else {}   # omitting lang = auto-detect
        if self.pass_mode:
            kw["mode"] = mode
        out = self.transcribe_long(self.asr, wav_path, **kw)
        if isinstance(out, dict):
            return TranscriptResult(out.get("text", ""), out.get("lang") or lang)
        if isinstance(out, (tuple, list)):  # (text, lid) style
            return TranscriptResult(str(out[0]), str(out[1]) if len(out) > 1 and isinstance(out[1], str) else lang)
        return TranscriptResult(str(out), lang)


class IndicFlex(IndicEngine):
    id = "indic-flex"
    label = "Indic-Transcribe Flex"
    description = "Best for Indian languages mixed with English. Keeps English words in English."
    languages = [""] + CORE_LANGS + ["hne", "bgc"]
    modes = ["mixed", "native", "romanized"]
    gated_repo = "bodhan-ai/indic-transcribe-flex"
