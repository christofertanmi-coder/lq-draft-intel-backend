// nim-proxy.js — LQ DRAFT INTEL
// Fungsi 1: Proxy ke NVIDIA NIM API (AI Summary)
// Fungsi 2: Simpan/baca draft simulator ke Supabase (tabel `drafts`)
// Fungsi 3: Auto-serve hero images ke browser (lokal)
// Fungsi 4: File watcher — deteksi perubahan CSV lokal untuk auto-refresh browser & auto-run pipeline
// Fungsi 5: Serve master.csv dari Supabase (tabel `matches_master`)
// Cara pakai (lokal): node nim-proxy.js  |  Default http://localhost:8787
// Di Render: environment variables SUPABASE_URL, SUPABASE_SERVICE_KEY, API_TOKEN, PORT diisi lewat dashboard.

require('dotenv').config();

const http  = require('http');
const https = require('https');
const fs    = require('fs');
const path  = require('path');
const { exec } = require('child_process');
const { createClient } = require('@supabase/supabase-js');

const PORT       = process.env.PORT || 8787;
const NIM_HOST   = 'integrate.api.nvidia.com';
const CONFIG_PATH = path.join(__dirname, 'lq_config.json');
const API_TOKEN  = process.env.API_TOKEN || '';

const supabase = (process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_KEY)
  ? createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_KEY)
  : null;

// ── CONFIG ─────────────────────────────────────────────────────
function loadConfig(){
  try { return JSON.parse(fs.readFileSync(CONFIG_PATH,'utf8')); } catch(e){ return {}; }
}
function saveConfig(cfg){
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2), 'utf8');
}

function getPipelinePath(){ return path.join(__dirname, 'pipeline.py'); }

// Backup master.csv sebelum pipeline.py meng-overwrite-nya — insurance murah supaya
// data tidak pernah hilang tanpa jejak.
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

// ── FILE WATCHER (auto-refresh + auto-run pipeline saat CSV scrape berubah) ──
let lastChange = Date.now();
let activeWatcher = null;

function runPipelineThenUpload(reason){
  const pipelinePath = getPipelinePath();
  if(!fs.existsSync(pipelinePath)) return;
  const pythonCmd = process.platform==='win32' ? 'python' : 'python3';
  console.log(`[Pipeline] Auto-run (${reason})`);
  backupMasterCsv();
  exec(`${pythonCmd} "${pipelinePath}"`, {timeout:60000}, (err, stdout, stderr)=>{
    if(err){ console.error('[Pipeline] Error:', err.message); return; }
    console.log('[Pipeline] Selesai.');
    lastChange = Date.now();
    exec(`${pythonCmd} "${path.join(__dirname,'upload_master.py')}"`, {timeout:60000}, (e2, so2, se2)=>{
      if(e2){ console.error('[Upload master] Error:', e2.message); return; }
      console.log('[Upload master] master.csv terupload ke Supabase.');
    });
  });
}

function startWatcher(folder){
  if(activeWatcher){ try{ activeWatcher.close(); }catch(e){} activeWatcher=null; }
  if(!folder || !fs.existsSync(folder)) return;
  try{
    activeWatcher = fs.watch(folder, {persistent:false}, (eventType, filename)=>{
      if(filename && /\.csv$/i.test(filename)){
        lastChange = Date.now();
        console.log(`[Watcher] Perubahan terdeteksi: ${filename} (${new Date().toLocaleTimeString()})`);
      }
    });
    console.log(`✓ File watcher aktif di: ${folder}`);
  }catch(e){ console.error('⚠ Gagal start watcher:', e.message); }
}

setTimeout(()=>{
  const cfg = loadConfig();
  if(cfg.csvFolder) startWatcher(cfg.csvFolder);
}, 500);

// ── HELPERS ────────────────────────────────────────────────────
function sendJSON(res, status, obj){
  const body = JSON.stringify(obj);
  res.writeHead(status, {
    'Content-Type':'application/json',
    'Access-Control-Allow-Origin':'*',
    'Access-Control-Allow-Methods':'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers':'Content-Type,X-Api-Token'
  });
  res.end(body);
}

function corsHeaders(){
  return {'Access-Control-Allow-Origin':'*','Access-Control-Allow-Methods':'GET,POST,OPTIONS','Access-Control-Allow-Headers':'Content-Type,X-Api-Token'};
}

function requireToken(req, res){
  if(!API_TOKEN) return true; // token belum diset (lokal dev) — lewatkan
  const supplied = req.headers['x-api-token'];
  if(supplied !== API_TOKEN){
    sendJSON(res, 401, {error:'Unauthorized: X-Api-Token salah/hilang'});
    return false;
  }
  return true;
}

function arr(v){
  if(Array.isArray(v)) return v.map(x=>String(x).trim()).filter(Boolean);
  if(typeof v==='string') return v.split(';').map(s=>s.trim()).filter(Boolean);
  return [];
}

function forwardToNim(urlPath, method, apiKey, payload, res){
  const data = payload ? JSON.stringify(payload) : null;
  const req = https.request({
    hostname:NIM_HOST, path:urlPath, method,
    headers:{
      'Authorization':'Bearer '+apiKey, 'Accept':'application/json',
      ...(data?{'Content-Type':'application/json','Content-Length':Buffer.byteLength(data)}:{})
    }
  }, nimRes=>{
    let chunks=[];
    nimRes.on('data',c=>chunks.push(c));
    nimRes.on('end',()=>{
      const raw=Buffer.concat(chunks).toString('utf8');
      res.writeHead(nimRes.statusCode,{'Content-Type':'application/json','Access-Control-Allow-Origin':'*'});
      res.end(raw);
    });
  });
  req.on('error',err=>sendJSON(res,502,{error:'Gagal ke NVIDIA NIM: '+err.message}));
  if(data) req.write(data);
  req.end();
}

// ── SERVER ─────────────────────────────────────────────────────
const server = http.createServer((req, res)=>{
  if(req.method==='OPTIONS'){ res.writeHead(204,corsHeaders()); return res.end(); }

  let body='';
  req.on('data',chunk=>body+=chunk);
  req.on('end', async ()=>{
    let parsed={};
    try{ parsed=body?JSON.parse(body):{}; }catch(e){ return sendJSON(res,400,{error:'Body bukan JSON valid'}); }

    // ── NVIDIA NIM ──
    if(req.url==='/models'&&req.method==='POST'){
      if(!parsed.apiKey) return sendJSON(res,400,{error:'apiKey wajib'});
      return forwardToNim('/v1/models','GET',parsed.apiKey,null,res);
    }
    if(req.url==='/chat'&&req.method==='POST'){
      if(!parsed.apiKey||!parsed.model||!parsed.messages) return sendJSON(res,400,{error:'apiKey/model/messages wajib'});
      return forwardToNim('/v1/chat/completions','POST',parsed.apiKey,
        {model:parsed.model,messages:parsed.messages,temperature:0.25,max_tokens:1024,stream:false},res);
    }

    // ── CONFIG (lokal only) ──
    if(req.url==='/get-config'&&req.method==='POST'){
      return sendJSON(res,200,loadConfig());
    }
    if(req.url==='/save-config'&&req.method==='POST'){
      try{
        const cfg=loadConfig();
        if(parsed.csvFolder!==undefined) cfg.csvFolder=parsed.csvFolder;
        if(parsed.heroFolder!==undefined) cfg.heroFolder=parsed.heroFolder;
        saveConfig(cfg);
        if(cfg.csvFolder) startWatcher(cfg.csvFolder);
        return sendJSON(res,200,{ok:true,config:cfg});
      }catch(e){ return sendJSON(res,500,{error:e.message}); }
    }

    // ── POLL CHANGES (auto-refresh browser) ──
    if(req.url==='/poll-changes'&&req.method==='POST'){
      const clientLast = parsed.lastChange || 0;
      return sendJSON(res,200,{ lastChange, hasChange: lastChange > clientLast, serverTime: Date.now() });
    }

    // ── HERO IMAGES (Supabase Storage — public bucket, sama untuk PC & HP) ──
    if(req.url==='/list-heroes'&&req.method==='POST'){
      if(!supabase) return sendJSON(res,500,{error:'Supabase belum dikonfigurasi'});
      try{
        const { data, error } = await supabase.storage.from('hero-images').list('', { limit: 1000, sortBy: { column: 'name', order: 'asc' } });
        if(error) return sendJSON(res,500,{error:'Gagal list hero images: '+error.message});
        const files = (data||[])
          .filter(f=>/\.(png|jpg|jpeg|webp)$/i.test(f.name))
          .map(f=>({ name:f.name, url: supabase.storage.from('hero-images').getPublicUrl(f.name).data.publicUrl }));
        return sendJSON(res,200,{files});
      }catch(e){ return sendJSON(res,500,{error:e.message}); }
    }
    // /serve-hero dipertahankan untuk kompatibilitas mundur — cukup redirect ke public URL Supabase.
    if(req.url==='/serve-hero'&&req.method==='POST'){
      if(!parsed.fileName && !parsed.filePath) return sendJSON(res,400,{error:'fileName wajib'});
      if(!supabase) return sendJSON(res,500,{error:'Supabase belum dikonfigurasi'});
      const name = parsed.fileName || path.basename(parsed.filePath);
      const { data } = supabase.storage.from('hero-images').getPublicUrl(name);
      res.writeHead(302, { Location: data.publicUrl, 'Access-Control-Allow-Origin':'*' });
      return res.end();
    }

    // ── DRAFT: SAVE (Supabase) ──
    if(req.url==='/save-draft'&&req.method==='POST'){
      if(!requireToken(req,res)) return;
      if(!supabase) return sendJSON(res,500,{error:'Supabase belum dikonfigurasi'});
      try{
        const d=parsed;
        if(!d.teamA||!d.teamB) return sendJSON(res,400,{error:'teamA dan teamB wajib'});
        const { data, error } = await supabase.from('drafts').insert({
          week: d.week||'', day: d.day||'', game: d.game||'',
          date: d.date||new Date().toISOString().slice(0,10),
          team_a: d.teamA, team_b: d.teamB,
          blue_picks: arr(d.bluePicks), red_picks: arr(d.redPicks),
          blue_bans: arr(d.blueBans), red_bans: arr(d.redBans),
          winner: d.winner||'', time: d.duration||'',
          result_a: d.winner===d.teamA?'W':d.winner===d.teamB?'L':'',
          result_b: d.winner===d.teamB?'W':d.winner===d.teamA?'L':'',
          blue_draft_order: arr(d.blueDraftOrder), red_draft_order: arr(d.redDraftOrder),
          blue_ban_order: arr(d.blueBans), red_ban_order: arr(d.redBans),
          blue_pick_roles: arr(d.bluePickRoles), red_pick_roles: arr(d.redPickRoles),
        }).select().single();
        if(error) return sendJSON(res,500,{error:'Gagal simpan: '+error.message});
        console.log(`[Draft saved] ${d.teamA} vs ${d.teamB} | Winner: ${d.winner||'TBD'}`);
        return sendJSON(res,200,{ok:true,id:data.id});
      }catch(e){ return sendJSON(res,500,{error:'Gagal simpan: '+e.message}); }
    }

    // ── DRAFT: READ (Supabase) ──
    if(req.url==='/read-drafts'&&req.method==='POST'){
      if(!supabase) return sendJSON(res,500,{error:'Supabase belum dikonfigurasi'});
      try{
        const PAGE = 1000;
        let all = [], from = 0;
        while(true){
          const { data, error } = await supabase.from('drafts').select('*')
            .order('id',{ascending:true}).range(from, from+PAGE-1);
          if(error) return sendJSON(res,500,{error:'Gagal baca: '+error.message});
          all = all.concat(data);
          if(data.length < PAGE) break;
          from += PAGE;
        }
        return sendJSON(res,200,{drafts:all});
      }catch(e){ return sendJSON(res,500,{error:'Gagal baca: '+e.message}); }
    }

    // ── DRAFT: DELETE (Supabase, by id) ──
    if(req.url==='/delete-draft'&&req.method==='POST'){
      if(!requireToken(req,res)) return;
      if(!supabase) return sendJSON(res,500,{error:'Supabase belum dikonfigurasi'});
      try{
        const { id } = parsed;
        if(!id) return sendJSON(res,400,{error:'id wajib'});
        const { error } = await supabase.from('drafts').delete().eq('id', id);
        if(error) return sendJSON(res,500,{error:'Gagal hapus: '+error.message});
        console.log(`[Draft deleted] id=${id}`);
        return sendJSON(res,200,{ok:true});
      }catch(e){ return sendJSON(res,500,{error:'Gagal hapus: '+e.message}); }
    }

    // ── DRAFT: UPDATE RESULT (Supabase, by id) ──
    if(req.url==='/update-result'&&req.method==='POST'){
      if(!requireToken(req,res)) return;
      if(!supabase) return sendJSON(res,500,{error:'Supabase belum dikonfigurasi'});
      try{
        const d=parsed;
        if(!d.id) return sendJSON(res,400,{error:'id wajib'});
        const patch={};
        if(d.winner!==undefined){
          patch.winner=d.winner;
          patch.result_a = d.winner===d.teamA?'W':d.winner===d.teamB?'L':'';
          patch.result_b = d.winner===d.teamB?'W':d.winner===d.teamA?'L':'';
        }
        if(d.duration!==undefined) patch.time=d.duration;
        if(d.bluePicks!==undefined) patch.blue_picks=arr(d.bluePicks);
        if(d.redPicks!==undefined) patch.red_picks=arr(d.redPicks);
        if(d.blueBans!==undefined) patch.blue_bans=arr(d.blueBans);
        if(d.redBans!==undefined) patch.red_bans=arr(d.redBans);
        if(d.bluePickRoles!==undefined) patch.blue_pick_roles=arr(d.bluePickRoles);
        if(d.redPickRoles!==undefined) patch.red_pick_roles=arr(d.redPickRoles);
        const { error } = await supabase.from('drafts').update(patch).eq('id', d.id);
        if(error) return sendJSON(res,500,{error:'Gagal update: '+error.message});
        return sendJSON(res,200,{ok:true,updated:true});
      }catch(e){ return sendJSON(res,500,{error:'Gagal update: '+e.message}); }
    }

    // ── PIPELINE: JALANKAN pipeline.py manual (tetap lokal only) ──
    if(req.url==='/run-pipeline'&&req.method==='POST'){
      const pipelinePath = getPipelinePath();
      if(!fs.existsSync(pipelinePath)) return sendJSON(res,404,{error:'pipeline.py tidak ditemukan di: '+pipelinePath});
      const pythonCmd = process.platform==='win32' ? 'python' : 'python3';
      const cmd = `${pythonCmd} "${pipelinePath}"`;
      console.log(`[Pipeline] Menjalankan: ${cmd}`);
      backupMasterCsv();
      exec(cmd, {timeout: 60000}, (err, stdout, stderr)=>{
        if(err){
          console.error('[Pipeline] Error:', err.message);
          return sendJSON(res, 500, {ok:false, error: err.message, stdout, stderr});
        }
        console.log('[Pipeline] Selesai:\n'+stdout);
        lastChange = Date.now();
        return sendJSON(res, 200, {ok:true, stdout, stderr});
      });
      return;
    }

    // ── PIPELINE: SERVE master.csv (Supabase) ──
    if(req.url==='/serve-master'&&req.method==='POST'){
      if(!supabase) return sendJSON(res,500,{error:'Supabase belum dikonfigurasi'});
      try{
        // Supabase/PostgREST membatasi max 1000 baris per request secara default —
        // paginate pakai .range() supaya semua baris (bisa >1000) ikut terambil.
        const PAGE = 1000;
        let all = [], from = 0;
        while(true){
          const { data, error } = await supabase.from('matches_master').select('*')
            .order('id',{ascending:true}).range(from, from+PAGE-1);
          if(error) return sendJSON(res,500,{error:'Gagal baca master: '+error.message});
          all = all.concat(data);
          if(data.length < PAGE) break;
          from += PAGE;
        }
        return sendJSON(res,200,{matches:all});
      }catch(e){ return sendJSON(res,500,{error:'Gagal baca master: '+e.message}); }
    }

    sendJSON(res,404,{error:'Endpoint tidak dikenal.'});
  });
});

server.listen(PORT,()=>{
  const cfg=loadConfig();
  console.log(`\n✓ LQ DRAFT INTEL Proxy jalan di port ${PORT}`);
  console.log(`  CSV folder  : ${cfg.csvFolder||'(belum dikonfigurasi)'}`);
  console.log(`  Hero folder : ${cfg.heroFolder||'(belum dikonfigurasi)'}`);
  console.log(`  Supabase    : ${supabase ? 'terhubung' : 'BELUM dikonfigurasi (cek .env)'}`);
  console.log(`  API token   : ${API_TOKEN ? 'aktif' : 'TIDAK ADA (endpoint tulis terbuka publik!)'}`);
  console.log('  Biarkan terminal ini terbuka. Ctrl+C untuk berhenti.\n');
});

module.exports = { runPipelineThenUpload };
