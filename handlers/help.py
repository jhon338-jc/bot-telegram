"""Perintah ``/help``: daftar perintah menurut level akses.

Teks bantuan dibagi dua bagian supaya jelas: perintah yang boleh dipakai
semua orang, dan perintah khusus pemilik bot serta admin. Seluruh isi
tanpa emoji, memakai helper di :mod:`utils.tampilan`.
"""

from __future__ import annotations

import logging

from telethon.tl.custom import Button

from utils.commands import command_pattern, new_message
from utils.context import Context
from utils.permissions import periksa_pemohon
from utils.ratelimit import send_limiter
from utils.tampilan import garis, judul, potong, sub

logger = logging.getLogger(__name__)

COMMAND = "help"

TOMBOL = [Button.text("/MENU", resize=True)]

PUBLIK: str = (
    "/start    Perkenalan dan pintasan perintah\n"
    "/menu     Menu lengkap dengan tombol\n"
    "/halo     Sapaan personal beserta role kamu\n"
    "/id       Detail akun: ID, status, nomor, role\n"
    "/id @user Detail user lain\n"
    "/ping     Cek apakah bot masih responsif\n"
    "/echo     Aku mengulang teks yang kamu kirim\n"
    "/groups   Daftar grup yang diikuti akun ini\n"
    "/help     Daftar perintah ini"
)

RAHASIA: str = (
    "/perms    Hak akses lengkap seorang user di grup ini\n"
    "/admins   Daftar admin dan pemilik grup\n"
    "/members  Semua anggota grup beserta role-nya\n"
    "/salam    Ucapan selamat datang, atur di grup\n"
    "/pamit   Ucapan perpisahan, atur di grup\n"
    "/admin    Panel admin dan konfigurasi bot\n"
    "/stat     Statistik dan uptime userbot"
)


def help_text(mention: str, role: str, boleh_rahasia: bool) -> str:
    """Susun teks bantuan sesuai role user.

    Args:
        mention: Sebutan akun yang bisa diketik di grup.
        role: Nama role user saat ini.
        boleh_rahasia: ``True`` bila user boleh melihat perintah admin.

    Returns:
        String berisi daftar perintah.
    """
    bagian = [judul("perintah umum"), PUBLIK]

    if boleh_rahasia:
        bagian.append("\n" + sub("khusus pemilik bot dan admin"))
        bagian.append(RAHASIA)
    else:
        bagian.append("\n" + sub("perintah admin"))
        bagian.append(
            "Perintah /perms /admins /members /salam /pamit /admin /stat\n"
            "hanya untuk pemilik bot dan admin grup.\n"
            f"Role kamu sekarang: {potong(role, 40)}."
        )

    bagian.append("\n\n" + sub("tips"))
    bagian.append(
        "1. Semua perintah diawali garis miring (/).\n"
        "2. Di grup, sebut " + potong(mention, 40) + " atau me-reply pesan\n"
        "   yang aku kirim.\n"
        "3. Cek role dan hak akses kapan saja dengan /id @namamu."
    )

    bagian.append("\n" + garis(20))
    bagian.append("Ketuk /MENU untuk memakai tombol.")

    return "\n".join(bagian)


async def help_command(event, ctx: Context) -> None:
    """Tangani ``/help``.

    Args:
        event: Event pesan masuk dari Telethon.
        ctx: Konteks bersama berisi profil akun.
    """
    akses = await periksa_pemohon(event, ctx)
    await send_limiter.wait()
    await event.reply(
        help_text(ctx.mention, akses.role_label, akses.can_manage), buttons=TOMBOL
    )
    logger.info("Bantuan ditampilkan untuk user %s.", event.sender_id)


def register(ctx: Context) -> None:
    """Daftarkan handler ``/help``.

    Args:
        ctx: Konteks bersama yang menyimpan klien Telethon.
    """

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND)))
    async def _on_help(event) -> None:
        await help_command(event, ctx)
