import os
import wave

from .base import Engine, TranscriptResult, free_memory

LANGS = ("af am ar as az ba be bg bn bo br bs ca cs cy da de el en es et eu fa fi fo fr gl gu ha haw he "
         "hi hr ht hu hy id is it ja jw ka kk km kn ko la lb ln lo lt lv mg mi mk ml mn mr ms mt my ne nl "
         "nn no oc pa pl ps pt ro ru sa sd si sk sl sn so sq sr su sv sw ta te tg th tk tl tr tt uk ur uz "
         "vi yi yo zh yue").split()


def preload_cuda12():
    """ctranslate2 (faster-whisper) is built for CUDA 12. Newer Colab images ship CUDA 13, so load the
    pip-installed CUDA 12 cuBLAS/cuDNN by hand; later dlopen calls by soname then find them."""
    import ctypes
    import glob
    import site
    import sys
    dirs = {*sys.path, *site.getsitepackages()}
    pending = sorted({f for d in dirs if d for pat in ("nvidia/cublas/lib/*.so.12", "nvidia/cudnn/lib/*.so.9")
                      for f in glob.glob(os.path.join(d, pat))})
    while pending:  # some libs depend on others, so retry until nothing new loads
        failed = []
        for f in pending:
            try:
                ctypes.CDLL(f, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                failed.append(f)
        if len(failed) == len(pending):
            break
        pending = failed


class Whisper(Engine):
    id = "whisper"
    label = "Whisper"
    description = "English and non-Indian languages. Weak on mixed speech."
    languages = [""] + LANGS
    modes = ["native"]
    vram_gb = 4.5

    def __init__(self):
        self.model = None
        self.size = os.environ.get("TRANSCRIBER_WHISPER_MODEL", "large-v3")  # or large-v3-turbo

    def load(self, device):
        from faster_whisper import WhisperModel
        if device == "cuda":
            preload_cuda12()
            try:
                self.model = WhisperModel(self.size, device="cuda", compute_type="float16")
                self._warm_up()  # CUDA libraries load lazily, so fail here rather than on the user's file
                return
            except Exception as e:
                if "lib" not in str(e).lower() and "cuda" not in str(e).lower():
                    raise
                print(f"Whisper can't use the GPU ({e}). Falling back to CPU, which is much slower.")
                self.model = None
                free_memory()
        self.model = WhisperModel(self.size, device="cpu", compute_type="int8")

    def _warm_up(self):
        import numpy as np
        segments, _ = self.model.transcribe(np.zeros(16000, np.float32), language="en")
        list(segments)

    def unload(self):
        self.model = None
        free_memory()

    def transcribe(self, wav_path, lang, mode):
        # Pass samples, not the path: faster-whisper's own decoder breaks on newer PyAV (metadata_errors).
        import numpy as np
        with wave.open(wav_path) as w:
            audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        segments, info = self.model.transcribe(audio, language=lang or None, vad_filter=True)
        segs = [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]
        return TranscriptResult(" ".join(s["text"] for s in segs), info.language, segs)
