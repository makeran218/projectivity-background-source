import requests
from PIL import Image, ImageDraw, ImageFont, ImageStat, ImageFilter
from io import BytesIO
import os
import textwrap
import re
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import shutil

load_dotenv(verbose=True)

# --- Configuration ---
TMDB_BEARER_TOKEN = os.getenv('TMDB_BEARER_TOKEN')
TMDB_BASE_URL = os.getenv('TMDB_BASE_URL', 'https://api.themoviedb.org/3')
HEADERS = {"accept": "application/json", "Authorization": f"Bearer {TMDB_BEARER_TOKEN}"}

# Font Paths
TITLE_FONT_PATH = 'BebasNeue-Regular.ttf'
BODY_FONT_PATH = 'Roboto-Light.ttf'
FALLBACK_FONT_PATH = 'NotoSansCJK-Regular.ttc'

BACKGROUND_DIR = "tmdb_backgrounds"
BASE_URL_FOR_API = "https://makeran218.github.io/projectivity-background-source"

# 4K Canvas
CANVAS_W = 3840
CANVAS_H = 2160

SERVICES = {
    "netflix": {"id": 213, "type": "network", "logo": "netflix_logo.png"},
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
        # Download Bebas Neue for Titles
        if not os.path.exists(TITLE_FONT_PATH):
            print("Downloading Bebas Neue...")
            url = 'https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf'
            r = requests.get(url)
            with open(TITLE_FONT_PATH, 'wb') as f: f.write(r.content)

        # Download Roboto for Body Text
        if not os.path.exists(BODY_FONT_PATH):
            print("Downloading Roboto Light...")
            url = 'https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Light.ttf'
            r = requests.get(url)
            with open(BODY_FONT_PATH, 'wb') as f: f.write(r.content)

    def get_font(self, size, text="", is_title=False):
        # 1. Handle CJK Fallback
        if any(ord(c) > 0x4e00 for c in text):
            if os.path.exists(FALLBACK_FONT_PATH):
                return ImageFont.truetype(FALLBACK_FONT_PATH, size)
            print("Warning: CJK font missing, falling back to default.")

        # 2. Use Bebas for Titles, Roboto for others
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

    def generate_image(self, item, is_movie, service_key, custom_label):
        m_type, m_id = ("movie" if is_movie else "tv"), item['id']
        title = item.get('title') if is_movie else item.get('name')
        svc = SERVICES.get(service_key, SERVICES["trending"])

        details = self.get_details(m_type, m_id)
        date_raw = item.get('release_date') if is_movie else item.get('first_air_date')
        year = date_raw[:4] if date_raw else "N/A"

        genres_source = MOVIE_GENRES if is_movie else TV_GENRES
        genre_str = ", ".join([genres_source.get(gid, '') for gid in item.get('genre_ids', [])][:2])
        extra = f"{details.get('runtime', 0)//60}h {details.get('runtime', 0)%60}m" if is_movie else f"{details.get('number_of_seasons', 1)} Seasons"
        info_text = f"{genre_str}  \u2022  {year}  \u2022  {extra}  \u2022  TMDB: {round(item.get('vote_average', 0), 1)}"

        # 1. Background Setup
        backdrop_path = item.get('backdrop_path')
        if not backdrop_path: return
        bg_res = requests.get(f"https://image.tmdb.org/t/p/original{backdrop_path}")
        image = Image.open(BytesIO(bg_res.content)).convert("RGBA")

        target_ratio = CANVAS_W / CANVAS_H
        img_ratio = image.width / image.height
        if img_ratio > target_ratio:
            new_w = int(target_ratio * image.height)
            image = image.crop(((image.width - new_w)//2, 0, (image.width + new_w)//2, image.height))
        else:
            new_h = int(image.width / target_ratio)
            image = image.crop((0, (image.height - new_h)//2, image.width, (image.height + new_h)//2))
        image = image.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)

        if os.path.exists("vignette.png"):
            vig = Image.open("vignette.png").convert("RGBA")
            if vig.size != (CANVAS_W, CANVAS_H):
                vig = vig.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
            image.alpha_composite(vig)

        draw = ImageDraw.Draw(image)

        # 2. Branding (Centered Top)
        if os.path.exists(svc["logo"]):
            brand_logo = Image.open(svc["logo"]).convert("RGBA")
            log_h = 100
            brand_logo = brand_logo.resize((int(brand_logo.width * (log_h/brand_logo.height)), log_h))
            f_custom = self.get_font(40, custom_label, is_title=False)
            label_text = f"{custom_label}".upper()
            lab_bbox = draw.textbbox((0, 0), label_text, font=f_custom)
            draw.text(((CANVAS_W - (lab_bbox[2]-lab_bbox[0]))//2, 100), label_text, font=f_custom, fill="white")
            image.alpha_composite(brand_logo, ((CANVAS_W - brand_logo.width)//2, 160))

        # 3. Main Content
        current_y = 480
        MAX_TEXT_W = int(CANVAS_W * 0.8)
        MAX_TITLE_H = 500

        logo_path = self.get_media_logo(m_type, m_id)
        if logo_path:
            try:
                l_res = requests.get(f"https://image.tmdb.org/t/p/original{logo_path}")
                logo_img = Image.open(BytesIO(l_res.content)).convert("RGBA")
                ratio = min(MAX_TEXT_W/logo_img.width, MAX_TITLE_H/logo_img.height)
                logo_img = logo_img.resize((int(logo_img.width * ratio), int(logo_img.height * ratio)), Image.LANCZOS)
                image.alpha_composite(logo_img, ((CANVAS_W - logo_img.width)//2, current_y))
                current_y += logo_img.height + 40
            except: logo_path = None

        if not logo_path:
            is_cjk = any(ord(c) > 0x4e00 for c in title)
            display_title = title.upper() if not is_cjk else title
            target_font_size = 350 if not is_cjk else 250

            while target_font_size > 80:
                f_title = self.get_font(target_font_size, display_title, is_title=True)
                wrap_val = (25 if target_font_size > 250 else 40) if not is_cjk else 15
                wrapped_lines = textwrap.wrap(display_title, width=wrap_val)
                total_h, max_line_w, line_data = 0, 0, []

                for line in wrapped_lines:
                    bbox = draw.textbbox((0, 0), line, font=f_title)
                    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    total_h += h + 20
                    max_line_w = max(max_line_w, w)
                    line_data.append((line, w, h))

                if max_line_w <= MAX_TEXT_W and total_h <= MAX_TITLE_H:
                    shadow_offset = 3
                    for line, w, h in line_data:
                        # Shadow
                        draw.text(((CANVAS_W - w)//2 + shadow_offset, current_y + shadow_offset), line, font=f_title, fill=(0, 0, 0, 180))
                        # Main Text
                        draw.text(((CANVAS_W - w)//2, current_y), line, font=f_title, fill="white")
                        current_y += h + 20
                    break
                else: target_font_size -= 20

        current_y = max(current_y, 480 + MAX_TITLE_H + 20)

        # 4. Info & Description (Roboto with Shadows)
        f_info = self.get_font(70, info_text, is_title=False)
        i_bbox = draw.textbbox((0, 0), info_text, font=f_info)
        draw.text(((CANVAS_W - (i_bbox[2]-i_bbox[0]))//2 + 1, current_y + 1), info_text, font=f_info, fill=(0,0,0,150))
        draw.text(((CANVAS_W - (i_bbox[2]-i_bbox[0]))//2, current_y), info_text, font=f_info, fill=(210, 210, 210))
        current_y += 110

        f_ov = self.get_font(55, item.get('overview', ''), is_title=False)
        wrapped_ov = textwrap.wrap(item.get('overview', ''), width=110)
        for line in wrapped_ov[:3]:
            l_bbox = draw.textbbox((0, 0), line, font=f_ov)
            draw.text(((CANVAS_W - (l_bbox[2]-l_bbox[0]))//2 + 2, current_y + 2), line, font=f_ov, fill=(0,0,0,150))
            draw.text(((CANVAS_W - (l_bbox[2]-l_bbox[0]))//2, current_y), line, font=f_ov, fill="white")
            current_y += 75

        output_path = os.path.join(BACKGROUND_DIR, f"{m_type}_tmdb_{m_id}.jpg")
        image.convert("RGB").save(output_path, "JPEG", quality=92, optimize=True)

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
        url = f"{TMDB_BASE_URL}/discover/{m_type}?include_adult=false&language=en-US&sort_by=popularity.desc"

        if service_key == "crunchyroll" or "anime" in service_key.lower():
            url += "&with_genres=16&with_original_language=ja"
            if service_key == "crunchyroll" and not is_movie:
                url += f"&with_networks={svc['id']}"
            if is_new_release:
                date_min = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
                p = "primary_release_date.gte" if is_movie else "first_air_date.gte"
                url += f"&{p}={date_min}"
        elif svc["type"] == "network":
            param = "with_companies" if is_movie else "with_networks"
            url += f"&{param}={svc['id']}"
            if is_new_release:
                date_min = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
                p = "primary_release_date.gte" if is_movie else "first_air_date.gte"
                url += f"&{p}={date_min}"
        else:
            url = f"{TMDB_BASE_URL}/trending/{m_type}/week"

        try:
            results = requests.get(url, headers=HEADERS).json().get('results', [])
            for item in results[:limit]:
                try: self.generate_image(item, is_movie, service_key, custom_label)
                except Exception as e: print(f"Skipping {item.get('id')}: {e}")
            self.generate_api_json()
        except Exception as e: print(f"API Error: {e}")

if __name__ == "__main__":
    bot = MediaGenerator()
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