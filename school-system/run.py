"""Start the school management system.

Usage:
    python run.py

Then open the address shown in the terminal in any web browser.
Other computers on the same school network can use the LAN address.
"""

from __future__ import annotations

import socket
import sys


def local_ip() -> str:
    """Best-effort LAN address, so teachers on the school WiFi can connect."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"


def main() -> None:
    try:
        import uvicorn
    except ImportError:
        print("\nRequired packages are missing. Please run:\n", flush=True)
        print("    pip install -r requirements.txt\n", flush=True)
        sys.exit(1)

    port = 8000
    ip = local_ip()

    # If port 8000 is already taken, say so in plain language instead of
    # crashing with a traceback the school cannot interpret.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind(("0.0.0.0", port))
    except OSError:
        print("\n  PROBLEM: port 8000 is already in use.", flush=True)
        print("  The system is probably already running in another window.", flush=True)
        print("  Close that window, or check http://localhost:8000 first.\n", flush=True)
        sys.exit(1)
    finally:
        probe.close()

    print("\n" + "=" * 56, flush=True)
    print("  SCHOOL MANAGEMENT SYSTEM", flush=True)
    print("=" * 56, flush=True)
    print(f"  On this computer:      http://localhost:{port}", flush=True)
    print(f"  On the school WiFi:    http://{ip}:{port}", flush=True)
    print(flush=True)
    print("  Keep this window open while the system is in use.", flush=True)
    print("  Press Ctrl+C to stop.", flush=True)
    print("=" * 56 + "\n", flush=True)

    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    main()
