"""Pencocokan perintah Telegram untuk Telethon.

Telethon mencocokkan event pesan dengan regex biasa, bukan dengan parser
perintah seperti ``python-telegram-bot``. Modul ini menyediakan satu pola
baku supaya semua perintah konsisten dan bisa menangkap argument di
belakang perintah.
"""

from __future__ import annotations

import re

from telethon import events
from telethon.tl.types import MessageEntityMention

import config

COMMAND_RE = re.compile(r"^/([A-Za-z0-9_]+)(?:@([A-Za-z0-9_]+))?(?:[ \t]+([\s\S]*))?$")


def in_allowed_chat(event: object) -> bool:
    """Periksa apakah event terjadi di chat yang boleh dilayani.

    Chat pribadi selalu dilayani. Grup harus terdaftar di
    ``ALLOWED_GROUP_IDS``; bila daftar itu kosong, tidak ada grup yang
    dilayani sama sekali.

    Args:
        event: Event pesan dari Telethon.

    Returns:
        ``True`` bila chat ini diizinkan.
    """
    if getattr(event, "is_private", False):
        return True
    return config.is_group_allowed(getattr(event, "chat_id", 0))


def command_pattern(command: str) -> str:
    """Bentuk regex yang mencocoki sebuah perintah beserta argumennya.

    Pola ini menerima tiga bentuk penulisan:

    - ``/perintah`` — di chat pribadi atau grup yang biasa.
    - ``/perintah@username`` — Telegram otomatis menambahkan username
      tujuan bila perintah diarahkan ke user tertentu.
    - ``/perintah argumen` — argumen bebas setelah spasi pertama.

    Args:
        command: Nama perintah tanpa garis miring, misal ``"start"``.

    Returns:
        String regex siap pakai untuk ``events.NewMessage(pattern=...)``.
    """
    return rf"^/{command}(?:@[A-Za-z0-9_]+)?(?:[ \t]+([\s\S]*))?\s*\Z"


def parse_command(text: str | None) -> tuple[str, str] | None:
    """Pecah teks pesan menjadi ``(nama_perintah, argumen)``.

    Args:
        text: Teks mentah dari pesan Telegram.

    Returns:
        Tuple berisi nama perintah huruf kecil dan sisa argumennya, atau
        ``None`` bila teks bukan perintah.
    """
    if not text:
        return None
    match = COMMAND_RE.match(text.strip())
    if match is None:
        return None
    return match.group(1).lower(), (match.group(3) or "").strip()


def args_of(text: str | None) -> str:
    """Ambil argumen sebuah perintah tanpa melakukan validasi nama.

    Args:
        text: Teks mentah dari pesan Telegram.

    Returns:
        Teks setelah nama perintah, atau string kosong.
    """
    if not text:
        return ""
    match = COMMAND_RE.match(text.strip())
    if match is None:
        return ""
    return (match.group(3) or "").strip()


def new_message(**kwargs: object) -> events.NewMessage:
    """Bungkus ``events.NewMessage`` agar semua handler memakai default sama.

    Default yang dipasang di sini:

    - ``incoming=True``: abaikan pesan yang dikirim akun ini sendiri.
    - ``func=in_allowed_chat``: abaikan grup yang tidak terdaftar di
      ``ALLOWED_GROUP_IDS``. Chat pribadi selalu boleh.

    Karena semua handler memakai fungsi ini, aturan whitelist grup berlaku
    seragam untuk seluruh perintah.

    Args:
        **kwargs: Parameter tambahan yang diteruskan ke ``events.NewMessage``.

    Returns:
        Objek ``NewMessage`` yang hanya bereaksi terhadap pesan masuk di chat
        yang diizinkan.
    """
    kwargs.setdefault("func", in_allowed_chat)
    return events.NewMessage(incoming=True, **kwargs)  # type: ignore[arg-type]


def mentioned_username(message: object) -> set[str]:
    """Kumpulkan seluruh username yang disebut di dalam satu pesan.

    Hanya entitas bertipe *mention* (``@nama``) yang diambil, sehingga teks
    biasa yang kebetulan mengandung ``@`` tidak ikut terhitung.

    Args:
        message: Objek ``Message`` dari Telethon.

    Returns:
        Set username huruf kecil tanpa ``@``.
    """
    text = getattr(message, "text", None)
    entities = getattr(message, "entities", None) or ()
    if not text or not entities:
        return set()

    found: set[str] = set()
    for entity in entities:
        if not isinstance(entity, MessageEntityMention):
            continue
        fragment = text[entity.offset : entity.offset + entity.length]
        found.add(fragment.lstrip("@").casefold())
    return found
