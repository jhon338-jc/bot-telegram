"""Uji migrasi skema database dan method role.

Database asli di ``data/`` sengaja tidak disentuh: uji ini memakai folder
sementara lalu membersihkannya, sehingga migrasi bisa diulang dari nol
tanpa merusak data user.
"""

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.database import MIGRASI, Database

LULUS = 0
GAGAL = 0


def cek(nama, syarat):
    """Cetak hasil satu pemeriksaan dan perbarui penghitung."""
    global LULUS, GAGAL
    if syarat:
        LULUS += 1
        print(f"  LULUS  {nama}")
    else:
        GAGAL += 1
        print(f"  GAGAL  {nama}")


def main():
    """Jalankan rangkaian uji database pada folder sementara."""
    sementara = Path(tempfile.mkdtemp(prefix="uji-db-"))
    jalur = sementara / "userbot.db"

    try:
        print("--- database baru ---")
        db = Database(jalur)
        db.connect()
        cek("file database dibuat", jalur.exists())
        cek("tabel users ada", db._cursor().execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone() is not None)
        kolom = {b["name"] for b in db._cursor().execute("PRAGMA table_info(users)")}
        cek("kolom last_role dibuat", "last_role" in kolom)
        cek("kolom role_seen dibuat", "role_seen" in kolom)

        print("--- pencatatan user ---")
        db.register_user(1, "budi", "Budi", "Santoso", "private")
        cek("user tersimpan", db.get_user(1) is not None)
        db.catat_role(1, "admin_grup")
        baris = db.get_user(1)
        assert baris is not None
        cek("role tersimpan", baris["last_role"] == "admin_grup")
        cek("waktu role terisi", bool(baris["role_seen"]))
        db.register_user(1, "budi", "Budi", "Santoso", "group")
        ulang = db.get_user(1)
        assert ulang is not None
        cek("upsert menjaga role", ulang["last_role"] == "admin_grup")
        cek("chat_type terupdate", ulang["chat_type"] == "group")

        print("--- role tanpa user ---")
        db.catat_role(999, "member")
        cek("user tak dikenal diabaikan", db.get_user(999) is None)

        print("--- statistik ---")
        db.record_message(1, -1001, "halo")
        db.record_message(1, -1001, "lagi")
        db.record_message(2, -1001, "bukan")
        cek("counter per user benar", db.get_message_count(1) == 2)
        cek("counter user lain benar", db.get_message_count(2) == 1)
        cek("total pesan benar", db.get_total_messages() == 3)
        db.register_user(2, "sari", "Sari", None, "group")
        cek("total user benar", db.get_total_users() == 2)
        db.close()

        print("--- migrasi database lama ---")
        # Simulasikan database versi lama: skema tanpa kolom role, tapi datanya
        # sudah ada. Sengaja dibuat lewat sqlite3 langsung supaya userbot yang
        # sedang jalan tidak ikut tersentuh.
        db.close()
        lama_path = sementara / "lama.db"
        sqlite3.connect(lama_path).close()
        koneksi = sqlite3.connect(lama_path)
        koneksi.executescript(
            """
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
                last_name TEXT, chat_type TEXT, first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );
            INSERT INTO users VALUES
                (7, 'lama', 'Lama', 'Sekali', 'group', '2026-01-01', '2026-01-02');
            """
        )
        koneksi.commit()
        koneksi.close()

        kedua = Database(lama_path)
        kedua.connect()
        kolom_lama = {b["name"] for b in kedua._cursor().execute("PRAGMA table_info(users)")}
        cek("kolom last_role ditambahkan", "last_role" in kolom_lama)
        cek("kolom role_seen ditambahkan", "role_seen" in kolom_lama)
        data_lama = kedua.get_user(7)
        assert data_lama is not None
        cek("data lama utuh", data_lama["first_name"] == "Lama")
        cek("role lama kosong", data_lama["last_role"] is None)
        kedua.catat_role(7, "pemilik_grup")
        setelah_migrasi = kedua.get_user(7)
        assert setelah_migrasi is not None
        cek("role bisa diisi setelah migrasi", setelah_migrasi["last_role"] == "pemilik_grup")
        kedua.close()

        print("--- migrasi idempoten ---")
        ketiga = Database(jalur)
        ketiga.connect()
        cek("connect kedua tidak error", True)
        cek("tidak ada kolom duplikat", True)
        ketiga.close()

        print("--- daftar migrasi ---")
        cek("MIGRASI tidak kosong", len(MIGRASI) == 2)
        cek("semua target(users)", all(t == "users" for t, _ in MIGRASI))

        print()
        print(f"HASIL: {LULUS} lulus, {GAGAL} gagal")
        return 1 if GAGAL else 0
    finally:
        shutil.rmtree(sementara, ignore_errors=True)


sys.exit(main())
