"""Perintah ``/ping`` dan ``/stat`` untuk monitoring userbot.

``/ping`` terbuka untuk semua user dan mengukur kecepatan bot memproses
perintah. ``/stat`` hanya untuk pemilik bot dan admin, dan menampilkan
ringkasan konfigurasi, statistik database, dan uptime.

Semua isi balasan tanpa emoji, memakai helper di :mod:`utils.tampilan`.
"""

from __future__ import annotations

import logging
import time

import config
from utils.commands import command_pattern, new_message
from utils.context import Context
from utils.permissions import admin_only
from utils.ratelimit import send_limiter
from utils.tampilan import baris, judul, sub

logger = logging.getLogger(__name__)

COMMAND_PING = "ping"
COMMAND_STAT = "stat"

# Diisi main.py saat userbot aktif, dipakai untuk menghitung uptime.
_MULAI: float | None = None


def tandai_mulai() -> None:
    """Catat waktu aktif userbot untuk perhitungan uptime."""
    global _MULAI
    _MULAI = time.monotonic()


def uptime() -> str:
    """Hitung berapa lama userbot sudah aktif.

    Returns:
        String seperti ``2 jam 5 menit``.
    """
    if _MULAI is None:
        return "tidak diketahui"
    detik = int(time.monotonic() - _MULAI)
    jam, sisa = divmod(detik, 3600)
    menit, sisa = divmod(sisa, 60)
    bagian = []
    if jam:
        bagian.append(f"{jam} jam")
    if menit or jam:
        bagian.append(f"{menit} menit")
    bagian.append(f"{sisa} detik")
    return " ".join(bagian)


async def ping(event, ctx: Context) -> None:
    """Tangani ``/ping``: ukur kecepatan respons bot.

    Args:
        event: Event pesan masuk dari Telethon.
        ctx: Konteks bersama (tidak dipakai langsung).
    """
    awal = time.perf_counter()
    await send_limiter.wait()
    await event.reply("Mengukur...")
    akhir = time.perf_counter()
    await event.reply(
        judul("bot aktif")
        + "\n"
        + "\n".join(
            [
                baris("Status", "aktif dan responsif"),
                baris("Balasan", f"{(akhir - awal) * 1000:.0f} ms"),
                baris("Uptime", uptime()),
            ]
        )
    )
    logger.info("/ping dari %s: %.0f ms", event.sender_id, (akhir - awal) * 1000)


async def stat_command(event, ctx: Context, akses_pemohon) -> None:
    """Tangani ``/stat`` (khusus admin): ringkasan kondisi userbot.

    Args:
        event: Event pesan masuk dari Telethon.
        ctx: Konteks bersama berisi database dan konfigurasi.
        akses_pemohon: Hak akses pengirim perintah.
    """
    total_user = ctx.db.get_total_users()
    total_pesan = ctx.db.get_total_messages()
    grup = ", ".join(str(g) for g in config.ALLOWED_GROUP_IDS) or "tidak ada"
    admin = ", ".join(str(a) for a in config.ADMIN_IDS) or "tidak ada (otomatis akun ini)"

    await send_limiter.wait()
    await event.reply(
        judul("statistik userbot")
        + "\n"
        + "\n".join(
            [
                sub("akun", 30),
                baris("Nama", ctx.display_name),
                baris("Username", f"@{ctx.username}" if ctx.username else "-"),
                baris("ID akun", ctx.me_id),
                baris("Uptime", uptime()),
                baris("Role pemohon", akses_pemohon.role_label),
                sub("penyimpanan", 30),
                baris("User tercatat", total_user),
                baris("Pesan tercatat", total_pesan),
                sub("konfigurasi", 30),
                baris("Admin bot", admin),
                baris("Grup diizinkan", grup),
                baris("Jeda kirim", f"{config.SEND_DELAY} detik"),
            ]
        )
    )
    logger.info("/stat dibuka oleh %s (%s).", akses_pemohon.user_id, akses_pemohon.role)


def register(ctx: Context) -> None:
    """Daftarkan handler ``/ping`` dan ``/stat``.

    Args:
        ctx: Konteks bersama yang menyimpan klien Telethon.
    """

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND_PING)))
    async def _on_ping(event) -> None:
        await ping(event, ctx)

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND_STAT)))
    @admin_only
    async def _on_stat(event, ctx_, akses) -> None:
        await stat_command(event, ctx_, akses)
