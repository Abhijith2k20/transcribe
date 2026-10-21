"""Entry point: load the default engine, start the web server and the tunnel, print the link."""
import argparse
import os
import threading
import time

import uvicorn

from . import tunnel
from .app import create_app
from .engines import registry
from .engines.base import LicenseError
from .jobs import JobStore


def device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def serve(engine: str = "indic-flex", port: int = 8000, use_tunnel: bool = True, block: bool = True) -> str:
    engines = registry()
    engine = os.environ.get("TRANSCRIBER_ENGINE") or engine
    if engine not in engines:
        raise SystemExit(f"Unknown engine '{engine}'. Choose from: {', '.join(engines)}")
    store = JobStore(engines, device(), engine)

    print(f"Loading {engines[engine].label} on {store.device.upper()}… (first run downloads the model)")
    try:
        store.ensure_loaded(engine)
        print("Model ready.")
    except LicenseError as e:
        print(f"Can't load {engine}: accept the license at https://huggingface.co/{e.repo}, "
              "then transcribe a file to retry. Starting the page anyway.")
    except Exception as e:
        print(f"Couldn't load {engine}: {e}. Starting the page anyway; pick another engine there.")

    server = uvicorn.Server(uvicorn.Config(create_app(store), host="0.0.0.0", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.1)

    url, public = tunnel.start(port) if use_tunnel else (f"http://localhost:{port}", True)
    tunnel.show_link(url, public)
    while block:
        time.sleep(300)
        print(time.strftime("%H:%M"), "still running:", url, flush=True)
    return url


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--engine", default="indic-flex")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-tunnel", action="store_true")
    a = p.parse_args()
    serve(a.engine, a.port, not a.no_tunnel)


if __name__ == "__main__":
    main()
