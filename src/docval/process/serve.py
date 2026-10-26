"""`make review RUN=<name>`: the review page of a processed tour, served on this computer.

Opened this way (instead of by double click) the page can
- read a box the person draws live with the same OCR as make process (Lieferschein number,
  page i/n, CMR i/n, tour number, TA) - the number lands in its field, the person checks it
  and confirms with Enter instead of typing it,
- save entscheidung.json straight into the tour's folder (no file dialog, nothing to move).

Only on 127.0.0.1 (nothing reachable from other computers). Without the server the page
works as before, just without live OCR. Stop with Ctrl+C.

    GET  /                   -> the review page (language: first of ui_languages)
    GET  /<file>             -> files of the run folder (pruefung*.html, seiten/...)
    GET  /api/ping           -> {"ok": true, "name": ...}
    POST /api/ocr            {"n": page, "box": [x1, y1, x2, y2] (0..1), "cls": class} -> {"text", "value"}
    POST /api/save           entscheidung.json content -> written into the run folder
"""

from __future__ import annotations

import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from PIL import Image

from ..config import artifacts
from ..zones.synthetic import to_rgb

MAX_BODY = 20 * 1024 * 1024


def make_server(run_dir: Path, read, port: int = 0, start_page: str = "pruefung.html", log=print):
    """read(image_path, box, cls) -> {"text", "value"}. port 0 = any free port."""
    run_dir = Path(run_dir).resolve()
    pages = {p["n"]: p for p in json.loads((run_dir / "ergebnis.json").read_text(encoding="utf-8"))["pages"]}
    name = run_dir.name
    lock = threading.Lock()   # one OCR at a time (onnxruntime session, memory on 8 GB machines)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):   # quiet: only errors and OCR reads are logged
            pass

        def send_json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_BODY:
                raise ValueError("leere oder zu große Anfrage")
            return json.loads(self.rfile.read(n).decode("utf-8"))

        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            if path == "/api/ping":
                return self.send_json({"ok": True, "name": name})
            if path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if path == "/":
                self.send_response(302)
                self.send_header("Location", "/" + start_page)
                self.end_headers()
                return
            f = (run_dir / path.lstrip("/")).resolve()
            if run_dir not in f.parents or not f.is_file():   # nothing outside the run folder
                return self.send_error(404)
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            # page images never change: let the browser cache them (many crops of the same page);
            # the review page itself always fresh
            self.send_header("Cache-Control", "max-age=86400" if f.suffix.lower() == ".png" else "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                req = self.body()
                if path == "/api/ocr":
                    p = pages[int(req["n"])]
                    box = [min(1.0, max(0.0, float(v))) for v in req["box"]]
                    if not (box[2] > box[0] and box[3] > box[1]):
                        raise ValueError("leere Box")
                    with lock:
                        res = read(run_dir / p["image"], box, str(req.get("cls") or ""))
                    log(f"[review] S. {p['n']} {req.get('cls')}: „{res['text']}“ -> {res['value'] or '–'}")
                    return self.send_json({"ok": True, **res})
                if path == "/api/save":
                    if req.get("format") != "docval-entscheidung":
                        raise ValueError("keine Entscheidungsdatei")
                    out = run_dir / "entscheidung.json"
                    out.write_text(json.dumps(req, ensure_ascii=False, indent=1), encoding="utf-8")
                    log(f"[review] Entscheidung gespeichert: {out}")
                    return self.send_json({"ok": True, "path": str(out)})
                return self.send_error(404)
            except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
                return self.send_json({"ok": False, "error": str(e)}, 400)

    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):   # browser closed a connection: not an error
            import sys
            if not isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
                super().handle_error(request, client_address)

    return Server(("127.0.0.1", port), Handler)


def run_review(cfg, run: str, port: int | None, log, open_browser: bool = True) -> int:
    from .run import BoxReader

    base = artifacts(cfg, "process", run)
    if not (base / "ergebnis.json").is_file():
        log(f"FEHLER: {base / 'ergebnis.json'} fehlt - zuerst `make process`")
        return 2
    langs = cfg.get("ui_languages") or ["de"]
    start = "pruefung.html" if langs[0] == "de" else f"pruefung_{langs[0]}.html"
    if not (base / start).is_file():
        start = "pruefung.html"
    log("[review] OCR-Modell wird geladen …")
    reader = BoxReader(cfg)

    def read(image_path: Path, box, cls):
        with Image.open(image_path) as im:
            return reader.read(to_rgb(im), box, cls)

    want = port if port is not None else int((cfg.get("process") or {}).get("review_port", 8765))
    try:
        srv = make_server(base, read, want, start, log)
    except OSError:   # port taken (e.g. a second tour open): any free port
        srv = make_server(base, read, 0, start, log)
    url = f"http://127.0.0.1:{srv.server_address[1]}/{start}"
    log(f"[review] Prüfseite: {url}  (Live-OCR beim Box-Zeichnen, Speichern direkt nach {base / 'entscheidung.json'})")
    log("[review] Beenden mit Strg+C, danach make finalize RUN=" + run)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:   # no browser on this machine (server, container): open the URL by hand
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0
