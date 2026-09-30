"""Database SQLite sederhana untuk registrasi user dan penghitung pesan.

Menggunakan modul standar ``sqlite3`` tanpa dependensi tambahan. Mode WAL
diaktifkan untuk kinerja baca/tulis yang lebih baik. Semua query memakai
parameter binding untuk keamanan.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

SCHEMA: str = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    first_name  TEXT,
    last_name   TEXT,
    chat_type   TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    chat_id    INTEGER NOT NULL,
    text       TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_user ON messages (user_id);
"""

# Kolom yang ditambahkan setelah versi pertama. Dijalankan sebagai migrasi
# ringan setiap start supaya database lama ikut ter-upgrade.
MIGRASI: tuple[tuple[str, str], ...] = (
    ("users", "last_role TEXT"),
    ("users", "role_seen TEXT"),
)


def _now() -> str:
    """Return timestamp UTC saat ini dalam ISO 8601."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Database:
    """Wrapper tipis untuk koneksi SQLite yang thread-safe."""

    def __init__(self, db_path: Path) -> None:
        """Inisialisasi path database.

        Args:
            db_path: Lokasi file database SQLite.
        """
        self.db_path: Path = db_path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Buka koneksi, aktifkan WAL, buat skema, lalu jalankan migrasi.

        Raises:
            sqlite3.Error: Jika gagal membuka atau menginisialisasi DB.
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        """Tambahkan kolom baru bila belum ada di database lama.

        ``ALTER TABLE ... ADD COLUMN`` tidak punya ``IF NOT
        EXISTS``, jadi ketersediaan kolom dicek lebih dulu lewat
        ``PRAGMA table_info``.
        """
        conn = self._require_conn()
        for tabel, definisi in MIGRASI:
            kolom = definisi.split()[0]
            ada = {baris["name"] for baris in conn.execute(f"PRAGMA table_info({tabel})")}
            if kolom not in ada:
                conn.execute(f"ALTER TABLE {tabel} ADD COLUMN {definisi}")

    def _require_conn(self) -> sqlite3.Connection:
        """Return koneksi aktif atau naikkan error bila belum dibuka.

        Raises:
            RuntimeError: Jika koneksi belum dibuka.
        """
        if self._conn is None:
            raise RuntimeError("Database belum connect(). Panggil connect() dulu.")
        return self._conn

    def _cursor(self) -> sqlite3.Cursor:
        """Return cursor dari koneksi aktif."""
        return self._require_conn().cursor()

    def register_user(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        chat_type: str | None,
    ) -> None:
        """Simpan atau perbarui data user (upsert).

        Args:
            user_id: ID Telegram user.
            username: Username tanpa ``@`` (bisa ``None``).
            first_name: Nama depan user.
            last_name: Nama belakang user (bisa ``None``).
            chat_type: Tipe chat, misal ``private`` / ``group``.
        """
        with self._lock, self._require_conn() as conn:
            now = _now()
            conn.execute(
                """
                INSERT INTO users
                    (user_id, username, first_name, last_name, chat_type,
                     first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username    = excluded.username,
                    first_name  = excluded.first_name,
                    last_name   = excluded.last_name,
                    chat_type   = excluded.chat_type,
                    last_seen   = excluded.last_seen
                """,
                (user_id, username, first_name, last_name, chat_type, now, now),
            )

    def record_message(
        self,
        user_id: int,
        chat_id: int,
        text: str | None,
    ) -> None:
        """Catat satu pesan masuk untuk keperluan statistik/counter.

        Args:
            user_id: ID Telegram pengirim.
            chat_id: ID chat tempat pesan dikirim.
            text: Isi teks pesan (bisa ``None`` untuk non-teks).
        """
        with self._lock, self._require_conn() as conn:
            conn.execute(
                """
                INSERT INTO messages (user_id, chat_id, text, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, chat_id, text, _now()),
            )

    def catat_role(self, user_id: int, role: str) -> None:
        """Simpan role terakhir yang teramati untuk sebuah user.

        Args:
            user_id: ID Telegram user.
            role: Kunci role, misal ``"admin_grup"``.
        """
        with self._lock, self._require_conn() as conn:
            ada = conn.execute(
                "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if ada is None:
                return
            conn.execute(
                "UPDATE users SET last_role = ?, role_seen = ? WHERE user_id = ?",
                (role, _now(), user_id),
            )

    def get_user(self, user_id: int) -> sqlite3.Row | None:
        """Ambil data satu user berdasarkan ID.

        Args:
            user_id: ID Telegram user.

        Returns:
            Baris users, atau ``None`` jika tidak ditemukan.
        """
        with self._lock:
            row = self._cursor().execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return row

    def get_message_count(self, user_id: int) -> int:
        """Hitung jumlah pesan yang pernah dikirim user.

        Args:
            user_id: ID Telegram user.

        Returns:
            Total pesan user tersebut.
        """
        with self._lock:
            row = self._cursor().execute(
                "SELECT COUNT(*) AS total FROM messages WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return int(row["total"]) if row else 0

    def get_total_users(self) -> int:
        """Hitung total user terdaftar.

        Returns:
            Jumlah baris pada tabel users.
        """
        with self._lock:
            row = self._cursor().execute(
                "SELECT COUNT(*) AS total FROM users"
            ).fetchone()
        return int(row["total"]) if row else 0

    def get_total_messages(self) -> int:
        """Hitung total pesan yang tercatat.

        Returns:
            Jumlah baris pada tabel messages.
        """
        with self._lock:
            row = self._cursor().execute(
                "SELECT COUNT(*) AS total FROM messages"
            ).fetchone()
        return int(row["total"]) if row else 0

    def close(self) -> None:
        """Tutup koneksi database bila masih terbuka."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None