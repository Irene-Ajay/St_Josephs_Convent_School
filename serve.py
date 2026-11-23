"""Run the portal website locally with the Supabase keys from .env.

A plain HTML page cannot read a .env file, so this tiny server (Python
standard library only, nothing to install) serves the site and generates
/config.js on the fly from SUPABASE_URL and SUPABASE_ANON_KEY.

    python serve.py                 # open http://localhost:8000
    python serve.py --port 9000
    python serve.py --write-config  # write config.js for static hosting
                                    # (Netlify, GitHub Pages, etc.)

Only the URL and the anon (publishable) key ever reach the browser.
"""

from __future__ import annotations

import argparse
import http.server
import json
import sys
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
BROWSER_KEYS = ("SUPABASE_URL", "SUPABASE_ANON_KEY")


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def config_js() -> str:
    env = load_env()
    config = {
        "url": env.get("SUPABASE_URL", ""),
        "anonKey": env.get("SUPABASE_ANON_KEY", ""),
    }
    return f"window.SUPABASE_CONFIG = {json.dumps(config)};\n"


class PortalHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        path = self.path.split("?", 1)[0]
        if path == "/config.js":
            body = config_js().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        # Never serve the .env file itself.
        if Path(path).name.startswith(".env"):
            self.send_error(404)
            return
        super().do_GET()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--write-config", action="store_true",
                        help="write config.js next to index.html and exit")
    args = parser.parse_args()

    env = load_env()
    missing = [key for key in BROWSER_KEYS if not env.get(key)]
    if missing:
        print(f"Warning: {', '.join(missing)} not set in .env - "
              "the site will run in demo mode with sample data.")

    if args.write_config:
        (ROOT / "config.js").write_text(config_js(), encoding="utf-8")
        print("Wrote config.js")
        return 0

    handler = partial(PortalHandler, directory=str(ROOT))
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"St. Joseph's portal running at http://localhost:{args.port}  (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
