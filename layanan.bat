@echo off
title Kelola Userbot Telegram (service)
cd /d "%~dp0"
chcp 65001 >nul

if not exist "venv\Scripts\pythonw.exe" (
  echo VENV BELUM ADA. Jalankan sekali:
  echo   python -m venv venv
  echo   venv\Scripts\activate
  echo   pip install -r requirements.txt
  pause
  exit /b 1
)

echo ============================================
echo   Userbot Telegram - Service Background
echo ============================================
echo   1. Install  - daftar autostart + jalan sekarang
echo   2. Start    - jalankan
echo   3. Stop     - hentikan
echo   4. Restart  - stop lalu start
echo   5. Status   - cek task + log
echo   6. Uninstall- hapus autostart
echo.
set /p PILIH=Pilih (1-6, Enter=1):

if "%PILIH%"=="" set PILIH=1
set AKSI=install
if "%PILIH%"=="2" set AKSI=start
if "%PILIH%"=="3" set AKSI=stop
if "%PILIH%"=="4" set AKSI=restart
if "%PILIH%"=="5" set AKSI=status
if "%PILIH%"=="6" set AKSI=uninstall

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0service.ps1" %AKSI%

echo.
pause
