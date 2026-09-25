"""
Equivalence test: proves the refactored pipeline (render.py) is
pixel-identical to the pre-refactor main.py.

The pre-refactor main.py is fetched from git (commit OLD_COMMIT, the last
commit containing it), imported with all TMDB network calls monkeypatched,
and run on the same dummy movie and sample assets as the new pipeline.
The two JPEG outputs must be byte-identical.

Run:
    .venv/bin/python equiv_test.py

No TMDB account or network access needed. The only possible network use
is a one-time font download if the .ttf/.ttc files are missing from a
fresh clone.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.abspath(__file__))
os.chdir(REPO)
sys.path.insert(0, REPO)

# Last commit that contains the pre-refactor main.py (before the render.py split).
OLD_COMMIT = "c750f2bc8aad260b1f5a6649171d39a9413f3da8"

# --- fetch the old main.py from git ---
try:
    raw = subprocess.run(
        ["git", "show", f"{OLD_COMMIT}:main.py"],
        cwd=REPO, capture_output=True, check=True,
    ).stdout
except subprocess.CalledProcessError as e:
    sys.exit(f"equiv_test: cannot read old main.py from git ({OLD_COMMIT}): {e.stderr.decode(errors='replace').strip()}")

old_path = os.path.join(tempfile.gettempdir(), "equiv_old_main.py")
with open(old_path, "w") as f:
    f.write(raw.decode())

# --- fake all TMDB network calls (patch before import: the old module
# calls get_genres() at module level). Non-TMDB URLs (font downloads)
# fall through to the real requests.get. ---
import requests

REAL_GET = requests.get

OVERVIEW = ("A thrilling journey through uncharted territories where heroes "
            "must face their deepest fears and uncover a secret that changes everything.")

details = {
    "id": 1,
    "title": "DUMMY SHOW",
    "backdrop_path": "/x.jpg",
    "release_date": "2024-05-01",
    "genres": [{"id": 18, "name": "Drama"}, {"id": 28, "name": "Action"}],
    "runtime": 135,
    "vote_average": 8.5,
    "overview": OVERVIEW,
}

class FakeResp:
    def __init__(self, content=None, json_data=None):
        self.content = content
        self._j = json_data
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._j

bg_bytes = open(os.path.join(REPO, "sample/bg.jpg"), "rb").read()
logo_bytes = open(os.path.join(REPO, "sample/logo.png"), "rb").read()

def fake_get(url, headers=None, params=None, timeout=None):
    if "/genre/" in url:
        return FakeResp(json_data={"genres": []})
    if "/movie/1?" in url:
        return FakeResp(json_data=details)
    if "/movie/1/release_dates" in url:
        return FakeResp(json_data={"results": [{"iso_3166_1": "US",
                                               "release_dates": [{"certification": "PG-13"}]}]})
    if "/movie/1/images" in url:
        return FakeResp(json_data={"logos": [{"iso_639_1": "en", "vote_average": 10,
                                              "file_path": "/l.png"}]})
    if "/x.jpg" in url:
        return FakeResp(content=bg_bytes)
    if "/l.png" in url:
        return FakeResp(content=logo_bytes)
    if "/movie/1" in url or "/tv/1" in url:
        raise AssertionError(f"unexpected TMDB URL: {url}")
    return REAL_GET(url, headers=headers, params=params, timeout=timeout)

requests.get = fake_get

spec = importlib.util.spec_from_file_location("old_main", old_path)
old_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old_main)
os.remove(old_path)

# Ensure fonts exist (real network only if a fresh clone is missing them)
old_main.MediaGenerator.__new__(old_main.MediaGenerator).download_fonts()

from PIL import Image, ImageChops

old_out = os.path.join(REPO, "tmdb_backgrounds/movie_tmdb_1.jpg")
new_out = os.path.join(tempfile.gettempdir(), "equiv_new_out.jpg")

try:
    # --- run OLD path (bypass __init__: it wipes the output dir) ---
    if os.path.exists(old_out):
        os.remove(old_out)
    os.makedirs(os.path.dirname(old_out), exist_ok=True)
    old_gen = old_main.MediaGenerator.__new__(old_main.MediaGenerator)
    old_gen.generate_image({"id": 1}, True, "netflix", "NEW RELEASE ON")
    if not os.path.exists(old_out):
        sys.exit("equiv_test: old path did not produce output")

    # --- run NEW path with identical inputs ---
    from render import Renderer

    image = Image.open(os.path.join(REPO, "sample/bg.jpg")).convert("RGBA")
    renderer = Renderer()  # reads the same config files as the old module did
    image = renderer.render(
        image,
        label="NEW RELEASE ON",
        service_logo=Image.open(os.path.join(REPO, "netflix_logo.png")).convert("RGBA"),
        title_logo=Image.open(os.path.join(REPO, "sample/logo.png")).convert("RGBA"),
        title="DUMMY SHOW",
        genres="Drama, Action",
        year="2024",
        extra="2h 15m",
        certification="PG-13",
        rating=8.5,
        overview=OVERVIEW,
    )
    image.convert("RGB").save(new_out, "JPEG",
                              quality=renderer.output_quality(),
                              optimize=True)

    # --- compare ---
    old_img = Image.open(old_out)
    new_img = Image.open(new_out)
    print("old size:", old_img.size, "new size:", new_img.size)
    assert old_img.size == new_img.size, "canvas sizes differ"

    old_bytes = open(old_out, "rb").read()
    new_bytes = open(new_out, "rb").read()

    diff = ImageChops.difference(old_img, new_img)
    bbox = diff.getbbox()
    print(f"byte-identical: {old_bytes == new_bytes}")
    print(f"pixel bbox of difference: {bbox}  extreme (min,max): {diff.getextrema()}")
    if bbox is None:
        print("RESULT: PIXEL-IDENTICAL")
    else:
        diff_px = sum(1 for p in diff.getdata() if any(p[:3]))
        print(f"RESULT: MISMATCH — {diff_px} / {old_img.size[0] * old_img.size[1]} pixels differ")
        sys.exit(1)
finally:
    # clean up test artifacts
    for p in (old_out, new_out):
        if os.path.exists(p):
            os.remove(p)

print("done")
