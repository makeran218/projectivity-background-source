"""
Shared image rendering for the generated backgrounds.

One module, one job: take a backdrop image + content data and draw the
standard layout on top of it. Used by:
  - main.py    -> batch generation from TMDB
  - web_gui.py -> live preview in the settings GUI

All layout values come from:
  - image_settings.json           (sizes, spacing, colors, output)
  - image_settings_elements.json  (absolute element positions, written by the GUI)
"""

import json
import math
import os

from PIL import Image, ImageDraw, ImageFont

# --- Font paths ---
TITLE_FONT_PATH = "Jersey25-Regular.ttf"
BODY_FONT_PATH = "Roboto-Light.ttf"
FALLBACK_FONT_PATH = "NotoSansCJK-Regular.ttc"

# --- Config files ---
SETTINGS_FILE = "image_settings.json"
ELEMENTS_FILE = "image_settings_elements.json"

# --- Service logos (filename per service key) ---
SERVICES = {
    "netflix": {"id": 8, "type": "provider", "logo": "netflix_logo.png"},
    "disney":  {"id": 2739, "type": "network", "logo": "disney-logo.png"},
    "amazon":  {"id": 1024, "type": "network", "logo": "amazon.png"},
    "apple":   {"id": 2552, "type": "network", "logo": "apple.png"},
    "peacock": {"id": 3353, "type": "network", "logo": "peacock.png"},
    "paramount": {"id": 4330, "type": "network", "logo": "paramount-logo.png"},
    "trending": {"id": None, "type": "trending", "logo": "tmdblogo.png"},
    "crunchyroll": {"id": 1112, "type": "network", "logo": "crunchyroll.png"},
    "anime_popular": {"id": None, "type": "anime", "logo": "tmdblogo.png"},
    "anime_new": {"id": None, "type": "anime", "logo": "tmdblogo.png"},
}

# --- Default settings (fallback when image_settings.json lacks a key) ---
DEFAULT_SETTINGS = {
    "canvas": {"width": 3840, "height": 2160},
    "gradient": {"start_x": 0, "end_x": 2100, "max_alpha": 205},
    "layout": {"left_margin": 260, "content_width": 1550, "start_y": 250},
    "label": {"font_size": 42, "spacing_after": 65},
    "service_logo": {"height": 75, "spacing_after": 55},
    "title_logo": {"max_width": 1350, "max_height": 420, "spacing_after": 55},
    "fallback_title": {"max_font_size": 155, "cjk_max_font_size": 125, "min_font_size": 80, "line_extra_spacing": 12, "bottom_padding": 35, "shadow_offset_x": 5, "shadow_offset_y": 5},
    "metadata": {"font_size": 48, "spacing_after": 85, "cert_padding_x": 15, "cert_padding_y": 20, "cert_radius": 3, "shadow_offset_x": 2, "shadow_offset_y": 4, "cert_y_offset": 14, "text_y_offset": 2, "dot_spacing": 20, "cert_dot_extra": 15, "dot_width_extra": 30},
    "rating": {"star_cx_offset": 25, "star_cy_offset": 32, "outer_radius": 28, "inner_radius": 12, "text_x_offset": 70, "spacing_after": 100, "font_size": 58, "star_y_offset": 5},
    "overview": {"font_size": 43, "max_lines": 3, "line_spacing": 62, "shadow_offset_x": 2, "shadow_offset_y": 2},
    "output": {"quality": 92, "use_vignette": True},
}


def _merge(base, override):
    """Deep merge: values in override replace values in base (in place)."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _merge(base[k], v)
        else:
            base[k] = v


def load_settings():
    """Load image_settings.json merged over the defaults."""
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as f:
                _merge(settings, json.load(f))
        except Exception as e:
            print(f"Failed to load {SETTINGS_FILE}: {e}. Using defaults.")
    return settings


def load_elements():
    """Load element positions written by the GUI."""
    if os.path.exists(ELEMENTS_FILE):
        try:
            with open(ELEMENTS_FILE) as f:
                return json.load(f)
        except Exception as e:
            print(f"Failed to load {ELEMENTS_FILE}: {e}. Using defaults.")
    return {}


class Renderer:
    """
    Draws the standard layout. Settings are resolved once per instance:

      Renderer()                        -> read from the config files
      Renderer(settings, elements)      -> use explicit values (GUI preview)
    """

    def __init__(self, settings=None, elements=None):
        self.settings = settings if settings is not None else load_settings()
        self.elements = elements if elements is not None else load_elements()

    # ------------------------------------------------------------------
    # Settings access
    # ------------------------------------------------------------------

    def _g(self, section, field, default=None):
        """Get a nested config value: _g('canvas', 'width')"""
        try:
            return self.settings[section][field]
        except (KeyError, TypeError):
            return default

    def _el(self, type_key, field, default=None):
        """Get a field from an element: _el('label', 'x') -> 260"""
        el = self.elements.get(type_key, {})
        return el.get(field, default)

    def _el_x(self, type_key):
        return self._el(type_key, "x", self._g("layout", "left_margin", 260))

    def _el_y(self, type_key):
        saved_y = self._el(type_key, "y", None)
        if saved_y is not None:
            return saved_y
        # Fallback: calculate sequential Y from config values
        return self._calculate_element_y(type_key)

    def _calculate_element_y(self, type_key):
        """Calculate element Y position from sequential config when elements file is missing."""
        LEFT = self._g("layout", "left_margin", 260)
        start_y = self._g("layout", "start_y", 250)

        # Order matters: label -> service_logo -> title_logo -> metadata -> rating -> overview
        order = ["label", "service_logo", "title_logo", "metadata", "rating", "overview"]
        current_y = start_y

        for key in order:
            if key == type_key:
                return current_y
            if key == "label":
                current_y += int(self._g("label", "font_size", 42) * 1.2) + self._g("label", "spacing_after", 65)
            elif key == "service_logo":
                current_y += self._g("service_logo", "height", 75) + self._g("service_logo", "spacing_after", 55)
            elif key == "title_logo":
                current_y += self._g("title_logo", "max_height", 420) + self._g("title_logo", "spacing_after", 55)
            elif key == "metadata":
                current_y += int(self._g("metadata", "font_size", 48) * 1.2) + self._g("metadata", "spacing_after", 85)
            elif key == "rating":
                current_y += int(self._g("rating", "font_size", 58) * 1.2) + self._g("rating", "spacing_after", 100)
            # overview is last, no spacing_after needed
        return current_y

    def _el_w(self, type_key):
        return self._el(type_key, "w", self._g("layout", "content_width", 1550))

    def _el_h(self, type_key):
        return self._el(type_key, "h", self._g("title_logo", "max_height", 420))

    def output_quality(self):
        """JPEG quality for the saved image (output.quality setting)."""
        return self._g("output", "quality", 92)

    # ------------------------------------------------------------------
    # Image helpers
    # ------------------------------------------------------------------

    def get_font(self, size, text="", is_title=False):
        if any(ord(c) > 0x4e00 for c in text):
            if os.path.exists(FALLBACK_FONT_PATH):
                return ImageFont.truetype(FALLBACK_FONT_PATH, size)
        font_path = TITLE_FONT_PATH if is_title else BODY_FONT_PATH
        return ImageFont.truetype(font_path, size)

    def prepare_background(self, image):
        """Center-crop to canvas ratio and resize to canvas size."""
        canvas_w = self._g("canvas", "width", 3840)
        canvas_h = self._g("canvas", "height", 2160)

        target_ratio = canvas_w / canvas_h
        img_ratio = image.width / image.height

        if img_ratio > target_ratio:
            new_w = int(target_ratio * image.height)
            image = image.crop(
                (
                    (image.width - new_w) // 2,
                    0,
                    (image.width + new_w) // 2,
                    image.height
                )
            )
        else:
            new_h = int(image.width / target_ratio)
            image = image.crop(
                (
                    0,
                    (image.height - new_h) // 2,
                    image.width,
                    (image.height + new_h) // 2
                )
            )

        return image.resize((canvas_w, canvas_h), Image.LANCZOS)

    def _apply_dark_gradient(self, image):
        """
        Dark left gradient. Strongest at left, fades toward center/right.
        Makes text readable without destroying the backdrop.
        Alpha depends only on x: build one row and scale it (fast, same output
        as the old per-pixel loop).
        """
        canvas_w = self._g("canvas", "width", 3840)
        canvas_h = self._g("canvas", "height", 2160)
        grad_end_x = self._g("gradient", "end_x", 2100)
        grad_max_alpha = self._g("gradient", "max_alpha", 205)

        row = Image.new("L", (canvas_w, 1))
        rp = row.load()
        for x in range(canvas_w):
            rp[x, 0] = int(grad_max_alpha * (1 - x / grad_end_x)) if x < grad_end_x else 0

        gradient = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 255))
        gradient.putalpha(row.resize((canvas_w, canvas_h), Image.NEAREST))
        image.alpha_composite(gradient)

    def _apply_vignette(self, image):
        if self._g("output", "use_vignette", True) and os.path.exists("vignette.png"):
            try:
                canvas_w = self._g("canvas", "width", 3840)
                canvas_h = self._g("canvas", "height", 2160)
                vig = Image.open("vignette.png").convert("RGBA")
                vig = vig.resize((canvas_w, canvas_h), Image.LANCZOS)
                image.alpha_composite(vig)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Main render
    # ------------------------------------------------------------------

    def render(self, image, *, label="", service_logo=None, title_logo=None,
               title="", genres="", year="N/A", extra="", certification="",
               rating=0.0, overview=""):
        """
        Draw the standard layout on an RGBA backdrop:
        crop/resize -> gradient -> vignette -> label, service logo,
        title logo (or fallback text title), metadata, rating, overview.

        Returns the finished image. NOTE: crop/resize always produces a new
        image object, so callers must use the return value, e.g.
            image = renderer.render(image, ...)
        """
        image = self.prepare_background(image)
        self._apply_dark_gradient(image)
        self._apply_vignette(image)

        year = year or "N/A"
        rating = float(rating or 0)

        # Local aliases so the drawing code below reads like the original
        _g = self._g
        _el_x, _el_y, _el_w, _el_h = self._el_x, self._el_y, self._el_w, self._el_h
        get_font = self.get_font

        CANVAS_W = _g("canvas", "width", 3840)
        CONTENT_WIDTH = _g("layout", "content_width", 1550)

        draw = ImageDraw.Draw(image)

        # --------------------------------------------------------
        # SERVICE LABEL
        # --------------------------------------------------------

        label_font_size = _g("label", "font_size", 42)
        f_label = get_font(
            label_font_size,
            label,
            is_title=False
        )

        label_text = label.upper()

        draw.text(
            (_el_x("label"), _el_y("label")),
            label_text,
            font=f_label,
            fill=(235, 235, 235, 230),
            stroke_width=1,
            stroke_fill=(0, 0, 0, 160)
        )

        # Service logo BELOW the label
        svc_logo_y = _el_y("service_logo")

        if service_logo is not None:

            try:
                brand_logo = service_logo

                LOGO_H = _g("service_logo", "height", 75)

                ratio = LOGO_H / brand_logo.height

                brand_logo = brand_logo.resize(
                    (
                        int(brand_logo.width * ratio),
                        LOGO_H
                    ),
                    Image.LANCZOS
                )

                image.alpha_composite(
                    brand_logo,
                    (_el_x("service_logo"), svc_logo_y)
                )

            except Exception:
                pass

        # --------------------------------------------------------
        # TITLE LOGO
        # --------------------------------------------------------

        used_logo = False

        if title_logo is not None:

            try:
                logo_img = title_logo

                MAX_LOGO_W = _el_w("title_logo")
                MAX_LOGO_H = _el_h("title_logo")

                ratio = min(
                    MAX_LOGO_W / logo_img.width,
                    MAX_LOGO_H / logo_img.height
                )

                logo_img = logo_img.resize(
                    (
                        int(logo_img.width * ratio),
                        int(logo_img.height * ratio)
                    ),
                    Image.LANCZOS
                )

                image.alpha_composite(
                    logo_img,
                    (
                        _el_x("title_logo"),
                        _el_y("title_logo")
                    )
                )

                used_logo = True

            except Exception:
                used_logo = False

        # --------------------------------------------------------
        # FALLBACK TITLE  (when no logo image)
        # --------------------------------------------------------

        if not used_logo:

            is_cjk = any(
                ord(c) > 0x4E00
                for c in title
            )

            display_title = (
                title
                if is_cjk
                else title.upper()
            )

            target_font_size = (
                _g("fallback_title", "cjk_max_font_size", 125)
                if is_cjk
                else _g("fallback_title", "max_font_size", 155)
            )

            title_width = _el_w("title_logo") or CONTENT_WIDTH

            while target_font_size >= _g("fallback_title", "min_font_size", 80):

                f_title = get_font(
                    target_font_size,
                    display_title,
                    is_title=True
                )

                words = display_title.split()
                lines = []
                line = ""

                for word in words:

                    test = (
                        f"{line} {word}".strip()
                    )

                    bbox = draw.textbbox(
                        (0, 0),
                        test,
                        font=f_title
                    )

                    if bbox[2] - bbox[0] <= title_width:
                        line = test
                    else:
                        if line:
                            lines.append(line)
                        line = word

                if line:
                    lines.append(line)

                if len(lines) <= 3:
                    break

                target_font_size -= 10

            # Track title Y position locally (multi-line titles)
            title_y = _el_y("title_logo")
            title_x = _el_x("title_logo")

            for line in lines:

                bbox = draw.textbbox(
                    (0, 0),
                    line,
                    font=f_title
                )

                # Shadow
                draw.text(
                    (
                        title_x + _g("fallback_title", "shadow_offset_x", 5),
                        title_y + _g("fallback_title", "shadow_offset_y", 5)
                    ),
                    line,
                    font=f_title,
                    fill=(0, 0, 0, 210)
                )

                draw.text(
                    (
                        title_x,
                        title_y
                    ),
                    line,
                    font=f_title,
                    fill=(255, 255, 255, 255)
                )

                title_y += (
                    bbox[3] - bbox[1]
                ) + _g("fallback_title", "line_extra_spacing", 12)

            title_y += _g("fallback_title", "bottom_padding", 35)

        # --------------------------------------------------------
        # METADATA
        # --------------------------------------------------------

        info_parts = []

        if genres:
            info_parts.append(genres)

        if year != "N/A":
            info_parts.append(year)

        if extra:
            info_parts.append(extra)

        if certification:
            info_parts.append(certification)

        meta_font_size = _g("metadata", "font_size", 48)
        dot_font = get_font(meta_font_size, "•", is_title=False)
        text_font = get_font(meta_font_size, "", is_title=False)

        def get_width(font, text):
            b = font.getbbox(text)
            return b[2] - b[0]

        def get_height(font, text):
            b = font.getbbox(text)
            return b[3] - b[1]

        parts_x = []
        cert_idx = None
        meta_x = _el_x("metadata")
        meta_width = _el_w("metadata") or CONTENT_WIDTH
        x = meta_x

        for i, part in enumerate(info_parts):
            is_cert = (part == certification)
            parts_x.append((part, x, False, is_cert))
            if is_cert:
                cert_idx = len(parts_x) - 1
            x += get_width(text_font, part)
            if i < len(info_parts) - 1:
                x += _g("metadata", "dot_spacing", 20)
                # Look ahead: is the NEXT part the certification?
                next_is_cert = (info_parts[i + 1] == certification)
                if next_is_cert:
                    # No dot before certification, just extra spacing
                    x += _g("metadata", "cert_dot_extra", 15)
                    x += _g("metadata", "dot_width_extra", 30)
                else:
                    parts_x.append(("•", x, True, False))
                    x += get_width(dot_font, "•") + _g("metadata", "dot_width_extra", 30)

        meta_y = _el_y("metadata")

        # Shadow (all parts, offset)
        for text, px, is_dot, is_cert in parts_x:
            color = (200, 30, 30, 255) if is_dot else (0, 0, 0, 180)
            draw.text(
                (px + _g("metadata", "shadow_offset_x", 2), meta_y + _g("metadata", "shadow_offset_y", 4)),
                text,
                font=dot_font if is_dot else text_font,
                fill=color
            )

        # Clamp metadata parts to element width
        if meta_width < CANVAS_W:
            parts_x = [(t, p, d, c) for t, p, d, c in parts_x if p + get_width(dot_font if d else text_font, t) <= meta_x + meta_width]

        # Certification badge — rounded box with white border
        if cert_idx is not None:
            _, cx, _, _ = parts_x[cert_idx]
            cert_text = info_parts[-1]
            tw = get_width(text_font, cert_text)
            th = get_height(text_font, cert_text)
            pad_x = _g("metadata", "cert_padding_x", 15)
            pad_y = _g("metadata", "cert_padding_y", 20)
            radius = _g("metadata", "cert_radius", 3)

            bx1, by1 = cx - pad_x, meta_y + _g("metadata", "cert_y_offset", 14) - pad_y
            bx2, by2 = cx + tw + pad_x, meta_y + _g("metadata", "cert_y_offset", 14) + th + pad_y

            # Draw border 3 times to simulate stroke_width (compatibility)
            for offset in (-1, 0, 1):
                draw.rounded_rectangle(
                    (bx1 + offset, by1 + offset, bx2 + offset, by2 + offset),
                    radius=radius,
                    outline=(255, 255, 255, 255)
                )

        # Main text
        for text, px, is_dot, is_cert in parts_x:
            if is_dot:
                color = (200, 30, 30, 255)
            elif is_cert:
                color = (255, 255, 255, 255)
            else:
                color = (225, 225, 225, 255)
            draw.text(
                (px, meta_y + _g("metadata", "text_y_offset", 2)),
                text,
                font=dot_font if is_dot else text_font,
                fill=color
            )

        # --------------------------------------------------------
        # RATING
        # --------------------------------------------------------

        if rating > 0:

            rating_y = _el_y("rating") + _g("rating", "star_y_offset", 5)

            # ------------------------------------------------------------
            # Draw 5-point star
            # ------------------------------------------------------------

            cx = _el_x("rating") + _g("rating", "star_cx_offset", 25)
            cy = rating_y + _g("rating", "star_cy_offset", 32)

            outer_radius = _g("rating", "outer_radius", 28)
            inner_radius = _g("rating", "inner_radius", 12)

            points = []

            for i in range(10):
                angle = -math.pi / 2 + (i * math.pi / 5)

                radius = (
                    outer_radius
                    if i % 2 == 0
                    else inner_radius
                )

                x = cx + math.cos(angle) * radius
                y = cy + math.sin(angle) * radius

                points.append((x, y))

            draw.polygon(
                points,
                fill=(255, 210, 80, 255)
            )

            # ------------------------------------------------------------
            # Rating number
            # ------------------------------------------------------------

            rating_text = str(rating)

            f_rating = get_font(
                _g("rating", "font_size", 58),
                rating_text,
                is_title=False
            )

            draw.text(
                (
                    _el_x("rating") + _g("rating", "text_x_offset", 70),
                    _el_y("rating")
                ),
                rating_text,
                font=f_rating,
                fill=(255, 255, 255, 255),
                stroke_width=1,
                stroke_fill=(0, 0, 0, 160)
            )

        # --------------------------------------------------------
        # OVERVIEW
        # --------------------------------------------------------

        if overview:

            f_ov = get_font(
                _g("overview", "font_size", 43),
                overview,
                is_title=False
            )

            overview_x = _el_x("overview")
            overview_width = _el_w("overview") or CONTENT_WIDTH

            words = overview.split()
            lines = []
            line = ""

            for word in words:

                test = (
                    f"{line} {word}".strip()
                )

                bbox = draw.textbbox(
                    (0, 0),
                    test,
                    font=f_ov
                )

                if bbox[2] - bbox[0] <= overview_width:
                    line = test
                else:

                    if line:
                        lines.append(line)

                    line = word

            if line:
                lines.append(line)

            lines = lines[:_g("overview", "max_lines", 3)]

            overview_y = _el_y("overview")

            for line in lines:

                draw.text(
                    (
                        overview_x + _g("overview", "shadow_offset_x", 2),
                        overview_y + _g("overview", "shadow_offset_y", 2)
                    ),
                    line,
                    font=f_ov,
                    fill=(0, 0, 0, 180)
                )

                draw.text(
                    (
                        overview_x,
                        overview_y
                    ),
                    line,
                    font=f_ov,
                    fill=(245, 245, 245, 245)
                )

                overview_y += _g("overview", "line_spacing", 62)

        return image
