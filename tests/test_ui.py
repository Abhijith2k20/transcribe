"""Playwright smoke test against the mock engine. Screenshots land in tests/screenshots/."""
import socket
import threading
import time
import zipfile
from pathlib import Path

import pytest
import uvicorn

pw = pytest.importorskip("playwright.sync_api")

from transcriber.app import create_app
from transcriber.engines.mock import Mock
from transcriber.jobs import JobStore

SHOTS = Path(__file__).parent / "screenshots"


class QuickMock(Mock):
    delay = (0.3, 0.8)


@pytest.fixture(scope="module")
def base_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(JobStore({"mock": QuickMock()}, "cpu", "mock")),
                                           port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


def test_upload_two_files(base_url, make_wav, tmp_path):
    files = [str(make_wav("one.wav")), str(make_wav("two.wav"))]
    SHOTS.mkdir(exist_ok=True)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        page = ctx.new_page()
        page.goto(base_url)
        pw.expect(page.locator("#status")).to_have_text("Running without a GPU, so transcription will be slow.")
        pw.expect(page.locator("#model")).to_have_value("mock")
        page.set_input_files("#file", files)
        pw.expect(page.locator(".file-meta")).to_have_text(["16 KB · Ready", "16 KB · Ready"])
        page.click("#start")
        pw.expect(page.locator(".file-meta")).to_have_text(["16 KB · Done", "16 KB · Done"], timeout=10000)
        pw.expect(page.locator("#output .seg time").first).to_have_text("00:00:00")

        page.click("#copy")
        pw.expect(page.locator("#toast")).to_have_text("Copied")
        assert "office" in page.evaluate("navigator.clipboard.readText()")

        with page.expect_download() as dl:
            page.click("#download")
        assert dl.value.suggested_filename == "one.txt"
        pw.expect(page.locator("#download-all")).to_have_text("Download all (2)")
        with page.expect_download() as dl:
            page.click("#download-all")
        z = tmp_path / "all.zip"
        dl.value.save_as(z)
        assert sorted(zipfile.ZipFile(z).namelist()) == ["one.txt", "two.txt"]
        pw.expect(page.locator("#start-hint")).to_have_text("All files are transcribed. Add more to continue.")

        for scheme in ("light", "dark"):
            for w, h in ((1440, 900), (390, 844)):
                page.emulate_media(color_scheme=scheme, reduced_motion="reduce")
                page.set_viewport_size({"width": w, "height": h})
                assert page.evaluate("document.documentElement.scrollWidth") <= w, "horizontal scroll"
                if w > 960:
                    assert page.evaluate("document.documentElement.scrollHeight") <= h, "desktop page scrolls"
                page.screenshot(path=SHOTS / f"{scheme}-{w}.png", full_page=True)
        browser.close()
