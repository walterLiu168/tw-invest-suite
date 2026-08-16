"""
Publish the latest market-screen HTML via Cloudflare quick tunnel.

Steps:
  1. Start a local HTTP server on a free port serving reports/
  2. Spawn `cloudflared tunnel --url http://localhost:PORT`
  3. Capture the public *.trycloudflare.com URL
  4. Print + save it to reports/PUBLIC_URL.txt

Re-run anytime to refresh the public URL.
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


def find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=str(directory), **kwargs)

    def end_headers(self):
        # Disable cache so updates are immediate
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        # Quiet
        pass


def start_local_server(port: int) -> HTTPServer:
    handler = lambda *a, **kw: _Handler(*a, directory=REPORTS_DIR, **kw)
    httpd = HTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def start_cloudflared(port: int) -> subprocess.Popen:
    """Spawn cloudflared quick tunnel. Returns Popen; output goes to a temp file."""
    log_path = REPORTS_DIR / "cloudflared.log"
    log_f = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
        stdout=log_f,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    proc._log_file = log_f  # keep handle
    return proc


def wait_for_url(proc: subprocess.Popen, timeout: int = 30) -> str | None:
    """Poll cloudflared log for the public URL."""
    log_path = REPORTS_DIR / "cloudflared.log"
    pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    end = time.time() + timeout
    while time.time() < end:
        if log_path.exists():
            text = log_path.read_text(encoding="utf-8", errors="ignore")
            m = pattern.search(text)
            if m:
                return m.group(0)
        if proc.poll() is not None:
            # Process died
            break
        time.sleep(0.5)
    return None


def main():
    print("=== tw-invest-suite · publish HTML via Cloudflare quick tunnel ===\n")

    # 1. Start local HTTP server
    port = find_free_port()
    print(f"[1/3] Starting local HTTP server on 127.0.0.1:{port} → {REPORTS_DIR}")
    httpd = start_local_server(port)

    # 2. Start cloudflared
    print(f"[2/3] Spawning cloudflared quick tunnel…")
    proc = start_cloudflared(port)

    # 3. Wait for URL
    print(f"      (waiting up to 30s for the public URL)")
    url = wait_for_url(proc, timeout=30)
    if not url:
        print("      ❌ Failed to get URL. Check reports/cloudflared.log for details.")
        proc.terminate()
        httpd.shutdown()
        sys.exit(1)

    print(f"      ✓ Public URL: {url}")

    # 4. Save the URL
    URL_FILE.write_text(url + "\n", encoding="utf-8")
    print(f"      saved → {URL_FILE}")

    # Summary
    print(f"\n[3/3] Now serving:")
    # List HTML files
    for f in sorted(REPORTS_DIR.glob("*.html")):
        print(f"      {url}/{f.name}")

    print(f"\n✅ Done. Open in browser: {url}/market-screen-{time.strftime('%Y-%m-%d')}.html")
    print(f"\nNote: this is a quick tunnel — it lives only while this process is running.")
    print(f"      cloudflared log: {REPORTS_DIR}/cloudflared.log")
    print(f"      URL is also saved to: {URL_FILE}")
    print(f"\nPress Ctrl-C to stop the tunnel + local server.")

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\nStopping…")
        proc.terminate()
        httpd.shutdown()


if __name__ == "__main__":
    main()
