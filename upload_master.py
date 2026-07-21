#!/usr/bin/env python3
"""
LQ DRAFT INTEL - Upload master.csv ke Supabase (tabel matches_master)
Full replace tiap run: truncate lalu insert ulang semua baris dari master.csv.

Cara pakai:
  python upload_master.py
"""

import csv
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / '.env')

CONFIG_PATH = SCRIPT_DIR / 'lq_config.json'

def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text('utf-8'))
    except Exception:
        return {}

cfg = load_config()
CSV_FOLDER = Path(cfg.get('csvFolder', str(SCRIPT_DIR)))
MASTER_CSV = CSV_FOLDER / 'master.csv'

# Map kolom master.csv (lihat pipeline.py MASTER_COLS) -> kolom tabel matches_master
COL_MAP = {
    'Date':           'date',
    'DateISO':        'date_iso',
    'Week':           'week',
    'Day':            'day',
    'Game':           'game',
    'TeamA':          'team_a',
    'TeamB':          'team_b',
    'Winner':         'winner',
    'ScoreA':         'score_a',
    'ScoreB':         'score_b',
    'BluePicks':      'blue_picks',
    'RedPicks':       'red_picks',
    'BlueBans':       'blue_bans',
    'RedBans':        'red_bans',
    'ResultA':        'result_a',
    'ResultB':        'result_b',
    'Time':           'time',
    'BlueDraftOrder': 'blue_draft_order',
    'RedDraftOrder':  'red_draft_order',
    'SourceFile':     'source_file',
}


def main():
    supabase_url = os.environ.get('SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_SERVICE_KEY')
    if not supabase_url or not supabase_key:
        print('ERROR: SUPABASE_URL / SUPABASE_SERVICE_KEY belum diset (cek .env)')
        sys.exit(1)

    if not MASTER_CSV.exists():
        print(f'ERROR: master.csv tidak ditemukan di {MASTER_CSV}. Jalankan pipeline.py dulu.')
        sys.exit(1)

    client = create_client(supabase_url, supabase_key)

    rows = []
    with open(MASTER_CSV, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for raw in reader:
            row = {}
            for src_col, dest_col in COL_MAP.items():
                row[dest_col] = raw.get(src_col, '') or ''
            rows.append(row)

    print(f'Membaca {len(rows)} baris dari {MASTER_CSV}')

    # Full replace: hapus semua baris lama, insert baris baru
    client.table('matches_master').delete().gte('id', 0).execute()

    if rows:
        BATCH = 500
        for i in range(0, len(rows), BATCH):
            batch = rows[i:i + BATCH]
            client.table('matches_master').insert(batch).execute()
            print(f'  Upload batch {i // BATCH + 1}: {len(batch)} baris')

    print(f'OK - {len(rows)} baris ter-upload ke Supabase (matches_master).')


if __name__ == '__main__':
    main()
