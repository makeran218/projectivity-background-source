"""
MediaGenerator: fetch TMDB data and generate background images for the
projectivity launcher. All image layout/drawing lives in render.py (shared
with the settings GUI, web_gui.py).
"""

import requests
from PIL import Image
from io import BytesIO
import os
import time
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import shutil
import random

from render import Renderer, SERVICES, TITLE_FONT_PATH, BODY_FONT_PATH

load_dotenv(verbose=True)

# --- Configuration ---
TMDB_BEARER_TOKEN = os.getenv('TMDB_BEARER_TOKEN')
TMDB_BASE_URL = os.getenv('TMDB_BASE_URL', 'https://api.themoviedb.org/3')
MDBLIST_API_KEY = os.getenv('MDBLIST_API_KEY')

HEADERS = {"accept": "application/json", "Authorization": f"Bearer {TMDB_BEARER_TOKEN}"}

BACKGROUND_DIR = "tmdb_backgrounds"
BASE_URL_FOR_API = "https://makeran218.github.io/projectivity-background-source"

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

    def get_details(self, media_type, media_id):
        url = f"{TMDB_BASE_URL}/{media_type}/{media_id}?language=en-US"
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
        # METADATA (from TMDB details)
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
        # SERVICE LOGO
        # ============================================================

        service_logo = None
        if os.path.exists(svc["logo"]):
            try:
                service_logo = Image.open(svc["logo"]).convert("RGBA")
            except Exception:
                pass

        # ============================================================
        # TITLE LOGO (optional; falls back to text title if missing)
        # ============================================================

        title_logo = None
        logo_path = self.get_media_logo(m_type, m_id)
        if logo_path:
            try:
                l_res = requests.get(
                    f"https://image.tmdb.org/t/p/original{logo_path}",
                    timeout=30
                )
                l_res.raise_for_status()
                title_logo = Image.open(
                    BytesIO(l_res.content)
                ).convert("RGBA")
            except Exception:
                title_logo = None

        # ============================================================
        # RENDER (all layout logic lives in render.py)
        # ============================================================

        renderer = Renderer()
        image = renderer.render(
            image,
            label=custom_label,
            service_logo=service_logo,
            title_logo=title_logo,
            title=title,
            genres=genres,
            year=year,
            extra=extra,
            certification=certification,
            rating=rating,
            overview=overview,
        )

        output_path = os.path.join(
            BACKGROUND_DIR,
            f"{m_type}_tmdb_{m_id}.jpg"
        )

        image.convert("RGB").save(
            output_path,
            "JPEG",
            quality=renderer.output_quality(),
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
        data = None
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

        if data is None:
            print("MDBList API unreachable after retries.")
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
