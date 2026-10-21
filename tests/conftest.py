import math
import struct
import wave

import pytest


@pytest.fixture
def make_wav(tmp_path):
    def make(name="clip.wav", seconds=0.5):
        path = tmp_path / name
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 10))) for i in range(int(16000 * seconds))))
        return path
    return make
