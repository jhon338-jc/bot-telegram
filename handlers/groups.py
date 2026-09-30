"""Handler untuk perintah /groups: daftar grup & supergroup yang diikuti akun.

Perintah ini menjawab masalah khas userbot: mencari tahu ID grup yang
harus dimasukkan ke ``ALLOWED_GROUP_IDS``. ID dialog dibaca langsung dari
Telegram, jadi tidak perlu bot pihak ketiga seperti @RawDataBot.

Bentuk singkat ``/groups <cari>`` menyaring daftar berdasarkan nama grup.
Seluruh isi balasan tanpa emoji.
"""

from __future__ import annotations

import logging

from telethon.tl.types import Channel, Chat

import config
from utils.commands import args_of, command_pattern, new_message
from utils.context import Context
from utils.ratelimit import send_limiter
from utils.tampilan import bersih, judul, potong

logger = logging.getLogger(__name__)

COMMAND = "groups"

MAX_DIALOGS = 200
CHUNK_SIZE = 8


def _is_group(entity: object) -> bool:
    """Periksa apakah sebuah entitas dialog adalah grup atau supergroup.

    Args:
        entity: Objek entitas dari Telethon.

    Returns:
        ``True`` untuk grup biasa maupun supergroup, ``False`` untuk user
        pribadi dan channel abono.
    """
    if isinstance(entity, Chat):
        return True
    return isinstance(entity, Channel) and bool(getattr(entity, "megagroup", False))


async def groups(event, ctx: Context) -> None:
    """Tangani perintah ``/groups``: tampilkan daftar grup yang diikuti.

    Args:
        event: Event pesan masuk dari Telethon.
        ctx: Konteks bersama berisi klien Telethon.
    """
    keyword = args_of(event.message.text).casefold()

    dialogs = await ctx.client.get_dialogs(limit=MAX_DIALOGS)

    lines: list[str] = []
    for dialog in dialogs:
        entity = dialog.entity
        if not _is_group(entity):
            continue
        title = bersih(entity.title) or "(tanpa nama)"
        if keyword and keyword not in title.casefold():
            continue
        status = "AKTIF" if config.is_group_allowed(dialog.id) else "nonaktif"
        lines.append(f"{potong(title, 36)} | {dialog.id} | {status}")

    if not lines:
        await event.reply(
            "Tidak ada grup yang cocok.\n\n"
            "Syaratnya: akun ini sudah bergabung dengan grup tersebut. "
            "Kalau grupnya tidak muncul, hapus history lalu kirim pesan "
            "di grup itu sekali saja agar muncul di daftar."
        )
        return

    header = judul(f"grup yang diikuti ({len(lines)})") + "\n"
    header += "Salin ID-nya ke ALLOWED_GROUP_IDS di file .env untuk\n"
    header += "mengaktifkan balasan di grup tersebut.\n"
    header += "AKTIF berarti grup itu sudah ada di whitelist.\n"

    chunks = [lines[i : i + CHUNK_SIZE] for i in range(0, len(lines), CHUNK_SIZE)]

    # Bisa sampai puluhan pesan beruntun, jadi wajib berbagi limiter
    # dengan perintah lain agar tidak kena flood-wait.
    for index, chunk in enumerate(chunks):
        await send_limiter.wait()
        if index == 0:
            await event.reply(header + "\n" + "\n".join(chunk))
        else:
            await event.reply("\n".join(chunk))

    logger.info("Daftar grup dikirim ke user %s (%d entri).", event.sender_id, len(lines))


def register(ctx: Context) -> None:
    """Daftarkan handler ``/groups`` ke klien.

    Args:
        ctx: Konteks bersama yang menyimpan klien Telethon.
    """

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND)))
    async def _on_groups(event) -> None:
        await groups(event, ctx)
