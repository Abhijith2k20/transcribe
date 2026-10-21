import html
import os
import queue
import re
import stat
import subprocess
import threading
import time
import urllib.request

CLOUDFLARED = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
BIN = "/tmp/cloudflared"
URL_RE = re.compile(r"https://[a-z0-9]+(?:-[a-z0-9]+)+\.trycloudflare\.com")


def cloudflare(port: int, timeout: float = 60) -> str:
    if not os.path.exists(BIN):
        urllib.request.urlretrieve(CLOUDFLARED, BIN)
        os.chmod(BIN, os.stat(BIN).st_mode | stat.S_IEXEC)
    p = subprocess.Popen([BIN, "tunnel", "--url", f"http://localhost:{port}", "--no-autoupdate"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    found: queue.Queue[str] = queue.Queue()
    registered = threading.Event()

    def drain():  # keep reading forever so cloudflared never blocks on a full pipe
        for line in p.stdout:
            if m := URL_RE.search(line):
                found.put(m.group(0))
            if "Registered tunnel connection" in line:
                registered.set()

    threading.Thread(target=drain, daemon=True).start()
    try:
        url = found.get(timeout=timeout)
    except queue.Empty:
        p.kill()
        raise RuntimeError("cloudflared didn't print a tunnel URL within 60 s")
    # The URL is printed before it works; opening it early gets an NXDOMAIN that browsers cache for minutes.
    print("Waiting for the public link to come online…")
    registered.wait(timeout)
    if not wait_until_live(url):
        print("The public link isn't answering yet. If it says 'can't be reached', wait a minute and retry, "
              "or use the backup link.")
    return url


def wait_until_live(url: str, timeout: float = 90) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(3)
    return False


def colab_proxy(port: int) -> str:
    from google.colab.output import eval_js
    return eval_js(f"google.colab.kernel.proxyPort({port})")


def start(port: int) -> tuple[str | None, str | None]:
    """Returns (public cloudflare url, colab-only backup url); either may be None."""
    try:
        backup = colab_proxy(port)
    except Exception:
        backup = None  # not running in Colab
    try:
        return cloudflare(port), backup
    except Exception as e:
        if not backup:
            raise
        print(f"Cloudflare tunnel failed ({e}). Use Colab's own link instead.")
        return None, backup


def show_link(url: str | None, backup: str | None = None):
    public = url is not None
    url = url or backup
    note = "" if public else ("This link only works in this browser, signed in to the same Google account "
                              "as Colab.")
    try:
        from IPython.display import HTML, display
        u = html.escape(url, quote=True)
        display(HTML(f"""
<div style="font-family:system-ui,sans-serif;padding:20px 0">
  <a href="{u}" target="_blank" rel="noopener" style="display:inline-block;background:#0B6E69;color:#fff;
     font-size:22px;font-weight:600;padding:14px 28px;border-radius:8px;text-decoration:none">Open the transcriber</a>
  <p style="font-size:16px;margin:12px 0 4px"><a href="{u}" target="_blank" rel="noopener">{u}</a></p>
  <p style="font-size:14px;margin:4px 0">{html.escape(note)}</p>
  {f'<p style="font-size:14px;margin:4px 0">If that link says it can’t be reached, use the <a href="{html.escape(backup, quote=True)}" target="_blank" rel="noopener">backup link</a> (works only in this browser, signed in to Colab).</p>' if public and backup else ''}
  <p style="font-size:14px;margin:4px 0">Keep this Colab tab open while you use the page.</p>
</div>"""))
    except ImportError:
        pass
    print(f"\n  Transcriber: {url}\n  {note}\n  Keep this Colab tab open while you use the page.\n")
    if public and backup:
        print(f"  Backup link (this browser only): {backup}\n")
