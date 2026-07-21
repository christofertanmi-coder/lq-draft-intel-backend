#!/usr/bin/env python3
"""
LQ DRAFT INTEL - Data Pipeline
Merge, normalize, dedupe, dan sort semua CSV ke satu master.csv

Cara pakai:
  python pipeline.py

Konfigurasi di bawah (CONFIG) atau lewat lq_config.json (otomatis dibaca kalau ada).
"""

import csv
import json
import os
import re
import sys
from datetime import datetime, date
from pathlib import Path

# Fix encoding Windows terminal (cmd.exe default cp1252 tidak support UTF-8)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8','utf-8-sig'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ── CONFIG ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / 'lq_config.json'

def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text('utf-8'))
    except:
        return {}

cfg = load_config()
CSV_FOLDER   = Path(cfg.get('csvFolder', str(SCRIPT_DIR)))
OUTPUT_FILE  = CSV_FOLDER / 'master.csv'
ALIAS_FILE   = SCRIPT_DIR / 'aliases.json'   # opsional: nama tim & hero aliases

# ── MASTER OUTPUT COLUMNS ─────────────────────────────────────────────────────
MASTER_COLS = [
    'Date', 'DateISO', 'Week', 'Day', 'Game',
    'TeamA', 'TeamB', 'Winner',
    'ScoreA', 'ScoreB',
    'BluePicks', 'RedPicks', 'BlueBans', 'RedBans',
    'ResultA', 'ResultB',
    'Time',
    'BlueDraftOrder', 'RedDraftOrder',
    'SourceFile'
]

# ── ALIASES (opsional) ────────────────────────────────────────────────────────
def load_aliases():
    """Load team & hero name aliases dari aliases.json kalau ada."""
    if not ALIAS_FILE.exists():
        return {}, {}
    try:
        data = json.loads(ALIAS_FILE.read_text('utf-8'))
        return data.get('teams', {}), data.get('heroes', {})
    except:
        return {}, {}

team_aliases, hero_aliases = load_aliases()

def normalize_team(name):
    """Normalisasi nama tim: strip, lowercase lookup di aliases."""
    if not name:
        return ''
    name = name.strip()
    key = name.lower().strip()
    return team_aliases.get(key, name)

def normalize_hero(name):
    """Normalisasi nama hero: strip, lookup aliases."""
    if not name:
        return ''
    name = name.strip()
    key = name.lower().strip()
    return hero_aliases.get(key, name)

def normalize_heroes(raw):
    """Parse dan normalisasi string hero (pisah pakai ; atau ,)."""
    if not raw:
        return ''
    # Pisah dengan ; atau | - kompatibel dengan kedua format
    heroes = re.split(r'[;|]', raw)
    heroes = [normalize_hero(h) for h in heroes if h.strip()]
    return '; '.join(heroes)

# ── DATE PARSING ──────────────────────────────────────────────────────────────
DATE_FORMATS = [
    '%Y-%m-%d',          # 2026-07-01 (ISO)
    '%d/%m/%Y',          # 02/07/2026 (simulator)
    '%B %d, %Y',         # July 1, 2026 (Liquidpedia full)
    '%b %d, %Y',         # Jul 1, 2026
    '%d %B %Y',          # 1 July 2026
    '%m/%d/%Y',          # 07/01/2026 (US format)
    '%d-%m-%Y',          # 01-07-2026
]

def parse_date(raw):
    """Parse berbagai format tanggal → (date_obj, iso_string). Return (None,'') kalau gagal."""
    if not raw:
        return None, ''
    # Hapus bagian waktu dan timezone kalau ada (misal "July 1, 2026 - 16:00 WIB")
    cleaned = re.sub(r'\s*[-–]\s*\d{1,2}:\d{2}.*$', '', raw).strip()
    cleaned = re.sub(r'\s*(WIB|UTC|GMT|ICT).*$', '', cleaned).strip()
    for fmt in DATE_FORMATS:
        try:
            d = datetime.strptime(cleaned, fmt).date()
            return d, d.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None, ''

# ── COLUMN MAPPING ────────────────────────────────────────────────────────────
# Map nama kolom dari berbagai format sumber ke nama standar internal
COL_MAP = {
    # Liquidpedia format
    'team a':        'TeamA',
    'team b':        'TeamB',
    'score a':       'ScoreA',
    'score b':       'ScoreB',
    'result a':      'ResultA',
    'result b':      'ResultB',
    'blue picks':    'BluePicks',
    'red picks':     'RedPicks',
    'blue bans':     'BlueBans',
    'red bans':      'RedBans',
    # simulator / existing format (sudah benar tapi lowercase dulu)
    'teama':         'TeamA',
    'teamb':         'TeamB',
    'scorea':        'ScoreA',
    'scoreb':        'ScoreB',
    'resulta':       'ResultA',
    'resultb':       'ResultB',
    'bluepicks':     'BluePicks',
    'redpicks':      'RedPicks',
    'bluebans':      'BlueBans',
    'redbans':       'RedBans',
    'bluedraftorder':'BlueDraftOrder',
    'reddraftorder': 'RedDraftOrder',
    # common shared
    'week':  'Week',
    'day':   'Day',
    'game':  'Game',
    'date':  'Date',
    'winner':'Winner',
    'time':  'Time',
}

def map_cols(header):
    """Map header CSV sumber ke nama kolom standar."""
    mapping = {}
    for i, col in enumerate(header):
        key = col.strip().lower().replace(' ', '').replace('_', '')
        # Coba direct lookup
        canonical = COL_MAP.get(col.strip().lower()) or COL_MAP.get(key)
        if canonical:
            mapping[canonical] = i
        else:
            # Fallback: pakai nama asli kalau ada di MASTER_COLS
            camel = col.strip()
            if camel in MASTER_COLS:
                mapping[camel] = i
    return mapping

# ── ROW PARSING ───────────────────────────────────────────────────────────────
def parse_row(raw_row, col_map, source_file):
    """Parse satu baris CSV → dict dengan kolom standar."""
    def get(col):
        i = col_map.get(col)
        if i is None or i >= len(raw_row):
            return ''
        return raw_row[i].strip()

    date_raw = get('Date')
    date_obj, date_iso = parse_date(date_raw)

    team_a = normalize_team(get('TeamA'))
    team_b = normalize_team(get('TeamB'))
    winner = normalize_team(get('Winner'))
    blue_picks = normalize_heroes(get('BluePicks'))
    red_picks  = normalize_heroes(get('RedPicks'))
    blue_bans  = normalize_heroes(get('BlueBans'))
    red_bans   = normalize_heroes(get('RedBans'))
    blue_draft = normalize_heroes(get('BlueDraftOrder'))
    red_draft  = normalize_heroes(get('RedDraftOrder'))

    # Infer Winner dari ResultA/ResultB kalau Winner kosong
    result_a = get('ResultA').upper()
    result_b = get('ResultB').upper()
    if not winner:
        if result_a == 'W':
            winner = team_a
        elif result_b == 'W':
            winner = team_b

    # Infer ResultA/ResultB dari Winner kalau kosong
    if winner and not result_a:
        result_a = 'W' if winner == team_a else 'L'
    if winner and not result_b:
        result_b = 'W' if winner == team_b else 'L'

    # Bersihkan field Game (hapus "Game " prefix kalau ada)
    game = get('Game')
    game = re.sub(r'^Game\s*', '', game, flags=re.IGNORECASE).strip()

    return {
        'Date':           date_raw,
        'DateISO':        date_iso,
        'Week':           get('Week'),
        'Day':            get('Day'),
        'Game':           game,
        'TeamA':          team_a,
        'TeamB':          team_b,
        'Winner':         winner,
        'ScoreA':         get('ScoreA'),
        'ScoreB':         get('ScoreB'),
        'BluePicks':      blue_picks,
        'RedPicks':       red_picks,
        'BlueBans':       blue_bans,
        'RedBans':        red_bans,
        'ResultA':        result_a,
        'ResultB':        result_b,
        'Time':           get('Time'),
        'BlueDraftOrder': blue_draft,
        'RedDraftOrder':  red_draft,
        'SourceFile':     source_file,
        '_date_obj':      date_obj,  # hanya untuk sorting, tidak masuk output
    }

# ── DEDUPLICATION ─────────────────────────────────────────────────────────────
def dedup_key(row):
    """
    Fingerprint unik per game.
    Prioritas pembeda (dari paling spesifik ke paling umum):
    1. DateISO + teams + picks + bans  → game sama tanggal = duplikat
    2. Week + Day + Game + teams + picks + bans → game sama identifikator = duplikat
    3. picks + bans saja (fallback) → risiko false positive tapi tidak ada pilihan lain
    """
    def norm_set(s):
        return '|'.join(sorted(h.strip().lower() for h in s.split(';') if h.strip()))

    bp = norm_set(row['BluePicks'])
    rp = norm_set(row['RedPicks'])
    bb = norm_set(row['BlueBans'])
    rb = norm_set(row['RedBans'])
    teams = tuple(sorted([row['TeamA'].lower(), row['TeamB'].lower()]))
    picks_bans = (bp, rp, bb, rb)

    # Level 1: ada tanggal ISO yang valid → pakai tanggal sebagai pembeda utama
    date_iso = (row.get('DateISO') or '').strip()
    if date_iso:
        return ('date', date_iso, teams, picks_bans)

    # Level 2: ada Week + Game identifier → pakai sebagai pembeda
    week = (row.get('Week') or '').strip().lower()
    day  = (row.get('Day')  or '').strip().lower()
    game = (row.get('Game') or '').strip().lower()
    if week and game:
        return ('week', week, day, game, teams, picks_bans)

    # Level 3 fallback: hanya picks + bans (risiko false positive untuk game yg
    # kebetulan identik draft-nya tapi dimainkan di waktu berbeda)
    return ('noid', teams, picks_bans)

# ── MAIN PIPELINE ─────────────────────────────────────────────────────────────
def run_pipeline():
    print(f"\n{'='*60}")
    print("LQ DRAFT INTEL - Data Pipeline")
    print(f"{'='*60}")
    print(f"Folder CSV : {CSV_FOLDER}")
    print(f"Output     : {OUTPUT_FILE}")
    print()

    if not CSV_FOLDER.exists():
        print(f"ERROR: Folder tidak ditemukan: {CSV_FOLDER}")
        sys.exit(1)

    SIM_FILE = 'draft_simulator.csv'

    # Pisahkan file: scrape CSV (data utama) vs draft_simulator.csv (hanya draft order)
    all_csv = sorted([f for f in CSV_FOLDER.glob('*.csv') if f.name.lower() != 'master.csv'])
    scrape_files = [f for f in all_csv if f.name.lower() != SIM_FILE.lower()]
    sim_file     = next((f for f in all_csv if f.name.lower() == SIM_FILE.lower()), None)

    if not scrape_files and not sim_file:
        print("Tidak ada file CSV ditemukan di folder.")
        sys.exit(0)

    print(f"Sumber data utama  ({len(scrape_files)} file scrape):")
    for f in scrape_files:
        print(f"  - {f.name}")
    if sim_file:
        print(f"Draft order sumber : {sim_file.name} (hanya BlueDraftOrder/RedDraftOrder)")
    print()

    # ── PASS 1: Baca semua file SCRAPE sebagai data utama ─────────────────────────
    all_rows  = []
    seen_keys = {}
    stats     = {'total_read': 0, 'duplicates': 0, 'no_picks': 0, 'tbd': 0, 'files': {}}
    dup_log   = []

    for csv_path in scrape_files:
        file_rows = 0
        try:
            raw      = csv_path.read_bytes()
            encoding = 'utf-8-sig' if raw[:3] == b'\xef\xbb\xbf' else 'utf-8'
            try:    text = raw.decode(encoding)
            except: text = raw.decode('latin-1')

            reader = csv.reader(text.splitlines())
            rows   = list(reader)
            if not rows:
                continue

            header  = rows[0]
            col_map = map_cols(header)

            for raw_row in rows[1:]:
                if not any(c.strip() for c in raw_row):
                    continue
                stats['total_read'] += 1

                row = parse_row(raw_row, col_map, csv_path.name)

                if row['TeamA'].upper() == 'TBD' or row['TeamB'].upper() == 'TBD':
                    stats['tbd'] = stats.get('tbd', 0) + 1
                    continue

                if not row['BluePicks'] or not row['RedPicks']:
                    stats['no_picks'] += 1
                    continue

                key = dedup_key(row)
                if key in seen_keys:
                    stats['duplicates'] += 1
                    first_src = seen_keys[key]
                    if len(dup_log) < 30:
                        dup_log.append({
                            'teams':        f"{row['TeamA']} vs {row['TeamB']}",
                            'date':         row.get('DateISO') or row.get('Date') or '-',
                            'week':         f"W{row.get('Week','-')} D{row.get('Day','-')} G{row.get('Game','-')}",
                            'key_type':     key[0] if key else '?',
                            'current_file': csv_path.name,
                            'first_file':   first_src,
                        })
                    continue
                seen_keys[key] = csv_path.name

                all_rows.append(row)
                file_rows += 1

        except Exception as e:
            print(f"  [WARN] Error baca {csv_path.name}: {e}")
            continue

        stats['files'][csv_path.name] = file_rows
        print(f"  OK {csv_path.name}: {file_rows} game valid")

    print()

    if not all_rows and not sim_file:
        print("Tidak ada data valid yang ditemukan.")
        sys.exit(0)

    # Sort data scrape dulu
    def sort_key(row):
        d = row.get('_date_obj')
        if d:
            return (0, d, row.get('Week',''), row.get('Day',''), row.get('Game',''))
        return (1, date.max, row.get('Week',''), row.get('Day',''), row.get('Game',''))

    all_rows.sort(key=sort_key)

    # ── PASS 2: Baca draft_simulator.csv, ambil HANYA draft order ─────────────────
    # draft_simulator.csv TIDAK pernah jadi data standalone di master.csv.
    # Hanya BlueDraftOrder & RedDraftOrder yang diambil, lalu di-merge ke baris scrape
    # yang cocok berdasarkan picks+bans fingerprint (3 level matching).
    merged_count = 0
    sim_standalone = 0  # baris simulator yang tidak ada padanannya di scrape (diabaikan)

    def pb_fingerprint(bp, rp, bb, rb):
        """Fingerprint picks+bans saja (tanpa nama tim, tanpa tanggal)."""
        def ns(s): return '|'.join(sorted(h.strip().lower() for h in s.split(';') if h.strip()))
        # Canonical form: sort dua sisi supaya posisi terbalik juga cocok
        s1 = (ns(bp), ns(rp), ns(bb), ns(rb))
        s2 = (ns(rp), ns(bp), ns(rb), ns(bb))
        return min(s1, s2)

    if sim_file and all_rows:
        # Build index dari semua baris scrape: fingerprint → (index, is_blue_A)
        pb_index = {}
        for i, row in enumerate(all_rows):
            def ns(s): return '|'.join(sorted(h.strip().lower() for h in s.split(';') if h.strip()))
            fp = pb_fingerprint(row['BluePicks'], row['RedPicks'], row['BlueBans'], row['RedBans'])
            if fp not in pb_index:
                # Simpan apakah canonical = normal (True) atau terbalik (False)
                s1 = (ns(row['BluePicks']), ns(row['RedPicks']), ns(row['BlueBans']), ns(row['RedBans']))
                s2 = (ns(row['RedPicks']), ns(row['BluePicks']), ns(row['RedBans']), ns(row['BlueBans']))
                pb_index[fp] = {'idx': i, 'canonical_normal': (min(s1,s2)==s1)}

        # Baca simulator
        try:
            raw      = sim_file.read_bytes()
            encoding = 'utf-8-sig' if raw[:3] == b'\xef\xbb\xbf' else 'utf-8'
            try:    sim_text = raw.decode(encoding)
            except: sim_text = raw.decode('latin-1')

            sim_reader = csv.reader(sim_text.splitlines())
            sim_rows   = list(sim_reader)

            if len(sim_rows) > 1:
                sim_header  = sim_rows[0]
                sim_col_map = map_cols(sim_header)

                for raw_row in sim_rows[1:]:
                    if not any(c.strip() for c in raw_row):
                        continue
                    sim_row = parse_row(raw_row, sim_col_map, sim_file.name)

                    if not sim_row.get('BlueDraftOrder') and not sim_row.get('RedDraftOrder'):
                        continue  # tidak ada data draft order, skip

                    fp = pb_fingerprint(
                        sim_row.get('BluePicks',''), sim_row.get('RedPicks',''),
                        sim_row.get('BlueBans',''),  sim_row.get('RedBans','')
                    )

                    if fp in pb_index:
                        entry      = pb_index[fp]
                        scrape_row = all_rows[entry['idx']]

                        # Tentukan apakah Blue di simulator = Blue di scrape atau terbalik
                        def ns2(s): return '|'.join(sorted(h.strip().lower() for h in s.split(';') if h.strip()))
                        sim_s1 = (ns2(sim_row.get('BluePicks','')), ns2(sim_row.get('RedPicks','')),
                                  ns2(sim_row.get('BlueBans','')),  ns2(sim_row.get('RedBans','')))
                        scr_s1 = (ns2(scrape_row['BluePicks']), ns2(scrape_row['RedPicks']),
                                  ns2(scrape_row['BlueBans']),  ns2(scrape_row['RedBans']))
                        same_side = (sim_s1 == scr_s1)

                        if same_side:
                            # Posisi sama: Blue sim = Blue scrape
                            if sim_row.get('BlueDraftOrder') and not scrape_row.get('BlueDraftOrder'):
                                scrape_row['BlueDraftOrder'] = sim_row['BlueDraftOrder']
                            if sim_row.get('RedDraftOrder') and not scrape_row.get('RedDraftOrder'):
                                scrape_row['RedDraftOrder']  = sim_row['RedDraftOrder']
                        else:
                            # Posisi terbalik: Blue sim = Red scrape
                            if sim_row.get('BlueDraftOrder') and not scrape_row.get('RedDraftOrder'):
                                scrape_row['RedDraftOrder']  = sim_row['BlueDraftOrder']
                            if sim_row.get('RedDraftOrder') and not scrape_row.get('BlueDraftOrder'):
                                scrape_row['BlueDraftOrder'] = sim_row['RedDraftOrder']
                        merged_count += 1
                    else:
                        sim_standalone += 1

        except Exception as e:
            print(f"  [WARN] Error baca {sim_file.name}: {e}")

        print(f"  [Draft Order] {merged_count} baris simulator di-merge ke data scrape")
        if sim_standalone > 0:
            print(f"  [Draft Order] {sim_standalone} baris simulator tidak ada padanan di scrape (diabaikan)")

    # Tulis master.csv
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=MASTER_COLS, extrasaction='ignore')
        writer.writeheader()
        for row in all_rows:
            row.pop('_date_obj', None)
            writer.writerow(row)

    print(f"{'='*60}")
    print(f"HASIL PIPELINE")
    print(f"{'='*60}")
    print(f"Total dibaca    : {stats['total_read']} baris (dari {len(scrape_files)} file scrape)")
    print(f"TBD dilewati    : {stats.get('tbd',0)}")
    print(f"Tanpa picks     : {stats['no_picks']} (dilewati)")
    print(f"Duplikat dihapus: {stats['duplicates']}")
    print(f"Draft order merged: {merged_count} game diperkaya dari simulator")
    print(f"Game valid      : {len(all_rows)}")
    print(f"Output          : {OUTPUT_FILE}")

    # ── LAPORAN DUPLIKAT ──────────────────────────────────────────────────────
    if dup_log:
        print(f"\n{'='*60}")
        print(f"LAPORAN DUPLIKAT (sample {len(dup_log)} dari {stats['duplicates']})")
        print(f"{'='*60}")

        # Analisa: duplikat per pasangan file
        from collections import Counter
        pair_counts = Counter()
        for d in dup_log:
            pair = tuple(sorted([d['current_file'], d['first_file']]))
            pair_counts[pair] += 1

        print("\nPasangan file dengan duplikat terbanyak:")
        for (f1, f2), count in pair_counts.most_common(5):
            if f1 == f2:
                print(f"  {count}x  [{f1}] dengan dirinya sendiri (baris duplikat dalam satu file)")
            else:
                print(f"  {count}x  [{f1}] vs [{f2}]")

        # Cek apakah ada yang pakai fallback key (risiko false positive)
        fallback = [d for d in dup_log if d['key_type'] == 'noid']
        if fallback:
            print(f"\n[WARN] {len(fallback)} duplikat pakai fingerprint fallback (tanpa tanggal/week)")
            print("  -> Ini MUNGKIN adalah game berbeda yang kebetulan picks+bans-nya sama!")
            print("  -> Contoh:")
            for d in fallback[:3]:
                print(f"     {d['teams']} | {d['current_file']}")
                print(f"       first seen: {d['first_file']}")
        else:
            print("\nOK - Semua duplikat punya identifier (tanggal/week) yang valid.")
            print("   Tidak ada risiko false positive dari game berbeda.")

        print(f"\nContoh 5 duplikat pertama:")
        for d in dup_log[:5]:
            print(f"  {d['teams']} | {d['date']} {d['week']}")
            print(f"    File saat ini : {d['current_file']}")
            print(f"    Sudah ada dari: {d['first_file']}")
            print(f"    Fingerprint   : {d['key_type']}")

    print(f"\nOK Pipeline selesai - {len(all_rows)} game di master.csv")
    print()

    return len(all_rows)

if __name__ == '__main__':
    run_pipeline()
