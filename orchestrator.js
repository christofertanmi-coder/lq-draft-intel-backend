// orchestrator.js — LQ DRAFT INTEL
// Jalan terus di PC selama sesi draft. Tugas:
//  1. Pantau folder CSV scrape lokal -> trigger sinkronisasi penuh saat ada file berubah.
//  2. Polling Supabase (tabel `drafts`) tiap POLL_INTERVAL_MS -> trigger sinkronisasi penuh
//     kalau ada draft baru.
//  Kedua trigger di atas menjalankan runFullSync() yang SAMA: download_drafts.py (tarik draft
//  terbaru dari Supabase) -> pipeline.py (gabung ke master.csv) -> upload_master.py (kirim
//  balik ke Supabase). Disatukan supaya tidak ada celah — sebelumnya file-watcher pakai jalur
//  terpisah yang skip langkah tarik draft, jadi draft baru bisa ketinggalan kalau yang trigger
//  duluan adalah perubahan file CSV scrape, bukan polling draft baru.
//
// Cara pakai: node orchestrator.js

require('dotenv').config();

const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');
const { createClient } = require('@supabase/supabase-js');

const POLL_INTERVAL_MS = 2 * 60 * 1000; // 2 menit, sesuai keputusan user
const CONFIG_PATH = path.join(__dirname, 'lq_config.json');
const PYTHON_CMD = process.platform === 'win32' ? 'python' : 'python3';

function loadConfig(){
  try { return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8')); } catch(e){ return {}; }
}

// Backup master.csv sebelum pipeline.py meng-overwrite-nya — insurance murah supaya
// data tidak pernah hilang tanpa jejak (pelajaran dari draft_simulator.csv yang ke-overwrite).
function backupMasterCsv(){
  const cfg = loadConfig();
  const folder = cfg.csvFolder;
  if(!folder) return;
  const masterPath = path.join(folder, 'master.csv');
  if(!fs.existsSync(masterPath)) return;
  if(fs.statSync(masterPath).size === 0) return;
  const backupDir = path.join(folder, '_backups');
  if(!fs.existsSync(backupDir)) fs.mkdirSync(backupDir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g,'-');
  const dest = path.join(backupDir, `master_${stamp}.csv`);
  fs.copyFileSync(masterPath, dest);
  console.log(`[Backup] master.csv -> ${dest}`);
}

const supabase = (process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_KEY)
  ? createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_KEY)
  : null;

if(!supabase){
  console.error('ERROR: SUPABASE_URL / SUPABASE_SERVICE_KEY belum diset (cek .env). Orchestrator berhenti.');
  process.exit(1);
}

let running = false; // mutex sederhana supaya tidak overlap

function runCmd(cmd){
  return new Promise((resolve, reject)=>{
    exec(cmd, { timeout: 120000, cwd: __dirname }, (err, stdout, stderr)=>{
      if(err) return reject(new Error(`${cmd} gagal: ${err.message}\n${stderr}`));
      resolve(stdout);
    });
  });
}

// Satu jalur sinkronisasi penuh dipakai oleh KEDUA trigger (file watcher maupun polling
// draft baru) — supaya tidak ada celah lagi seperti sebelumnya (file-watcher sempat skip
// langkah tarik draft terbaru dari Supabase karena pakai jalur terpisah).
async function runFullSync(reason){
  if(running){
    console.log(`[Orchestrator] Skip (${reason}) - masih ada proses berjalan.`);
    return;
  }
  running = true;
  console.log(`[Orchestrator] Trigger: ${reason}`);
  try{
    await runCmd(`${PYTHON_CMD} "${path.join(__dirname,'download_drafts.py')}"`);
    console.log('[Orchestrator] download_drafts.py selesai.');
    backupMasterCsv();
    await runCmd(`${PYTHON_CMD} "${path.join(__dirname,'pipeline.py')}"`);
    console.log('[Orchestrator] pipeline.py selesai.');
    await runCmd(`${PYTHON_CMD} "${path.join(__dirname,'upload_master.py')}"`);
    console.log('[Orchestrator] upload_master.py selesai. master.csv sinkron ke Supabase.');
  }catch(e){
    console.error('[Orchestrator] ERROR:', e.message);
  }finally{
    running = false;
  }
}

// ── 1. Watcher folder CSV lokal ──────────────────────────────────
let debounceTimer = null;
function startFileWatcher(folder){
  if(!folder || !fs.existsSync(folder)){
    console.log('[Orchestrator] csvFolder belum dikonfigurasi / tidak ditemukan, watcher tidak aktif.');
    return;
  }
  fs.watch(folder, { persistent: true }, (eventType, filename)=>{
    if(!filename || !/\.csv$/i.test(filename)) return;
    if(filename.toLowerCase() === 'draft_simulator.csv') return; // itu ditangani oleh polling Supabase, hindari loop
    if(filename.toLowerCase() === 'master.csv') return; // output, bukan input
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(()=>{
      runFullSync(`file berubah: ${filename}`);
    }, 3000); // debounce 3s biar tidak trigger berkali-kali saat file masih ditulis
  });
  console.log(`[Orchestrator] Watcher CSV aktif di: ${folder}`);
}

// ── 2. Polling Supabase drafts ───────────────────────────────────
let lastKnownMaxId = 0;

async function pollDrafts(){
  try{
    const { data, error } = await supabase
      .from('drafts')
      .select('id')
      .order('id', { ascending: false })
      .limit(1);
    if(error){ console.error('[Orchestrator] Poll error:', error.message); return; }
    const currentMaxId = (data && data[0]) ? data[0].id : 0;
    if(currentMaxId > lastKnownMaxId){
      const isFirstRun = lastKnownMaxId === 0;
      lastKnownMaxId = currentMaxId;
      if(!isFirstRun){
        await runFullSync(`draft baru terdeteksi (id ${currentMaxId})`);
      }
    }
  }catch(e){
    console.error('[Orchestrator] Poll exception:', e.message);
  }
}

// ── MAIN ──────────────────────────────────────────────────────────
async function main(){
  console.log('='.repeat(60));
  console.log('LQ DRAFT INTEL — Orchestrator');
  console.log('='.repeat(60));
  console.log(`Polling interval: ${POLL_INTERVAL_MS / 1000}s`);

  const cfg = loadConfig();
  startFileWatcher(cfg.csvFolder);

  // Inisialisasi lastKnownMaxId tanpa trigger run (baseline)
  await pollDrafts();
  console.log(`Baseline draft id: ${lastKnownMaxId}`);

  setInterval(pollDrafts, POLL_INTERVAL_MS);
  console.log('Orchestrator berjalan. Ctrl+C untuk berhenti.\n');
}

main();
