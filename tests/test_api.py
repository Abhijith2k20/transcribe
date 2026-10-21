import io
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from transcriber.app import create_app
from transcriber.engines.base import Engine, LicenseError, TranscriptResult
from transcriber.engines.mock import Mock
from transcriber.jobs import JobStore


class FastMock(Mock):
    delay = (0, 0)


@pytest.fixture
def client():
    store = JobStore({"mock": FastMock()}, "cpu", "mock")
    return TestClient(create_app(store))


def upload(client, path, **form):
    with open(path, "rb") as f:
        return client.post("/api/jobs", files={"file": (path.name, f)}, data={"engine": "mock", **form})


def wait(client, job_id):
    for _ in range(100):
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.05)
    raise AssertionError("job never finished")


def test_job_runs_to_done(client, make_wav):
    j = wait(client, upload(client, make_wav(), lang="ta", mode="native").json()["id"])
    assert j["status"] == "done" and j["text"] and j["language"] == "ta"
    assert j["audio_seconds"] == pytest.approx(0.5, abs=0.05)


@pytest.mark.parametrize("form", [{"engine": "nope"}, {"lang": "xx"}, {"mode": "romanized"}])
def test_bad_combination_is_400(client, make_wav, form):
    assert upload(client, make_wav(), **form).status_code == 400


def test_unreadable_file_fails_plainly(client, tmp_path):
    bad = tmp_path / "broken.mp3"
    bad.write_bytes(b"this is not audio")
    j = wait(client, upload(client, bad).json()["id"])
    assert j["status"] == "failed"
    assert j["error"] == "This file couldn't be read as audio. Try mp3, wav or m4a."


def test_zip_has_one_txt_per_done_job_with_unique_names(client, make_wav, tmp_path):
    p = make_wav("talk.wav")
    ids = [upload(client, p).json()["id"] for _ in range(2)]
    ids.append(upload(client, make_wav("other.wav")).json()["id"])
    for i in ids:
        wait(client, i)
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/zip?ids={','.join(ids)},missing").content))
    assert sorted(z.namelist()) == ["other.txt", "talk (2).txt", "talk.txt"]


class Recorder(Engine):
    languages, modes = [""], ["native"]

    def __init__(self, id, log, gated=False):
        self.id, self.label, self.log, self.gated = id, id, log, gated

    def load(self, device):
        if self.gated:
            raise LicenseError("org/" + self.id)
        self.log.append(f"{self.id}.load")

    def unload(self):
        self.log.append(f"{self.id}.unload")

    def transcribe(self, wav, lang, mode):
        return TranscriptResult("")


def test_engine_switch_unloads_then_loads(make_wav):
    log = []
    store = JobStore({"a": Recorder("a", log), "b": Recorder("b", log)}, "cpu", "a")
    store.ensure_loaded("a")
    client = TestClient(create_app(store))
    with open(make_wav(), "rb") as f:
        r = client.post("/api/jobs", files={"file": ("x.wav", f)}, data={"engine": "b"})
    j = wait(client, r.json()["id"])
    assert log == ["a.load", "a.unload", "b.load"]
    assert j["text"] == "(No speech found in this recording.)"


def test_gated_engine_fails_with_license_message(make_wav):
    store = JobStore({"g": Recorder("g", [], gated=True)}, "cpu", "g")
    client = TestClient(create_app(store))
    with open(make_wav(), "rb") as f:
        j = wait(client, client.post("/api/jobs", files={"file": ("x.wav", f)}, data={"engine": "g"}).json()["id"])
    assert j["error"] == "Accept the license at huggingface.co/org/g, then try again."
    assert client.get("/api/engines").json()[0]["available"] is False


def test_locked_engine_is_rejected_and_reported(make_wav):
    store = JobStore({"mock": FastMock()}, "cpu", "mock")
    store.locked = {"mock"}
    client = TestClient(create_app(store))
    e = client.get("/api/engines").json()[0]
    assert e["locked"] is True and e["available"] is False
    assert "Hugging Face token" in upload(client, make_wav()).json()["detail"]


@pytest.mark.parametrize("ranked", [{"ta": 0.9, "ml": 0.1}, [("ta", 0.9), ("ml", 0.1)], ["ta", "ml"],
                                    [{"lang": "ta", "prob": 0.9}], {"lang": "ta", "probs": {}}, "ta"])
def test_top_lang_accepts_common_shapes(ranked):
    from transcriber.engines.indic_flex import top_lang
    assert top_lang(ranked) == "ta"


def test_indic_detects_language_before_transcribing(make_wav):
    from transcriber.engines.indic_flex import IndicFlex
    calls = {}

    class FakeASR:
        def identify(self, path):
            import wave
            with wave.open(path) as w:
                calls["clip_seconds"] = w.getnframes() / w.getframerate()
            return [("ml", 0.8), ("ta", 0.2)]

    eng = IndicFlex()
    eng.asr = FakeASR()
    eng.transcribe_long = lambda asr, wav, lang, mode: calls.setdefault("lang", lang) and "ഹലോ"
    res = eng.transcribe(str(make_wav(seconds=40)), None, "mixed")
    assert calls == {"clip_seconds": 30.0, "lang": "ml"} and res.language == "ml"
