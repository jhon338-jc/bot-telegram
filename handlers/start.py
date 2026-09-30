"""Perintah ``/start`` dan ``/halo``.

``/start`` memperkenalkan userbot beserta perintah yang tersedia, disertai
kumpulan tombol pintasan. ``/halo`` memberi sapaan personal beserta role
yang sedang dimiliki user di chat tersebut.

Seluruh isi balasan tanpa emoji: judul memakai huruf kapital bergaris ``=``
dan isi memakai label rata kiri. Tombol memakai huruf kapital polos
(``/MENU``, ``/ID``) supaya labelnya tidak bergantung pada font emoji.

Semua perintah pada project ini dipicu dengan garis miring (``/``).
Balasan otomatis untuk pesan teks biasa sengaja tidak ada: setiap aksi
harus memang diketik user, sehingga akun tidak pernah mengirim pesan tanpa
permintaan dan aman dari pemblokiran Telegram.
"""

from __future__ import annotations

import logging

from telethon.tl.custom import Button

from utils.commands import command_pattern, new_message
from utils.context import Context
from utils.permissions import periksa_pemohon
from utils.ratelimit import send_limiter
from utils.tampilan import baris, bersih, judul, potong

logger = logging.getLogger(__name__)

COMMAND_START = "start"
COMMAND_HALO = "halo"

TOMBOL = [
    [Button.text("/MENU", resize=True), Button.text("/ID", resize=True)],
    [Button.text("/PING", resize=True), Button.text("/HELP", resize=True)],
]


def pengenalan(ctx: Context) -> str:
    """Teks perkenalan yang dipakai bersama oleh ``/start`` dan ``/halo``.

    Args:
        ctx: Konteks bersama berisi profil akun.

    Returns:
        String perkenalan.
    """
    return (
        f"Aku {ctx.mention}, userbot yang berjalan di atas akun "
        f"{bersih(ctx.display_name)}.\n"
        f"Semua perintah diawali garis miring, ketik /menu untuk melihat "
        f"tombol lengkap."
    )


async def start(event, ctx: Context) -> None:
    """Tangani ``/start``: perkenalan dan pintasan perintah.

    Args:
        event: Event pesan masuk dari Telethon.
        ctx: Konteks bersama berisi klien, database, dan profil akun.
    """
    sender = await event.get_sender()
    if sender is None:
        return

    nama = bersih(sender.first_name) or "sobat"
    if event.is_private:
        tambahan = "Ketik /help untuk melihat semua perintah."
    else:
        tambahan = (
            f"Di grup, perintahku dipanggil dengan menyebut {ctx.mention} "
            "atau me-reply pesan yang aku kirim."
        )

    await send_limiter.wait()
    await event.reply(
        judul("perkenalan")
        + "\n"
        + "\n".join(
            [
                baris("Halo", nama),
                baris("Akun", ctx.display_name),
                baris("ID akun", ctx.me_id),
                baris("Username", f"@{ctx.username}" if ctx.username else "-"),
            ]
        )
        + "\n\n"
        + potong(tambahan, 300),
        buttons=TOMBOL,
    )
    logger.info("User %s menjalankan /start.", sender.id)


async def halo(event, ctx: Context) -> None:
    """Tangani ``/halo``: sapaan personal lengkap dengan role user.

    Args:
        event: Event pesan masuk dari Telethon.
        ctx: Konteks bersama berisi database dan profil akun.
    """
    akses = await periksa_pemohon(event, ctx)
    ctx.db.register_user(
        akses.user_id,
        akses.username,
        akses.display,
        None,
        "private" if event.is_private else "group",
    )
    ctx.db.catat_role(akses.user_id, akses.role)

    nama = (bersih(akses.display).split() or ["sobat"])[0]
    await send_limiter.wait()
    await event.reply(
        judul(f"halo {nama}")
        + "\n"
        + "\n".join(
            [
                baris("Role kamu", akses.role_label),
                baris("Status kamu", akses.status),
                baris("Bot ini", ctx.display_name),
                baris("ID akun bot", ctx.me_id),
            ]
        )
        + "\n\n"
        + "Coba /id untuk detail lengkap, atau /menu untuk tombol lengkap.",
        buttons=TOMBOL,
    )
    logger.info("User %s (%s) menjalankan /halo.", akses.user_id, akses.role)


def register(ctx: Context) -> None:
    """Daftarkan handler ``/start`` dan ``/halo``.

    Args:
        ctx: Konteks bersama yang menyimpan klien Telethon.
    """

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND_START)))
    async def _on_start(event) -> None:
        await start(event, ctx)

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND_HALO)))
    async def _on_halo(event) -> None:
        await halo(event, ctx)
