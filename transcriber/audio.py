import subprocess
import wave


class AudioError(Exception):
    pass


def to_wav(src: str, dst: str) -> float:
    """Convert any ffmpeg-readable audio/video to 16 kHz mono PCM WAV. Returns duration in seconds."""
    r = subprocess.run(["ffmpeg", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst],
                       capture_output=True)
    if r.returncode:
        raise AudioError(r.stderr.decode(errors="replace")[-500:])
    with wave.open(dst) as w:
        return w.getnframes() / w.getframerate()
