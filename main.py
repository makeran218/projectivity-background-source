import requests
from PIL import Image, ImageDraw, ImageFont, ImageStat, ImageFilter
from io import BytesIO
import os
import textwrap
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import shutil
import random

load_dotenv(verbose=True)

# --- Configuration ---
TMDB_BEARER_TOKEN = os.getenv('TMDB_BEARER_TOKEN')
TMDB_BASE_URL = os.getenv('TMDB_BASE_URL', 'https://api.themoviedb.org/3')

HEADERS = {"accept": "application/json", "Authorization": f"Bearer {TMDB_BEARER_TOKEN}"}

# Font Paths
TITLE_FONT_PATH = 'Jersey25-Regular.ttf'
BODY_FONT_PATH = 'Roboto-Light.ttf'
FALLBACK_FONT_PATH = 'NotoSansCJK-Regular.ttc'

BACKGROUND_DIR = "tmdb_backgrounds"
BASE_URL_FOR_API = "https://makeran218.github.io/projectivity-background-source"

# 4K Canvas
CANVAS_W = 3840
CANVAS_H = 2160

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
    "anime_new": {"id": None, "type": "anime", "logo": "tmdblogo.png"}
}

def get_genres(media_type):
    url = f'{TMDB_BASE_URL}/genre/{media_type}/list?language=en-US'
    try:
        data = requests.get(url, headers=HEADERS).json()
        return {g['id']: g['name'] for g in data.get('genres', [])}
    except: return {}

MOVIE_GENRES = get_genres("movie")
TV_GENRES = get_genres("tv")

class MediaGenerator:
    def __init__(self):
        if os.path.exists(BACKGROUND_DIR):
            print(f"Cleaning up old backgrounds in {BACKGROUND_DIR}...")
            shutil.rmtree(BACKGROUND_DIR)
        os.makedirs(BACKGROUND_DIR, exist_ok=True)
        self.download_fonts()

    def download_fonts(self):
        if not os.path.exists(TITLE_FONT_PATH):
            print("Downloading Title font...")
            url = 'https://github.com/google/fonts/raw/refs/heads/main/ofl/jersey25/Jersey25-Regular.ttf'
            r = requests.get(url)
            with open(TITLE_FONT_PATH, 'wb') as f: f.write(r.content)

        if not os.path.exists(BODY_FONT_PATH):
            print("Downloading Roboto Light...")
            url = 'https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Light.ttf'
            r = requests.get(url)
            with open(BODY_FONT_PATH, 'wb') as f: f.write(r.content)

    def get_font(self, size, text="", is_title=False):
        if any(ord(c) > 0x4e00 for c in text):
            if os.path.exists(FALLBACK_FONT_PATH):
                return ImageFont.truetype(FALLBACK_FONT_PATH, size)
        font_path = TITLE_FONT_PATH if is_title else BODY_FONT_PATH
        return ImageFont.truetype(font_path, size)

    def get_details(self, media_type, media_id):
        url = f'{TMDB_BASE_URL}/{media_type}/{media_id}?language=en-US'
        return requests.get(url, headers=HEADERS).json()

    def get_media_logo(self, media_type, media_id):
        url = f"{TMDB_BASE_URL}/{media_type}/{media_id}/images?include_image_language=en,null"
        try:
            response = requests.get(url, headers=HEADERS).json()
            all_logos = response.get("logos", [])
            targeted = [l for l in all_logos if l.get("iso_639_1") == "en"] or [l for l in all_logos if l.get("iso_639_1") is None]
            if not targeted: return None
            top = sorted(targeted, key=lambda x: x.get("vote_average", 0), reverse=True)[0]
            return top['file_path']
        except: return None

    def get_certification(self, media_type, media_id):
        if media_type == "movie":
            url = f"{TMDB_BASE_URL}/movie/{media_id}/release_dates"
        else:
            url = f"{TMDB_BASE_URL}/tv/{media_id}/content_ratings"
        try:
            data = requests.get(url, headers=HEADERS).json()
            results = data.get("results", [])

            # Both movie release_dates and tv content_ratings return a list
            for entry in results:
                if entry.get("iso_3166_1") == "US":
                    if media_type == "movie":
                        for rd in entry.get("release_dates", []):
                            cert = rd.get("certification", "")
                            if cert:
                                return cert
                    else:
                        cert = entry.get("rating", "")
                        if cert:
                            return cert

            return ""
        except:
            return ""

    def generate_image(self, item, is_movie, service_key, custom_label):
        m_type, m_id = ("movie" if is_movie else "tv"), item["id"]
        details = self.get_details(m_type, m_id)

        title = details.get("title") if is_movie else details.get("name")
        svc = SERVICES.get(service_key, SERVICES["trending"])

        # ============================================================
        # METADATA
        # ============================================================

        date_raw = (
            details.get("release_date")
            if is_movie
            else details.get("first_air_date")
        )
        year = date_raw[:4] if date_raw else "N/A"

        genres = ", ".join(
            [g["name"] for g in details.get("genres", [])][:2]
        )

        if is_movie:
            runtime = details.get("runtime") or 0
            extra = f"{runtime // 60}h {runtime % 60}m"
        else:
            seasons = details.get("number_of_seasons") or 1
            extra = f"{seasons} Season" + ("s" if seasons != 1 else "")

        # Certification (US rating like PG-13, TV-14, etc.)
        certification = self.get_certification(m_type, m_id)

        rating = details.get("vote_average") or 0
        rating = round(rating, 1)

        overview = (details.get("overview") or "").strip()

        # ============================================================
        # DOWNLOAD BACKDROP
        # ============================================================

        backdrop_path = details.get("backdrop_path")
        if not backdrop_path:
            print(f"No backdrop for {title}")
            return

        bg_res = requests.get(
            f"https://image.tmdb.org/t/p/original{backdrop_path}",
            timeout=30
        )
        bg_res.raise_for_status()

        image = Image.open(
            BytesIO(bg_res.content)
        ).convert("RGBA")

        # ============================================================
        # CROP TO 3840x2160
        # ============================================================

        target_ratio = CANVAS_W / CANVAS_H
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

        image = image.resize(
            (CANVAS_W, CANVAS_H),
            Image.LANCZOS
        )

        # ============================================================
        # DARK LEFT GRADIENT
        #
        # This is the most important visual change.
        # It makes text readable without destroying the backdrop.
        # ============================================================

        gradient = Image.new(
            "RGBA",
            (CANVAS_W, CANVAS_H),
            (0, 0, 0, 0)
        )

        gradient_pixels = gradient.load()

        for x in range(CANVAS_W):
            # Strongest at left, fades toward center/right.
            if x < 2100:
                strength = int(205 * (1 - x / 2100))
            else:
                strength = 0

            for y in range(CANVAS_H):
                gradient_pixels[x, y] = (
                    0,
                    0,
                    0,
                    strength
                )

        image.alpha_composite(gradient)

        # ============================================================
        # OPTIONAL EXISTING VIGNETTE
        # ============================================================

        if os.path.exists("vignette.png"):
            try:
                vig = Image.open("vignette.png").convert("RGBA")
                vig = vig.resize(
                    (CANVAS_W, CANVAS_H),
                    Image.LANCZOS
                )
                image.alpha_composite(vig)
            except Exception:
                pass

        draw = ImageDraw.Draw(image)

        # ============================================================
        # LAYOUT
        # ============================================================

        LEFT = 260
        CONTENT_WIDTH = 1550

        current_y = 250



        # ============================================================
        # SERVICE LABEL
        # LABEL FIRST, SERVICE LOGO BELOW
        # ============================================================

        f_label = self.get_font(
            42,
            custom_label,
            is_title=False
        )

        label_text = custom_label.upper()

        draw.text(
            (LEFT, current_y),
            label_text,
            font=f_label,
            fill=(235, 235, 235, 230),
            stroke_width=1,
            stroke_fill=(0, 0, 0, 160)
        )

        current_y += 65

        # Service logo BELOW the label
        if os.path.exists(svc["logo"]):

            try:
                brand_logo = Image.open(
                    svc["logo"]
                ).convert("RGBA")

                LOGO_H = 75

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
                    (LEFT, current_y)
                )

                current_y += LOGO_H + 55

            except Exception:
                pass

        # ============================================================
        # TITLE LOGO
        # ============================================================

        logo_path = self.get_media_logo(
            m_type,
            m_id
        )

        used_logo = False

        if logo_path:

            try:
                l_res = requests.get(
                    f"https://image.tmdb.org/t/p/original{logo_path}",
                    timeout=30
                )
                l_res.raise_for_status()

                logo_img = Image.open(
                    BytesIO(l_res.content)
                ).convert("RGBA")

                # Much smaller than your current 80% canvas width.
                MAX_LOGO_W = 1350
                MAX_LOGO_H = 420

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
                        LEFT,
                        current_y
                    )
                )

                current_y += logo_img.height + 55
                used_logo = True

            except Exception:
                used_logo = False

        # ============================================================
        # FALLBACK TITLE
        # ============================================================

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

            # More restrained than the old 350px title.
            target_font_size = (
                155 if not is_cjk else 125
            )

            while target_font_size >= 80:

                f_title = self.get_font(
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

                    if bbox[2] - bbox[0] <= CONTENT_WIDTH:
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

            for line in lines:

                bbox = draw.textbbox(
                    (0, 0),
                    line,
                    font=f_title
                )

                w = bbox[2] - bbox[0]

                # Shadow
                draw.text(
                    (
                        LEFT + 5,
                        current_y + 5
                    ),
                    line,
                    font=f_title,
                    fill=(0, 0, 0, 210)
                )

                draw.text(
                    (
                        LEFT,
                        current_y
                    ),
                    line,
                    font=f_title,
                    fill=(255, 255, 255, 255)
                )

                current_y += (
                    bbox[3] - bbox[1]
                ) + 12

            current_y += 35

        # ============================================================
        # METADATA
        # ============================================================

        info_parts = []

        if genres:
            info_parts.append(genres)

        if year != "N/A":
            info_parts.append(year)

        if extra:
            info_parts.append(extra)

        if certification:
            info_parts.append(certification)

        # Metadata — draw segments with red dots between them
        dot_font = self.get_font(48, "•", is_title=False)
        text_font = self.get_font(48, "", is_title=False)

        def get_width(font, text):
            b = font.getbbox(text)
            return b[2] - b[0]

        def get_height(font, text):
            b = font.getbbox(text)
            return b[3] - b[1]

        parts_x = []  # (text, x, is_dot)
        cert_idx = None  # index of certification in parts_x
        x = LEFT

        for i, part in enumerate(info_parts):
            is_cert = (part == certification)
            parts_x.append((part, x, False, is_cert))
            if is_cert:
                cert_idx = len(parts_x) - 1
            x += get_width(text_font, part)
            if i < len(info_parts) - 1:
                x += 20
                parts_x.append(("•", x, True, False))
                if is_cert:
                    x += 15
                x += get_width(dot_font, "•") + 30

        # Shadow (all parts, offset)
        for text, px, is_dot, is_cert in parts_x:
            color = (200, 30, 30, 255) if is_dot else (0, 0, 0, 180)
            draw.text(
                (px + 2, current_y + 4),
                text,
                font=dot_font if is_dot else text_font,
                fill=color
            )

        # Certification badge — rounded box with white border
        if cert_idx is not None:
            _, cx, _, _ = parts_x[cert_idx]
            cert_text = info_parts[-1]
            tw = get_width(text_font, cert_text)
            th = get_height(text_font, cert_text)
            pad_x = 15
            pad_y = 20
            radius = 3

            bx1, by1 = cx - pad_x, current_y + 14 - pad_y
            bx2, by2 = cx + tw + pad_x, current_y + 14 + th + pad_y

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
                (px, current_y + 2),
                text,
                font=dot_font if is_dot else text_font,
                fill=color
            )

        current_y += 85

        # ============================================================
        # RATING (only if valid / non-zero)
        # ============================================================

        if rating and float(rating) > 0:

            rating_y = current_y + 5

            # ------------------------------------------------------------
            # Draw 5-point star
            # ------------------------------------------------------------

            cx = LEFT + 25
            cy = rating_y + 32

            outer_radius = 28
            inner_radius = 12

            points = []

            import math

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

            f_rating = self.get_font(
                58,
                rating_text,
                is_title=False
            )

            draw.text(
                (
                    LEFT + 70,
                    current_y
                ),
                rating_text,
                font=f_rating,
                fill=(255, 255, 255, 255),
                stroke_width=1,
                stroke_fill=(0, 0, 0, 160)
            )

            current_y += 100

        # ============================================================
        # OVERVIEW / DESCRIPTION
        # ============================================================

        if overview:

            f_ov = self.get_font(
                43,
                overview,
                is_title=False
            )

            # Wrap based on pixel width rather than
            # an arbitrary character count.
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

                if bbox[2] - bbox[0] <= CONTENT_WIDTH:
                    line = test
                else:

                    if line:
                        lines.append(line)

                    line = word

            if line:
                lines.append(line)

            # Projectivy background:
            # keep description short.
            lines = lines[:3]

            for line in lines:

                draw.text(
                    (
                        LEFT + 2,
                        current_y + 2
                    ),
                    line,
                    font=f_ov,
                    fill=(0, 0, 0, 180)
                )

                draw.text(
                    (
                        LEFT,
                        current_y
                    ),
                    line,
                    font=f_ov,
                    fill=(245, 245, 245, 245)
                )

                current_y += 62

        # ============================================================
        # SAVE
        # ============================================================

        output_path = os.path.join(
            BACKGROUND_DIR,
            f"{m_type}_tmdb_{m_id}.jpg"
        )

        image.convert("RGB").save(
            output_path,
            "JPEG",
            quality=92,
            optimize=True
        )

        print(
            f"Generated: {title} -> {output_path}"
        )
    def generate_api_json(self):
        api_data = []
        filenames = sorted(os.listdir(BACKGROUND_DIR))
        for filename in filenames:
            if filename.endswith(".jpg"):
                name = os.path.splitext(filename)[0]
                last_u = name.rfind('_')
                api_data.append({
                    "actionUrl": f"{name[:last_u]}:{name[last_u+1:]}",
                    "imageUrl": f"{BASE_URL_FOR_API}/{BACKGROUND_DIR}/{filename}",
                    "title": name
                })
        with open("api.json", "w") as f:
            json.dump(api_data, f, indent=4)

    def run(self, service_key, is_movie, custom_label, limit=5, is_new_release=False):
        svc = SERVICES.get(service_key, SERVICES["trending"])
        m_type = "movie" if is_movie else "tv"

        # Base Discover URL
        base_discover_url = f"{TMDB_BASE_URL}/discover/{m_type}?include_adult=false&language=en-US&sort_by=popularity.desc"

        if service_key == "crunchyroll" or "anime" in service_key.lower():
            base_discover_url += "&with_genres=16&with_original_language=ja"
            if service_key == "crunchyroll" and not is_movie:
                base_discover_url += f"&with_networks={svc['id']}"
            if is_new_release:
                date_min = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
                p = "primary_release_date.gte" if is_movie else "first_air_date.gte"
                base_discover_url += f"&{p}={date_min}"
        elif svc["type"] == "provider":
            base_discover_url += "&watch_region=US"
            base_discover_url += f"&with_watch_providers={svc['id']}"
            base_discover_url += "&with_watch_monetization_types=flatrate"
            if is_new_release:
                date_min = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
                p = "primary_release_date.gte" if is_movie else "first_air_date.gte"
                base_discover_url += f"&{p}={date_min}"
        elif svc["type"] == "network":
            param = "with_companies" if is_movie else "with_networks"
            base_discover_url += f"&{param}={svc['id']}"
            if is_new_release:
                date_min = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
                p = "primary_release_date.gte" if is_movie else "first_air_date.gte"
                base_discover_url += f"&{p}={date_min}"
        else:
            base_discover_url = f"{TMDB_BASE_URL}/trending/{m_type}/week"

        try:
            # Fetch 3 pages to get enough results for the top-N selection
            all_potential_results = []
            pages_to_fetch = 3 if "trending" not in base_discover_url else 1

            for page in range(1, pages_to_fetch + 1):
                paged_url = f"{base_discover_url}&page={page}" if "?" in base_discover_url else base_discover_url
                res = requests.get(paged_url, headers=HEADERS).json()
                all_potential_results.extend(res.get('results', []))
                if "trending" in base_discover_url: break # Trending only has 1 page

            # --- Take top results (deterministic, matching TMDB sort order) ---
            selected_items = all_potential_results[:limit]

            for item in selected_items:
                try:
                    self.generate_image(item, is_movie, service_key, custom_label)
                except Exception as e:
                    print(f"Skipping {item.get('id')}: {e}")

            self.generate_api_json()
        except Exception as e:
            print(f"API Error in run(): {e}")

    def run_mdblist(self, username, list_name, label, service_key="mdblist", limit=5, pool_size=30):
        api_url = f"https://api.mdblist.com/lists/{username}/{list_name}/items"
        params = {"apikey": MDBLIST_API_KEY}

        # Retry with exponential backoff for rate limiting
        for attempt in range(5):
            try:
                res = requests.get(api_url, params=params)
                if res.status_code == 429:
                    wait = (attempt + 1) * 30
                    print(f"Rate limited. Retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                res.raise_for_status()
                data = res.json()
                break
            except Exception as e:
                print(f"MDBList API request failed: {e}")
                return

        # MDBList API returns { "movies": [...], "shows": [...], "pagination": {...} }
        items = data.get('movies', []) + data.get('shows', [])

        # Extract (tmdb_id, mediatype) pairs from each item
        tmdb_items = []
        for item in items:
            tmdb_id = item.get('ids', {}).get('tmdb')
            if tmdb_id:
                mediatype = item.get('mediatype', 'show')
                tmdb_items.append((tmdb_id, mediatype))

        # Pool: take first `pool_size` items, then randomly sample up to `limit`
        pool = tmdb_items[:pool_size]
        sample_size = min(len(pool), limit)
        if pool:
            selected = random.sample(pool, sample_size)
        else:
            selected = []

        for tmdb_id, mediatype in selected:
            is_movie = mediatype == 'movie'
            try:
                self.generate_image({'id': tmdb_id}, is_movie=is_movie, service_key=service_key, custom_label=label)
                print(f"Generated MDBList {'movie' if is_movie else 'TV show'}: TMDB {tmdb_id}")
            except Exception as e:
                print(f"Error processing MDBList item {tmdb_id}: {e}")

        self.generate_api_json()

if __name__ == "__main__":
    bot = MediaGenerator()

    # 1. Standard Targets
    targets = [
        ("netflix", "New Release on", True),
        ("netflix", "Popular on", False),
        ("paramount", "New Release on", True),
        ("paramount", "Popular on", False),
        ("amazon", "New Release on", True),
        ("amazon", "Popular on", False),
        ("peacock", "New Release on", True),
        ("peacock", "Popular on", False),
        ("anime_popular", "Popular Anime", False),
        ("anime_new", "New Seasonal Anime", True),
    ]

    for svc, label, new_rel in targets:
       bot.run(svc, True, label, 5, new_rel)
       bot.run(svc, False, label, 5, new_rel)

    for svc, label, new_rel in [("crunchyroll", "New on", True), ("crunchyroll", "Popular on", False)]:
        bot.run(svc, False, label, 10, new_rel)
        bot.run(svc, True, label, 10, new_rel)
