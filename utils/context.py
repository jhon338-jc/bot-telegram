"""Konteks bersama yang diteruskan ke setiap handler.

Handler pada project ini tidak memakai dekorator global seperti pada
``python-telegram-bot``; masing-masing modul mendaftarkan callback-nya lewat
``register(ctx)``. Objek ``Context`` ini yang membawa klien, database, dan
profil akun sehingga handler tetap modular.
"""

from __future__ import annotations

from dataclasses import dataclass

from telethon import TelegramClient
from telethon.tl.types import User

from utils.database import Database


@dataclass(frozen=True)
class Context:
    """Berisi keadaan yang dibutuhkan semua handler."""

    client: TelegramClient
    db: Database
    me: User

    @property
    def me_id(self) -> int:
        """ID numerik akun yang sedang dijalankan."""
        return self.me.id

    @property
    def username(self) -> str | None:
        """Username akun tanpa ``@``, atau ``None`` bila tidak punya username."""
        return self.me.username

    @property
    def mention(self) -> str:
        """Sebutan yang bisa diketik user untuk memanggil akun ini di grup."""
        return f"@{self.me.username}" if self.me.username else "akun ini"

    @property
    def display_name(self) -> str:
        """Nama akun untuk ditampilkan di log dan pesan."""
        return self.me.first_name or str(self.me_id)
