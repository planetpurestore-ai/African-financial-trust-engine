import hmac
import os
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

TOKEN = os.environ.get("BACKUP_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trust Engine database export</title>
<style>
body{font-family:system-ui,sans-serif;background:#0b1220;color:#eef2f7;max-width:620px;margin:12vh auto;padding:24px}
main{background:#141e30;border:1px solid #344158;border-radius:16px;padding:28px}
h1{font-size:1.45rem}p{line-height:1.55;color:#cbd5e1}
input,button{box-sizing:border-box;width:100%;padding:14px;border-radius:9px;margin-top:12px;font:inherit}
input{background:#0b1220;border:1px solid #53627a;color:white}button{background:#d7b66d;color:#111827;border:0;font-weight:700}
small{color:#a9b4c6}
</style></head><body><main><h1>Trust Engine — database backup</h1>
<p>This utility creates a PostgreSQL custom-format export and downloads it to your device. It does not upgrade your plan.</p>
<form method="post" action="/backup">
<label for="token">Temporary backup access token</label>
<input id="token" name="token" type="password" autocomplete="off" required>
<button type="submit">Create and download backup</button>
</form><p><small>Keep the downloaded backup somewhere safe. This temporary utility is not the permanent storage location.</small></p></main></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Avoid logging request parameters or secrets.
        print("%s - %s" % (self.client_address[0], fmt % args))

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if self.path != "/":
            self.send_error(404)
            return
        body = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/backup":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length > 4096:
            self.send_error(413)
            return
        form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        supplied = form.get("token", [""])[0]
        if not TOKEN or not hmac.compare_digest(supplied, TOKEN):
            self.send_error(403, "Invalid token")
            return
        if not DATABASE_URL:
            self.send_error(503, "Database connection is not configured")
            return

        path = None
        try:
            with tempfile.NamedTemporaryFile(prefix="trust-engine-", suffix=".dump", delete=False) as f:
                path = f.name
            result = subprocess.run(
                ["pg_dump", "--dbname", DATABASE_URL, "--format=custom",
                 "--no-owner", "--no-privileges", "--file", path],
                capture_output=True, text=True, timeout=240, check=False,
            )
            if result.returncode != 0:
                print("pg_dump failed (details withheld from HTTP response)")
                self.send_error(502, "Database export failed; check service logs")
                return
            size = os.path.getsize(path)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="trust-engine-postgres-backup.dump"')
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with open(path, "rb") as backup:
                while True:
                    chunk = backup.read(1024 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except subprocess.TimeoutExpired:
            self.send_error(504, "Backup timed out")
        except Exception:
            self.send_error(500, "Backup could not be completed")
        finally:
            if path and os.path.exists(path):
                os.remove(path)

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("BACKUP_TOKEN must be set")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL must be set")
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))), Handler)
    print("Temporary backup utility ready")
    server.serve_forever()
