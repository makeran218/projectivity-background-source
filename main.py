import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os
import shutil
import textwrap
import re
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPM

load_dotenv(verbose=True)

# --- Configuration ---
TMDB_BEARER_TOKEN = os.getenv('TMDB_BEARER_TOKEN')
TMDB_BASE_URL = os.getenv('TMDB_BASE_URL', 'https://api.themoviedb.org/3')
LANGUAGE = os.getenv("TMDB_LANGUAGE", "en-US")
HEADERS = {"accept": "application/json", "Authorization": f"Bearer {TMDB_BEARER_TOKEN}"}

TRUETYPE_PATH = 'Roboto-Light.ttf'
FALLBACK_FONT_PATH = 'NotoSansCJK-Regular.ttc'
BACKGROUND_DIR = "tmdb_backgrounds"
# Update this to your GitHub Pages URL later
# --- Configuration ---
# This points directly to the raw file storage on GitHub
BASE_URL_FOR_API = "https://makeran218.github.io/projectivity-background-source"

SERVICES = {
    "netflix": {"id": 213, "type": "network", "logo": "netflix_logo.png"},
    "disney":  {"id": 2739, "type": "network", "logo": "disney-logo.png"},
    "amazon":  {"id": 1024, "type": "network", "logo": "amazon.png"},
    "apple":   {"id": 2552, "type": "network", "logo": "apple.png"},
    "peacock": {"id": 3353, "type": "network", "logo": "peacock.png"},
    "paramount": {"id": 4330, "type": "network", "logo": "paramount-logo.png"},
    "trending": {"id": None, "type": "trending", "logo": "tmdblogo.png"}
}

def get_genres(media_type):
    url = f'{TMDB_BASE_URL}/genre/{media_type}/list?language={LANGUAGE}'
    try:
        data = requests.get(url, headers=HEADERS).json()
        return {g['id']: g['name'] for g in data.get('genres', [])}
    except: return {}

MOVIE_GENRES = get_genres("movie")
TV_GENRES = get_genres("tv")

class MediaGenerator:
    def __init__(self):
        if not os.path.exists(BACKGROUND_DIR):
            os.makedirs(BACKGROUND_DIR, exist_ok=True)
        self.download_fonts()

    def download_fonts(self):
        if not os.path.exists(TRUETYPE_PATH):
            url = 'https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Light.ttf'
            r = requests.get(url)
            with open(TRUETYPE_PATH, 'wb') as f: f.write(r.content)

    def contains_cjk(self, text):
        return bool(re.search(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', text))

    def get_font(self, size, text=""):
        if self.contains_cjk(text) and os.path.exists(FALLBACK_FONT_PATH):
            return ImageFont.truetype(FALLBACK_FONT_PATH, size)
        return ImageFont.truetype(TRUETYPE_PATH, size)

    def get_details(self, media_type, media_id):
        url = f'{TMDB_BASE_URL}/{media_type}/{media_id}?language={LANGUAGE}'
        return requests.get(url, headers=HEADERS).json()

    def get_media_logo(self, media_type, media_id):
        url = f"{TMDB_BASE_URL}/{media_type}/{media_id}/images"
        response = requests.get(url, headers=HEADERS).json()
        logos = [l for l in response.get("logos", []) if l.get("iso_639_1") == LANGUAGE.split('-')[0]]
        if not logos: logos = [l for l in response.get("logos", []) if l.get("iso_639_1") == "en"]
        return sorted(logos, key=lambda x: x.get("vote_average", 0), reverse=True)[0]["file_path"] if logos else None

    def generate_image(self, item, is_movie, service_key, custom_label):
        m_type, m_id = ("movie" if is_movie else "tv"), item['id']
        title = item.get('title') if is_movie else item.get('name')
        svc = SERVICES.get(service_key, SERVICES["trending"])

        details = self.get_details(m_type, m_id)
        date_raw = item.get('release_date') if is_movie else item.get('first_air_date')
        year = date_raw[:4] if date_raw else "N/A"

        genres_source = MOVIE_GENRES if is_movie else TV_GENRES
        genre_str = ", ".join([genres_source.get(gid, '') for gid in item.get('genre_ids', [])][:2])
        extra = f"{details.get('runtime', 0)//60}h{details.get('runtime', 0)%60}min" if is_movie else f"{details.get('number_of_seasons', 1)} Seasons"
        info_text = f"{genre_str}  \u2022  {year}  \u2022  {extra}  \u2022  TMDB: {round(item.get('vote_average', 0), 1)}"

        backdrop_path = item.get('backdrop_path')
        if not backdrop_path: return

        # Process Images
        bg_res = requests.get(f"https://image.tmdb.org/t/p/original{backdrop_path}")
        image = Image.open(BytesIO(bg_res.content))
        image = image.resize((int(image.width * (1500/image.height)), 1500))

        bckg = Image.open("bckg.png").convert("RGBA")
        overlay = Image.open("overlay.png").convert("RGBA")
        brand_logo = Image.open(svc["logo"]).convert("RGBA")

        bckg.paste(image, (1175, 0))
        bckg.alpha_composite(overlay, (1175, 0))
        draw = ImageDraw.Draw(bckg)

        # Overview & Info
        f_small = self.get_font(50, item.get('overview', ''))
        wrapped_ov = "\n".join(textwrap.wrap(item.get('overview', ''), width=70, max_lines=2, placeholder=" ..."))
        draw.text((210, 730), wrapped_ov, font=f_small, fill="white")
        draw.text((210, 650), info_text, font=f_small, fill=(150, 150, 150))

        # Brand Logo Positioning
        f_custom = self.get_font(30, custom_label)
        label_pos = (210, 890)
        draw.text(label_pos, f"{custom_label}".upper(), font=f_custom, fill="white")
        bbox = draw.textbbox(label_pos, f"{custom_label}".upper(), font=f_custom)

        log_h = 80
        brand_logo = brand_logo.resize((int(brand_logo.width * (log_h/brand_logo.height)), log_h))
        bckg.alpha_composite(brand_logo, (label_pos[0], bbox[3] + 20))

        # Media Logo Logic (SVG/PNG)
        logo_path = self.get_media_logo(m_type, m_id)
        logo_img = None
        if logo_path:
            l_res = requests.get(f"https://image.tmdb.org/t/p/original{logo_path}")
            if logo_path.lower().endswith('.svg'):
                drawing = svg2rlg(BytesIO(l_res.content))
                mem = BytesIO()
                renderPM.drawToFile(drawing, mem, fmt="PNG")
                logo_img = Image.open(mem).convert("RGBA")
            else:
                logo_img = Image.open(BytesIO(l_res.content)).convert("RGBA")

        if logo_img:
            ratio = min(1000/logo_img.width, 450/logo_img.height)
            logo_img = logo_img.resize((int(logo_img.width * ratio), int(logo_img.height * ratio)), Image.LANCZOS)
            bckg.alpha_composite(logo_img, (200, 600 - logo_img.height))
        else:
            f_title = self.get_font(190, title)
            draw.text((200, 420), title, font=f_title, fill="white")

        bckg.convert("RGB").save(os.path.join(BACKGROUND_DIR, f"{m_type}_tmdb_{m_id}.jpg"), "JPEG")

    def generate_api_json(self):
        api_data = []
        for filename in os.listdir(BACKGROUND_DIR):
            if filename.endswith(".jpg"):
                name = os.path.splitext(filename)[0]
                last_u = name.rfind('_')
                api_data.append({
                    "actionUrl": f"{name[:last_u]}:{name[last_u+1:]}",
                    "imageUrl": f"{BASE_URL_FOR_API}/{BACKGROUND_DIR}/{filename}",
                    "title": name
                })
        with open("api.json", "w") as f: json.dump(api_data, f, indent=4)

    def run(self, service_key, is_movie, custom_label, limit=5, is_new_release=False):
        svc = SERVICES[service_key]
        m_type = "movie" if is_movie else "tv"
        if svc["type"] == "network":
            param = "with_companies" if is_movie else "with_networks"
            url = f"{TMDB_BASE_URL}/discover/{m_type}?{param}={svc['id']}&sort_by=popularity.desc"
        else:
            url = f"{TMDB_BASE_URL}/trending/{m_type}/week"

        results = requests.get(url, headers=HEADERS).json().get('results', [])
        for item in results[:limit]:
            try: self.generate_image(item, is_movie, service_key, custom_label)
            except Exception as e: print(f"Error: {e}")
        self.generate_api_json()

if __name__ == "__main__":
    bot = MediaGenerator()

    # Netflix
    bot.run(service_key="netflix", is_movie=True, custom_label="New Release on ", limit=5, is_new_release=True)
    bot.run(service_key="netflix", is_movie=False, custom_label="New Release on ", limit=5, is_new_release=True)
    bot.run(service_key="netflix", is_movie=True, custom_label="Popular on ", limit=5, is_new_release=False)

    # Paramount
    bot.run(service_key="paramount", is_movie=True, custom_label="New Release on ", limit=5, is_new_release=True)
    bot.run(service_key="paramount", is_movie=False, custom_label="New Release on ", limit=5, is_new_release=True)
    bot.run(service_key="paramount", is_movie=True, custom_label="Popular on ", limit=5, is_new_release=False)

    # Amazon
    bot.run(service_key="amazon", is_movie=True, custom_label="New Release on ", limit=5, is_new_release=True)
    bot.run(service_key="amazon", is_movie=False, custom_label="New Release on ", limit=5, is_new_release=True)
    bot.run(service_key="amazon", is_movie=True, custom_label="Popular on ", limit=5, is_new_release=False)

    #peacock
    bot.run(service_key="peacock", is_movie=True, custom_label="New Release on ", limit=5, is_new_release=True)
    bot.run(service_key="peacock", is_movie=False, custom_label="New Release on ", limit=5, is_new_release=True)
    bot.run(service_key="peacock", is_movie=True, custom_label="Popular on ", limit=5, is_new_release=False)