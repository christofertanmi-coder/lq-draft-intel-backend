"""
Scraper gambar hero Mobile Legends via Fandom MediaWiki API.
Tidak mengakses halaman HTML langsung, sehingga tidak kena blokir Cloudflare.

Cara pakai:
    pip install requests beautifulsoup4
    python scrape_hero_images.py

Output:
    - Folder "hero_images/" berisi semua file gambar (PNG/JPG)
    - File "hero_images.csv" berisi daftar nama hero + URL gambar
"""

import os, re, csv, time, requests
from bs4 import BeautifulSoup

API  = "https://mobile-legends.fandom.com/api.php"
OUT_DIR  = "hero_images"
CSV_PATH = "hero_images.csv"

HEADERS = {
    "User-Agent": "MLBBHeroScraper/1.0 (educational project)",
}

session = requests.Session()
session.headers.update(HEADERS)


# ── Langkah 1: ambil HTML tabel dari API (lebih longgar dari halaman biasa) ──

def fetch_page_html(page_title: str) -> str:
    params = {
        "action": "parse",
        "page": page_title,
        "prop": "text",
        "format": "json",
        "disablelimitreport": 1,
    }
    r = session.get(API, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["parse"]["text"]["*"]


# ── Langkah 2: resolve nama file gambar → URL download via API ──

def get_image_urls(filenames: list[str]) -> dict[str, str]:
    """Ambil URL gambar dari daftar nama file (batch 50 sekaligus)."""
    url_map = {}
    for i in range(0, len(filenames), 50):
        batch = filenames[i:i+50]
        params = {
            "action": "query",
            "titles": "|".join(f"File:{fn}" for fn in batch),
            "prop": "imageinfo",
            "iiprop": "url",
            "format": "json",
        }
        r = session.get(API, params=params, timeout=30)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            title = page.get("title", "")          # "File:Hero011-icon.png"
            fn = title.replace("File:", "", 1)
            ii = page.get("imageinfo", [])
            if ii:
                url_map[fn] = ii[0]["url"]
    return url_map


# ── Langkah 3: parse tabel HTML hasil API ──

def parse_heroes(html: str):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="wikitable")
    if not table:
        table = soup.find("table")

    heroes = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        img_tag = row.find("img")
        if not img_tag:
            continue

        # data-image-name = nama file asli di wiki (paling reliable)
        file_name = img_tag.get("data-image-name") or img_tag.get("data-src", "").split("/")[-1].split("?")[0]
        if not file_name:
            continue

        link_tag = row.find("a", title=True)
        hero_name = link_tag["title"].strip() if link_tag else "unknown"

        hero_order = ""
        for c in cells:
            t = c.get_text(strip=True)
            if t.isdigit():
                hero_order = t
                break

        heroes.append({
            "hero_order": hero_order,
            "hero_name": hero_name,
            "file_name": file_name,
        })
    return heroes


# ── Main ──

def main():
    print("Mengambil data hero via API...")
    html = fetch_page_html("List of heroes")

    heroes = parse_heroes(html)
    print(f"Ditemukan {len(heroes)} hero.")

    print("Mengambil URL gambar via API...")
    filenames = [h["file_name"] for h in heroes]
    url_map = get_image_urls(filenames)

    os.makedirs(OUT_DIR, exist_ok=True)
    records = []

    print("Mulai download gambar...")
    for i, hero in enumerate(heroes, 1):
        fn = hero["file_name"]
        img_url = url_map.get(fn)
        if not img_url:
            print(f"[{i}/{len(heroes)}] URL tidak ditemukan: {hero['hero_name']}")
            continue

        ext = os.path.splitext(fn)[-1] or ".png"
        order = hero["hero_order"].zfill(3) if hero["hero_order"] else "000"
        safe  = re.sub(r"[^\w\-]", "_", hero["hero_name"])
        filename = f"{order}_{safe}{ext}"
        filepath = os.path.join(OUT_DIR, filename)

        records.append({
            "hero_order": hero["hero_order"],
            "hero_name":  hero["hero_name"],
            "image_url":  img_url,
            "filename":   filename,
        })

        if os.path.exists(filepath):
            print(f"[{i}/{len(heroes)}] SKIP (sudah ada): {hero['hero_name']}")
            continue

        try:
            r = session.get(img_url, timeout=30)
            r.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(r.content)
            print(f"[{i}/{len(heroes)}] OK: {hero['hero_name']}")
        except Exception as e:
            print(f"[{i}/{len(heroes)}] GAGAL: {hero['hero_name']} -> {e}")

        time.sleep(0.2)

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["hero_order","hero_name","image_url","filename"])
        writer.writeheader()
        writer.writerows(records)

    print(f"\nSelesai! {len(records)} gambar di folder '{OUT_DIR}/', daftar di '{CSV_PATH}'.")


if __name__ == "__main__":
    main()
