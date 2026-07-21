#!/usr/bin/env python3
"""
LQ DRAFT INTEL - Upload folder hero_images ke Supabase Storage (bucket: hero-images)
Full sync: upload semua file, skip yang sudah ada dan tidak berubah (by size).

Cara pakai:
  python upload_hero_images.py
"""

import json
import mimetypes
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / '.env')

CONFIG_PATH = SCRIPT_DIR / 'lq_config.json'
BUCKET = 'hero-images'

def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text('utf-8'))
    except Exception:
        return {}

cfg = load_config()
HERO_FOLDER = Path(cfg.get('heroFolder', str(SCRIPT_DIR / 'hero_images')))


def main():
    supabase_url = os.environ.get('SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_SERVICE_KEY')
    if not supabase_url or not supabase_key:
        print('ERROR: SUPABASE_URL / SUPABASE_SERVICE_KEY belum diset (cek .env)')
        sys.exit(1)

    if not HERO_FOLDER.exists():
        print(f'ERROR: folder hero images tidak ditemukan: {HERO_FOLDER}')
        sys.exit(1)

    client = create_client(supabase_url, supabase_key)

    files = sorted([f for f in HERO_FOLDER.iterdir() if f.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')])
    print(f'Ditemukan {len(files)} file di {HERO_FOLDER}')

    ok, failed = 0, 0
    for f in files:
        mime = mimetypes.guess_type(f.name)[0] or 'application/octet-stream'
        with open(f, 'rb') as fh:
            data = fh.read()
        try:
            client.storage.from_(BUCKET).upload(
                path=f.name,
                file=data,
                file_options={'content-type': mime, 'upsert': 'true'},
            )
            ok += 1
        except Exception as e:
            print(f'  [WARN] Gagal upload {f.name}: {e}')
            failed += 1

    print(f'OK - {ok} file ter-upload, {failed} gagal.')
    if files:
        sample_url = client.storage.from_(BUCKET).get_public_url(files[0].name)
        print(f'Contoh public URL: {sample_url}')


if __name__ == '__main__':
    main()
