import os

from .base import Engine, TranscriptResult, free_memory

LANGS = ("af am ar as az ba be bg bn bo br bs ca cs cy da de el en es et eu fa fi fo fr gl gu ha haw he "
         "hi hr ht hu hy id is it ja jw ka kk km kn ko la lb ln lo lt lv mg mi mk ml mn mr ms mt my ne nl "
         "nn no oc pa pl ps pt ro ru sa sd si sk sl sn so sq sr su sv sw ta te tg th tk tl tr tt uk ur uz "
         "vi yi yo zh yue").split()


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
        self.model = WhisperModel(self.size, device=device,
                                  compute_type="float16" if device == "cuda" else "int8")

    def unload(self):
        self.model = None
        free_memory()

    def transcribe(self, wav_path, lang, mode):
        segments, info = self.model.transcribe(wav_path, language=lang or None, vad_filter=True)
        segs = [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]
        return TranscriptResult(" ".join(s["text"] for s in segs), info.language, segs)
