"""Read-only loopback review server. No remote file browsing or mutation API."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ALLOWED = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.mjs": "app.mjs",
    "/style.css": "style.css",
    "/geometry.mjs": "geometry.mjs",
    "/plan.json": "plan.json",
    "/mark.svg": "mark.svg",
}


def serve(folder, port=0):
    root = Path(folder).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Review directory is missing")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            host = self.headers.get("Host")
            origin = self.headers.get("Origin")
            allowed = {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }
            if host not in allowed or (
                origin and origin not in {"http://" + h for h in allowed}
            ):
                return self.send_error(403, "Use the printed loopback address")
            path = urlsplit(self.path).path
            if path not in ALLOWED:
                return self.send_error(404)
            target = root / ALLOWED[path]
            if (
                not target.is_file()
                or target.is_symlink()
                or target.resolve().parent != root
            ):
                return self.send_error(404)
            if target.stat().st_size > 64 * 1024 * 1024:
                return self.send_error(413)
            blob = target.read_bytes()
            ctype = {
                "mjs": "text/javascript",
                "json": "application/json",
                "css": "text/css",
                "html": "text/html",
                "svg": "image/svg+xml",
            }[target.suffix[1:]]
            self.send_response(200)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(blob)

        def do_POST(self):
            return self.send_error(405, "Review is read-only")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    print(f"Polyweft review · http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
