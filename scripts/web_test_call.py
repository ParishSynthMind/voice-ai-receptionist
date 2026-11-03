"""Live end-to-end test over a real Vapi web call, no phone line needed.

A local Chromium page joins a Vapi web call to the receptionist. Instead of a microphone it plays
pre-recorded caller lines (made with any text-to-speech, e.g. macOS `say`), waiting for the receptionist
to finish speaking before each one. Vapi transcribes the caller, Claude decides, the server tools run.

  VAPI_PUBLIC_KEY=... python scripts/web_test_call.py --assistant-id ID --clips clips/booking --shot out.png
Clips are played in filename order (01.wav, 02.wav, ...).
"""
from __future__ import annotations

import argparse
import functools
import http.server
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent / "web_caller"


def serve(root: Path, port: int) -> http.server.ThreadingHTTPServer:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(root))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def wait_for(page, js: str, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if page.evaluate(js):
            return True
        time.sleep(0.25)
    return False


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--assistant-id", required=True)
    p.add_argument("--clips", required=True, help="Folder of caller lines, played in name order")
    p.add_argument("--shot", help="Save a screenshot of the live transcript here")
    p.add_argument("--port", type=int, default=8799)
    p.add_argument("--quiet-seconds", type=float, default=2.5, help="Receptionist silence before the next line")
    a = p.parse_args()
    key = os.environ.get("VAPI_PUBLIC_KEY")
    if not key:
        raise SystemExit("Set VAPI_PUBLIC_KEY (the Vapi public key, not the private one).")

    root = Path(tempfile.mkdtemp())
    shutil.copy(HERE / "index.html", root / "index.html")
    clips = sorted(Path(a.clips).glob("*.wav"))
    (root / "clips").mkdir()
    for c in clips:
        shutil.copy(c, root / "clips" / c.name)
    srv = serve(root, a.port)
    quiet = f"!__state.speaking && __state.lastSpeechEnd > 0 && Date.now() - __state.lastSpeechEnd > {a.quiet_seconds * 1000}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--autoplay-policy=no-user-gesture-required",
                                                          "--use-fake-ui-for-media-stream"])
        page = browser.new_page(viewport={"width": 1100, "height": 900})
        page.goto(f"http://127.0.0.1:{a.port}/index.html")
        page.wait_for_function("typeof window.setup === 'function'", timeout=30000)
        page.evaluate("k => setup(k)", key)
        call_id = page.evaluate("id => startCall(id)", a.assistant_id)
        print("call id:", call_id)
        if not wait_for(page, quiet, 40):
            raise SystemExit("Receptionist never finished its greeting: " + str(page.evaluate("__state")))
        for clip in clips:
            print("caller says:", clip.name)
            page.evaluate("u => playClip(u)", f"clips/{clip.name}")
            page.evaluate("() => { __state.lastSpeechEnd = 0 }")
            if not wait_for(page, "__state.ended || __state.speaking", 30):
                print("  (no reply within 30s)")
            if not wait_for(page, f"__state.ended || ({quiet})", 90):
                print("  (still talking after 90s)")
            if page.evaluate("__state.ended"):
                break
        wait_for(page, "__state.ended", 20)
        if not page.evaluate("__state.ended"):
            page.evaluate("stopCall()")
            wait_for(page, "__state.ended", 10)
        time.sleep(1)
        if a.shot:
            page.screenshot(path=a.shot, full_page=True)
        state = page.evaluate("__state")
        print("ended:", state["ended"], "error:", state["error"], "mic hooked:", state.get("gum"), state.get("inputSet"))
        browser.close()
    srv.shutdown()


if __name__ == "__main__":
    main()
