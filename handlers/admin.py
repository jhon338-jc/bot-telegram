"""Perintah ``/admin`` untuk pemilik bot dan admin.

Perintah ini menampilkan ringkasan hak akses pengirim, konfigurasi
userbot, dan statistik database. Aksesnya dijaga dekorator
:func:`utils.permissions.admin_only`, jadi hanya pemilik bot, admin grup,
atau user yang terdaftar di ``ADMIN_IDS`` yang bisa membukanya.
"""

from __future__ import annotations

import logging

import config
from utils.commands import command_pattern, new_message
from utils.context import Context
from utils.permissions import admin_only, ringkas_akses
from utils.ratelimit import send_limiter
from utils.tampilan import baris, bersih, judul, potong, sub

logger = logging.getLogger(__name__)

COMMAND = "admin"


async def admin(event, ctx: Context, akses) -> None:
    """Tangani ``/admin``: panel ringkasan untuk pemilik bot dan admin.

    Args:
        event: Event pesan masuk dari Telethon.
        ctx: Konteks bersama berisi database dan konfigurasi.
        akses: Hak akses pengirim perintah.
    """
    total_user = ctx.db.get_total_users()
    total_pesan = ctx.db.get_total_messages()

    admin_daftar = ", ".join(str(a) for a in config.ADMIN_IDS) or "kosong"
    grup_daftar = ", ".join(str(g) for g in config.ALLOWED_GROUP_IDS) or "kosong"

    await send_limiter.wait()
    await event.reply(
        judul("panel admin")
        + "\n"
        + "\n".join(
            [
                sub("kamu", 30),
                baris("Nama", potong(bersih(akses.display) or "-", 40)),
                baris("User ID", akses.user_id),
                baris("Role", akses.role_label),
                baris("Status", akses.status),
                baris("Hak akses", ringkas_akses(akses)),
                sub("akun bot", 30),
                baris("Nama", ctx.display_name),
                baris(
                    "Username",
                    f"@{ctx.username}" if ctx.username else "tidak punya username",
                ),
                baris("ID akun", ctx.me_id),
                sub("penyimpanan", 30),
                baris("User tercatat", total_user),
                baris("Pesan tercatat", total_pesan),
                sub("konfigurasi", 30),
                baris("ADMIN_IDS", admin_daftar),
                baris("Grup diizinkan", grup_daftar),
                baris("Jeda kirim", f"{config.SEND_DELAY} detik"),
            ]
        )
        + "\n\nPerintah lain: /members /admins /perms /stat /id /groups /help"
    )
    logger.info("Panel admin dibuka oleh %s (%s).", akses.user_id, akses.role)


def register(ctx: Context) -> None:
    """Daftarkan handler ``/admin`` (khusus pemilik bot dan admin).

    Args:
        ctx: Konteks bersama yang menyimpan klien Telethon.
    """

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND)))
    @admin_only
    async def _on_admin(event, ctx_, akses) -> None:
        await admin(event, ctx_, akses)
