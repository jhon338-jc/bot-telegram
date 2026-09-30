"""Supervisor userbot: menjaga ``main.py`` tetap hidup di belakang layar.

Userbot ini dijalankan tanpa jendela console (``pythonw.exe``) supaya tidak
muncul cmd di tengah layar. Masalahnya, begitu tidak ada console, proses
yang mati tidak terlihat dan tidak ada yang memulihkannya. Modul ini
menjadi perisai: ``main.py`` dijalankan sebagai child process, dan setiap
kali child berhenti (crash, koneksi putus, ``Ctrl+C``) supervisor
menjalankannya lagi dengan jeda yang bertambah naik.

Registrasi ke Task Scheduler (agar otomatis hidup saat login) dilakukan
lewat ``service.ps1``, bukan lewat modul ini.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if os.name == "nt":
    os.chdir(BASE_DIR)

# Flag yang dibaca supervisor, dan lock file yang mencegah dua supervisor
# berjalan bersamaan (keduanya akan berebut file session SQLite).
STOP_FLAG = BASE_DIR / "data" / "stop.flag"
LOCK_FILE = BASE_DIR / "data" / "server.lock"
LOG_FILE = BASE_DIR / "logs" / "server.log"

PYTHON = BASE_DIR / "venv" / "Scripts" / ("pythonw.exe" if os.name == "nt" else "python")
MAIN = BASE_DIR / "main.py"

# Jeda antar percobaan restart. Naik sampai maksimum supaya bot yang
# memang rusak tidak memakai CPU dan kuota jaringan tanpa henti.
BACKOFF_AWAL = 2.0
BACKOFF_MAKS = 60.0
# Kalau child hidup lebih lama dari ini, dianggap sehat: jeda restart
# di-reset supaya masalah sesaat tidak menghasilkan jeda 60 detik.
SEHAT_SETELAH = 60.0


def log(pesan: str) -> None:
    """Tulis satu baris ke ``logs/server.log``.

    Args:
        pesan: Isi pesan tanpa stempel waktu.
    """
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    stempel = datetime.now().astimezone().isoformat(timespec="seconds")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{stempel} | {pesan}\n")


def ambil_lock() -> object | None:
    """Kunci file agar hanya ada satu supervisor aktif.

    Project ini dijalankan di Windows, jadi pengunci memakai ``msvcrt``.
    Di platform lain fungsi ini mengembalikan handle tanpa penguncian.

    Returns:
        File handle yang terkunci, atau ``None`` bila sudah ada supervisor
        lain yang berjalan.
    """
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    f = LOCK_FILE.open("a+")
    if os.name != "nt":
        f.seek(0)
        f.truncate()
        f.write(str(os.getpid()))
        f.flush()
        return f

    import msvcrt

    f.seek(0)
    try:
        # Byte 0 dikunci sebagai penanda "sudah ada supervisor lain".
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        f.close()
        return None
    try:
        # PID ditulis mulai byte 1, di luar rentang yang terkunci.
        f.seek(1)
        f.truncate()
        f.write(str(os.getpid()))
        f.flush()
    except OSError:
        pass
    return f


def minta_stop() -> None:
    """Tandai supervisor supaya berhenti setelah child selesai."""
    STOP_FLAG.parent.mkdir(parents=True, exist_ok=True)
    STOP_FLAG.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")


def stop_diminta() -> bool:
    """Periksa apakah ada permintaan berhenti.

    Returns:
        ``True`` bila file ``stop.flag`` ada.
    """
    return STOP_FLAG.exists()


def bersihkan_stop() -> None:
    """Hapus file ``stop.flag`` sebelum supervisor dijalankan lagi."""
    STOP_FLAG.unlink(missing_ok=True)


def flags_jendela() -> int:
    """Buat subprocess tanpa jendela console.

    Returns:
        Flag creations untuk Windows, atau ``0`` di platform lain.
    """
    if os.name != "nt":
        return 0
    return (
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )


def hentikan(child: subprocess.Popen) -> None:
    """Akhiri child dengan rapi, paksa kalau tidak mau complies.

    Args:
        child: Proses ``main.py`` yang sedang berjalan.
    """
    child.terminate()
    try:
        child.wait(timeout=15)
    except subprocess.TimeoutExpired:
        log("Child tidak Mau berhenti, dipaksa (kill).")
        child.kill()


def jalankan_sekali() -> tuple[int, float]:
    """Jalankan ``main.py`` sekali dan tunggu sampai selesai.

    Selama menunggu, file ``stop.flag`` dipantau setiap detik supaya
    ``server.py stop`` benar-benar menghentikan child yang sedang aktif,
    bukan hanya menahan restart berikutnya.

    Returns:
        Tuple ``(exit_code, durasi_detik)``. Exit code ``-1`` berarti
        child gagal dijalankan sama sekali.
    """
    if not MAIN.exists():
        log(f"FATAL: {MAIN} tidak ditemukan.")
        return -1, 0.0
    try:
        child = subprocess.Popen(
            [str(PYTHON), str(MAIN)],
            cwd=str(BASE_DIR),
            creationflags=flags_jendela(),
        )
    except OSError as exc:
        log(f"Gagal menjalankan main.py: {exc}")
        return -1, 0.0

    mulai = time.monotonic()
    log(f"Menjalankan main.py (PID {child.pid}).")
    try:
        while True:
            try:
                kode = child.wait(timeout=1)
                return kode, time.monotonic() - mulai
            except subprocess.TimeoutExpired:
                pass
            if stop_diminta():
                log("Permintaan stop saat child berjalan, child dihentikan.")
                hentikan(child)
                kode = child.returncode if child.returncode is not None else 0
                return kode, time.monotonic() - mulai
    except KeyboardInterrupt:
        # Ctrl+C di console supervisor diteruskan ke child, lalu supervisor
        # ikut berhenti (tidak ada restart).
        log("Ctrl+C diterima, meneruskan ke main.py lalu berhenti.")
        hentikan(child)
        return 0, time.monotonic() - mulai


def supervise() -> int:
    """Jalankan ``main.py`` berulang kali selama belum diminta berhenti.

    Returns:
        Exit code supervisor (``0`` bila berhenti normal).
    """
    bersihkan_stop()
    lock = ambil_lock()
    if lock is None:
        log("Supervisor lain sudah berjalan. Tidak ada yang dilakukan.")
        return 1

    log("=" * 60)
    log(f"Supervisor aktif (PID {os.getpid()}), controlling {MAIN.name}.")
    jeda = BACKOFF_AWAL
    percobaan = 0

    try:
        while not stop_diminta():
            percobaan += 1
            kode, durasi = jalankan_sekali()

            if stop_diminta():
                log("Permintaan berhenti diterima, supervisor selesai.")
                break

            if kode < 0:
                log("Main.py tidak bisa dijalankan sama sekali.")
            else:
                log(f"Main.py berhenti dengan kode {kode} setelah {durasi:.0f} detik.")

            if kode == 0 and durasi < 1.0:
                # Keluar instan berulang kali = salah konfigurasi, bukan
                # crash. Jeda panjang supaya tidak membanjiri log.
                jeda = BACKOFF_MAKS
            elif durasi >= SEHAT_SETELAH:
                # Child sudah berjalan stabil: masalahnya sesaat, jadi jeda
                # restart dikembalikan ke nilai paling kecil.
                log(f"Child bertahan {durasi:.0f} detik, dianggap sehat, jeda di-reset.")
                jeda = BACKOFF_AWAL
            else:
                jeda = min(BACKOFF_MAKS, max(BACKOFF_AWAL, jeda * 1.5))

            log(f"Restart dalam {jeda:.0f} detik (percobaan ke-{percobaan}).")
            waktu_tidur = 0.0
            while waktu_tidur < jeda:
                if stop_diminta():
                    break
                time.sleep(min(1.0, jeda - waktu_tidur))
                waktu_tidur += 1.0
    finally:
        bersihkan_stop()
        log("Supervisor berhenti.")
    return 0


def main() -> int:
    """Titik masuk: ``start``, ``stop``, atau ``status``.

    Returns:
        Exit code untuk skrip.
    """
    parser = argparse.ArgumentParser(
        prog="server.py",
        description="Supervisor userbot: menjaga main.py hidup di background.",
    )
    parser.add_argument(
        "aksi",
        nargs="?",
        default="start",
        choices=("start", "stop", "status"),
        help="start (default) jalankan supervisor, stop hentikan, status cek",
    )
    args = parser.parse_args()

    if args.aksi == "stop":
        minta_stop()
        print("Permintaan stop dikirim. Supervisor dan child dihentikan sebentar lagi.")
        return 0

    if args.aksi == "status":
        ada_stop = STOP_FLAG.exists()
        print(f"File session   : {(BASE_DIR / 'data' / 'userbot.session').exists()}")
        print(f"Stop flag      : {'ada (sedang berhenti)' if ada_stop else 'tidak ada (aktif)'}")
        if LOG_FILE.exists():
            print(f"Log supervisor : {LOG_FILE}")
            print("--- 10 baris terakhir ---")
            print(LOG_FILE.read_text(encoding="utf-8", errors="replace")[-2000:])
        else:
            print("Log supervisor : belum ada")
        return 0

    try:
        return supervise()
    except Exception:
        # pythonw.exe tidak punya stderr, jadi tanpa catch di sini error
        # akan hilang tanpa jejak. Semua kegagalan fatal masuk ke log file.
        log("FATAL: " + traceback.format_exc().replace("\n", " | "))
        raise


if __name__ == "__main__":
    # pythonw.exe tidak punya stderr sama sekali. Semua kesalahan, termasuk
    # yang terjadi saat import modul, dicatat ke file supaya tidak hilang.
    try:
        sys.exit(main())
    except BaseException:
        try:
            log("FATAL: " + traceback.format_exc().replace("\n", " | "))
        except Exception:
            pass
        raise
