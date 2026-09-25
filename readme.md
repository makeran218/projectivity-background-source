# Background & simple backend for projectivity launcher

Simple script & backend to create & load background in projectivity launcher..

## Settings GUI

    python web_gui.py
    → open http://localhost:8765

The preview is rendered by the same code main.py uses (`render.py`) with
dummy sample content, so the preview is exactly the output image.

Save writes the files main.py reads:
- `image_settings.json` — sizing / color / output settings
- `image_settings_elements.json` — absolute element positions (drag & drop in the GUI)
- `sample/sample_data.json` — dummy content used for the preview

The Sample content group has a "Title display" selector to preview both
title variants: the logo image, or the text fallback (what main.py draws
when TMDB has no clean logo for a show).

`sample/` is local-only (gitignored) — it feeds the GUI preview, not
`main.py`. The GitHub Pages site publishes only what `main.py` produces
with the committed settings: `api.json` + `tmdb_backgrounds/`.
