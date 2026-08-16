"""
Background publisher: start local server + cloudflared, save public URL to file,
print URL, then exit. The server and tunnel keep running in the background.

Use `stop_publish.py` to kill it.
"""
import os
import re
import socket
import subprocess
import sys
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


REPORTS_DIR = Path.home() / ".claude" / "skills" / "tw-invest-suite" / "reports"
URL_FILE = REPORTS_DIR / "PUBLIC_URL.txt"
PID_FILE = REPORTS_DIR / "publisher.pid"
LOG_FILE = REPORTS_DIR / "publisher.log"
CF_LOG = REPORTS_DIR / "cloudflared.log"


def find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=str(directory), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # quiet


def start_local_server(port: int) -> HTTPServer:
    handler = lambda *a, **kw: _Handler(*a, directory=REPORTS_DIR, **kw)
    httpd = HTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def start_cloudflared(port: int) -> subprocess.Popen:
    log_f = open(CF_LOG, "w", encoding="utf-8")
    return subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
        stdout=log_f,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def wait_for_url(timeout: int = 30) -> str | None:
    pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    end = time.time() + timeout
    while time.time() < end:
        if CF_LOG.exists():
            text = CF_LOG.read_text(encoding="utf-8", errors="ignore")
            m = pattern.search(text)
            if m:
                return m.group(0)
        time.sleep(0.5)
    return None


def write_pid():
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def main():
    write_pid()
    log = open(LOG_FILE, "a", encoding="utf-8")

    def logprint(msg):
        print(msg)
        log.write(msg + "\n")
        log.flush()

    logprint(f"=== publisher starting (pid={os.getpid()}) ===")

    port = find_free_port()
    logprint(f"[1/3] Local HTTP server on 127.0.0.1:{port} → {REPORTS_DIR}")
    httpd = start_local_server(port)

    logprint("[2/3] Spawning cloudflared…")
    proc = start_cloudflared(port)

    logprint("      waiting for public URL…")
    url = wait_for_url(timeout=30)
    if not url:
        logprint("      ❌ failed. see cloudflared.log")
        proc.terminate()
        httpd.shutdown()
        sys.exit(1)

    logprint(f"      ✓ {url}")
    URL_FILE.write_text(url + "\n", encoding="utf-8")

    logprint(f"\n[3/3] Public files:")
    for f in sorted(REPORTS_DIR.glob("*.html")):
        logprint(f"      {url}/{f.name}")
    for f in sorted(REPORTS_DIR.glob("*.md")):
        logprint(f"      {url}/{f.name}")

    logprint(f"\n✅ Serving. Latest HTML: {url}/market-screen-{time.strftime('%Y-%m-%d')}.html")
    logprint("   this process keeps the tunnel alive. Use stop_publish.py to kill it.")


if __name__ == "__main__":
    main()
