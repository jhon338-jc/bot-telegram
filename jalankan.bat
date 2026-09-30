@echo off
title Telegram Userbot
cd /d "%~dp0"
chcp 65001 >nul

if not exist "venv\Scripts\activate.bat" (
  echo VENV BELUM ADA. Jalankan sekali:
  echo   python -m venv venv
  echo   venv\Scripts\activate
  echo   pip install -r requirements.txt
  pause
  exit /b 1
)

call venv\Scripts\activate.bat
set PYTHONUTF8=1

echo ============================================
echo   Telegram Userbot - akun asli (Telethon)
echo ============================================
echo   1. Cek konfigurasi   (belum perlu konek)
echo   2. Login cepat QR    (pertama kali, tanpa OTP)
echo   3. Login kode OTP     (pertama kali)
echo   4. Jalankan userbot
echo   5. Reset session     (login ulang dari nol)
echo.
set /p PILIH=Silakan pilih (1-5):

if "%PILIH%"=="1" python main.py --cek
if "%PILIH%"=="2" python main.py --qr
if "%PILIH%"=="3" python main.py
if "%PILIH%"=="4" python main.py
if "%PILIH%"=="5" python main.py --reset

echo.
echo Program berhenti. Jendela ini akan ditutup dalam 5 detik...
timeout /t 5 >nul
