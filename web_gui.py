"""
Web GUI for editing the generated background image.

The preview is rendered by the same code main.py uses (render.py) with
dummy "sample" content, so what you see is exactly what main.py outputs.
No JS re-implementation of the layout — the GUI is a pure editor.

Saving writes the files main.py reads:
  - image_settings.json            (sizing / color / output settings)
  - image_settings_elements.json   (absolute element positions)
  - sample/sample_data.json        (dummy content used for the preview)

Usage:
  python web_gui.py
  → open http://localhost:8765
"""

import base64
import io
import json
import os
import threading

from PIL import Image
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

from render import (
    Renderer,
    SERVICES,
    load_settings,
    load_elements,
    SETTINGS_FILE,
    ELEMENTS_FILE,
)

PORT = 8765
SAMPLE_DIR = "sample"
SAMPLE_DATA_FILE = os.path.join(SAMPLE_DIR, "sample_data.json")

# Element fields main.py actually reads (image_settings_elements.json).
# label/rating: position only. w/h: max size (title logo) / max width (text).
ELEMENT_KEYS = {
    "label": ["x", "y"],
    "service_logo": ["x", "y"],
    "title_logo": ["x", "y", "w", "h"],
    "metadata": ["x", "y", "w"],
    "rating": ["x", "y"],
    "overview": ["x", "y", "w"],
}

DEFAULT_SAMPLE = {
    "bg": "bg.jpg",
    "title_logo": "logo.png",
    "title_source": "logo",  # "logo" (image) or "text" (fallback text title)
    "service": "netflix_logo.png",
    "label": "NETFLIX",
    "title": "DUMMY SHOW",
    "genres": "Action, Drama",
    "year": "2024",
    "extra": "2h 15m",
    "certification": "PG-13",
    "rating": 8.5,
    "overview": "A thrilling journey through uncharted territories where heroes must face their deepest fears and uncover a secret that changes everything.",
}

_write_lock = threading.Lock()


def load_sample():
    """Dummy content for the preview (sample/sample_data.json + defaults)."""
    sample = dict(DEFAULT_SAMPLE)
    if os.path.exists(SAMPLE_DATA_FILE):
        try:
            with open(SAMPLE_DATA_FILE) as f:
                sample.update(json.load(f))
        except Exception as e:
            print(f"Failed to load {SAMPLE_DATA_FILE}: {e}. Using defaults.")
    return sample


def effective_elements(settings, elements):
    """
    Positions the renderer will actually use: values from the elements file,
    with the sequential-layout fallback for anything missing. The GUI edits
    these, so saving makes every position explicit.
    """
    r = Renderer(settings, elements)
    getters = {"x": r._el_x, "y": r._el_y, "w": r._el_w, "h": r._el_h}
    out = {}
    for key, fields in ELEMENT_KEYS.items():
        out[key] = {f: getters[f](key) for f in fields}
    return out


def render_preview(settings, elements, sample):
    """Render the test image with the real render code. Returns JPEG bytes."""
    renderer = Renderer(settings, elements)

    # Background
    bg_path = os.path.join(SAMPLE_DIR, sample.get("bg") or DEFAULT_SAMPLE["bg"])
    if not os.path.exists(bg_path):
        raise FileNotFoundError(f"sample background not found: {bg_path}")
    image = Image.open(bg_path).convert("RGBA")

    # Service logo (repo root)
    service_logo = None
    svc_logo_path = sample.get("service") or DEFAULT_SAMPLE["service"]
    if os.path.exists(svc_logo_path):
        try:
            service_logo = Image.open(svc_logo_path).convert("RGBA")
        except Exception:
            pass

    # Title logo (sample dir) — only when "Title display" is set to logo;
    # "text" forces the fallback text title (shows without a clean logo)
    title_logo = None
    if sample.get("title_source", "logo") == "logo":
        title_logo_path = os.path.join(SAMPLE_DIR, sample.get("title_logo") or DEFAULT_SAMPLE["title_logo"])
        if os.path.exists(title_logo_path):
            try:
                title_logo = Image.open(title_logo_path).convert("RGBA")
            except Exception:
                pass

    image = renderer.render(
        image,
        label=sample.get("label", ""),
        service_logo=service_logo,
        title_logo=title_logo,
        title=sample.get("title", ""),
        genres=sample.get("genres", ""),
        year=sample.get("year", ""),
        extra=sample.get("extra", ""),
        certification=sample.get("certification", ""),
        rating=sample.get("rating", 0),
        overview=sample.get("overview", ""),
    )

    buf = io.BytesIO()
    image.convert("RGB").save(
        buf, "JPEG",
        quality=renderer.output_quality(),
        optimize=True,
    )
    return buf.getvalue()


def save_files(settings, elements, sample):
    """Persist the three files main.py / the GUI read."""
    with _write_lock:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
        with open(ELEMENTS_FILE, "w") as f:
            json.dump(elements, f, indent=2)
        os.makedirs(SAMPLE_DIR, exist_ok=True)
        with open(SAMPLE_DATA_FILE, "w") as f:
            json.dump(sample, f, indent=2)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/config":
            settings = load_settings()
            elements = load_elements()
            self._json({
                "settings": settings,
                "elements": effective_elements(settings, elements),
                "sample": load_sample(),
                "service_logos": sorted({s["logo"] for s in SERVICES.values()}),
            })
            return

        self._serve_static()

    def _serve_static(self):
        if urlparse(self.path).path == "/":
            self.path = "/index.html"
        return super().do_GET()

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------

    def do_POST(self):
        path = urlparse(self.path).path

        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
        except Exception as e:
            self._json({"error": f"bad request: {e}"}, 400)
            return

        if path == "/api/save":
            try:
                save_files(
                    data.get("settings") or load_settings(),
                    data.get("elements") or {},
                    data.get("sample") or load_sample(),
                )
                self._json({"ok": True})
            except Exception as e:
                self._json({"error": str(e)}, 500)

        elif path == "/api/render":
            # Explicit payload from the GUI, or the files on disk if absent
            try:
                out = render_preview(
                    data.get("settings") or load_settings(),
                    data.get("elements") or load_elements(),
                    data.get("sample") or load_sample(),
                )
                self._bytes(out, "image/jpeg")
            except Exception as e:
                self._json({"error": str(e)}, 500)

        elif path == "/api/upload":
            # data: {"target": "bg" | "title_logo", "filename": ..., "data": "<base64>"}
            target = data.get("target")
            filename = os.path.basename(data.get("filename") or "")
            if target == "bg" and filename:
                dest = os.path.join(SAMPLE_DIR, "bg.jpg")
            elif target == "title_logo" and filename:
                dest = os.path.join(SAMPLE_DIR, filename)
            else:
                self._json({"error": "bad target (use 'bg' or 'title_logo')"}, 400)
                return
            try:
                os.makedirs(SAMPLE_DIR, exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(base64.b64decode(data.get("data", "")))
                self._json({"ok": True, "filename": os.path.basename(dest)})
            except Exception as e:
                self._json({"error": str(e)}, 500)

        else:
            self._json({"error": "not found"}, 404)

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, data, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def main():
    print(f"Web GUI: http://localhost:{PORT}")
    print("Preview is rendered by render.py (same code as main.py).")
    print(f"Save writes: {SETTINGS_FILE}, {ELEMENTS_FILE}, {SAMPLE_DATA_FILE}")
    print("Press Ctrl+C to stop")
    try:
        server = ThreadedHTTPServer(("0.0.0.0", PORT), Handler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
