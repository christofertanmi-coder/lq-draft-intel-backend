#!/usr/bin/env python3
"""
LQ DRAFT INTEL - Download drafts dari Supabase ke draft_simulator.csv lokal
Menulis ulang draft_simulator.csv dengan format kolom yang sama seperti versi lama,
supaya pipeline.py bisa membacanya tanpa perubahan apa pun.

Cara pakai:
  python download_drafts.py
"""

import csv
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / '.env')

CONFIG_PATH = SCRIPT_DIR / 'lq_config.json'


def backup_before_overwrite(file_path: Path):
    """Simpan salinan file_path (kalau ada isinya) ke _backups/ sebelum ditimpa.
    Insurance murah supaya overwrite tidak pernah menghilangkan data tanpa jejak."""
    if not file_path.exists() or file_path.stat().st_size == 0:
        return
    backup_dir = file_path.parent / '_backups'
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = backup_dir / f'{file_path.stem}_{stamp}{file_path.suffix}'
    shutil.copy2(file_path, dest)
    print(f'[Backup] {file_path.name} -> {dest}')

def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text('utf-8'))
    except Exception:
        return {}

cfg = load_config()
CSV_FOLDER = Path(cfg.get('csvFolder', str(SCRIPT_DIR)))
DRAFT_CSV = CSV_FOLDER / 'draft_simulator.csv'

HEADER = ['Week','Day','Game','Date','TeamA','TeamB','BluePicks','RedPicks','BlueBans',
          'RedBans','Winner','Time','ResultA','ResultB','BlueDraftOrder','RedDraftOrder',
          'BlueBanOrder','RedBanOrder','BluePickRoles','RedPickRoles']


def join_list(v):
    if not v:
        return ''
    if isinstance(v, list):
        return '; '.join(str(x).strip() for x in v if str(x).strip())
    return str(v)


def main():
    supabase_url = os.environ.get('SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_SERVICE_KEY')
    if not supabase_url or not supabase_key:
        print('ERROR: SUPABASE_URL / SUPABASE_SERVICE_KEY belum diset (cek .env)')
        sys.exit(1)

    client = create_client(supabase_url, supabase_key)
    resp = client.table('drafts').select('*').order('id').execute()
    drafts = resp.data or []

    CSV_FOLDER.mkdir(parents=True, exist_ok=True)
    backup_before_overwrite(DRAFT_CSV)
    with open(DRAFT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        for d in drafts:
            writer.writerow([
                d.get('week',''), d.get('day',''), d.get('game',''), d.get('date',''),
                d.get('team_a',''), d.get('team_b',''),
                join_list(d.get('blue_picks')), join_list(d.get('red_picks')),
                join_list(d.get('blue_bans')), join_list(d.get('red_bans')),
                d.get('winner',''), d.get('time',''),
                d.get('result_a',''), d.get('result_b',''),
                join_list(d.get('blue_draft_order')), join_list(d.get('red_draft_order')),
                join_list(d.get('blue_ban_order')), join_list(d.get('red_ban_order')),
                join_list(d.get('blue_pick_roles')), join_list(d.get('red_pick_roles')),
            ])

    print(f'OK - {len(drafts)} draft ditulis ke {DRAFT_CSV}')


if __name__ == '__main__':
    main()
