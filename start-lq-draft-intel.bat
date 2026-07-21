@echo off
title LQ DRAFT INTEL - Launcher
cd /d "%~dp0"

echo ============================================
echo   LQ DRAFT INTEL - Starting...
echo ============================================

where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js tidak ditemukan. Install dulu dari https://nodejs.org
    pause
    exit /b 1
)

echo [1/3] Menjalankan proxy server (nim-proxy.js) di port 8787...
start "LQ Proxy Server" cmd /k node nim-proxy.js

echo [2/3] Menjalankan orchestrator (pipeline otomatis + sync Supabase)...
start "LQ Orchestrator" cmd /k node orchestrator.js

echo [3/3] Menunggu server siap...
timeout /t 2 /nobreak >nul

echo Membuka dashboard di browser...
start "" "lq-draft-intel-v2.html"

echo Selesai. Jangan tutup jendela "LQ Proxy Server" dan "LQ Orchestrator" selama pakai dashboard.
