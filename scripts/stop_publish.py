"""Stop the background publisher (local server + cloudflared)."""
import os
import subprocess
import sys
from pathlib import Path

REPORTS_DIR = Path.home() / ".claude" / "skills" / "tw-invest-suite" / "reports"
PID_FILE = REPORTS_DIR / "publisher.pid"
URL_FILE = REPORTS_DIR / "PUBLIC_URL.txt"

def kill_proc(name: str):
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/IM", name], capture_output=True)
    else:
        subprocess.run(["pkill", "-f", name], capture_output=True)

def main():
    pid = None
    if PID_FILE.exists():
        pid = int(PID_FILE.read_text().strip())
    print(f"Stopping publisher (pid={pid})…")
    if pid:
        try:
            os.kill(pid, 9) if sys.platform != "win32" else None
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        except ProcessLookupError:
            pass
    kill_proc("cloudflared")
    kill_proc("python.exe")  # in case the publisher process is named generically
    for f in (PID_FILE, URL_FILE):
        if f.exists():
            f.unlink()
    print("Done.")

if __name__ == "__main__":
    main()
