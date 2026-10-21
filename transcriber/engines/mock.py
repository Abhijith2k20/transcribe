import random
import time

from .base import Engine, TranscriptResult

TEXT = {
    "mixed": "நான் நேற்று office-க்கு late-ஆ போனேன். ഇന്ന് meeting ഉണ്ട്, so please be on time.",
    "native": "நான் நேற்று ஆஃபீஸுக்கு லேட்டா போனேன். ഇന്ന് മീറ്റിംഗ് ഉണ്ട്, സോ പ്ലീസ് ബി ഓൺ ടൈം.",
}


class Mock(Engine):
    id = "mock"
    label = "Mock engine"
    description = "Fake engine for local development. Returns canned text."
    languages = ["", "ta", "ml", "en", "hi", "kn"]
    modes = ["mixed", "native"]
    delay = (1.0, 3.0)

    def load(self, device):
        pass

    def transcribe(self, wav_path, lang, mode):
        time.sleep(random.uniform(*self.delay))
        return TranscriptResult(TEXT[mode], lang or "ta")
