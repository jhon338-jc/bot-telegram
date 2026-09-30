"""Perintah ``/members`` dan ``/admins`` untuk melihat anggota grup.

Kedua perintah hanya untuk pemilik bot dan admin, karena membocorkan
struktur internal grup. ``/admins`` menampilkan pemilik grup dan semua
admin, ``/members`` menampilkan gabungan admin dan member beserta role-nya.

Seluruh isi balasan tanpa emoji, memakai helper di :mod:`utils.tampilan`.
"""

from __future__ import annotations

import logging

from utils.commands import args_of, command_pattern, new_message
from utils.context import Context
from utils.permissions import admin_only, daftar_admin, daftar_member, nama_mention, ringkas_akses
from utils.ratelimit import send_limiter
from utils.tampilan import bersih, judul, potong

logger = logging.getLogger(__name__)

COMMAND_ADMINS = "admins"
COMMAND_MEMBERS = "members"

BATAS_MEMBER = 200
PER_BARIS = 10

PRIVAT = "Perintah ini hanya bisa dipakai di dalam grup."


def _format_daftar(judul_teks: str, daftar, batas_per_baris: int = PER_BARIS) -> list[str]:
    """Susun daftar user menjadi beberapa blok pesan.

    Args:
        judul_teks: Baris judul untuk blok pertama.
        daftar: Iterable objek ``Akses``.
        batas_per_baris: Jumlah user per pesan.

    Returns:
        Daftar teks siap kirim, satu elemen per pesan.
    """
    baris_teks = [
        f"{ringkas_akses(a)} {nama_mention(a)} - {potong(bersih(a.display), 28)} "
        f"({a.user_id})"
        for a in daftar
    ]
    if not baris_teks:
        return [judul(judul_teks) + "\n\nTidak ada data yang bisa ditampilkan."]

    blok = [
        baris_teks[i : i + batas_per_baris]
        for i in range(0, len(baris_teks), batas_per_baris)
    ]
    hasil = [judul(judul_teks) + "\n" + "\n".join(blok[0])]
    for lanjutan in blok[1:]:
        hasil.append(potong("lanjutan:\n" + "\n".join(lanjutan), 3800))
    return hasil


async def admins_command(event, ctx: Context, akses_pemohon) -> None:
    """Tangani ``/admins`` (khusus admin): daftar admin dan pemilik grup.

    Args:
        event: Event pesan masuk dari Telethon.
        ctx: Konteks bersama berisi klien Telethon.
        akses_pemohon: Hak akses pengirim perintah.
    """
    if event.is_private:
        await event.reply(PRIVAT)
        return

    admins = await daftar_admin(ctx.client, event.chat_id, ctx.me_id)
    if not admins:
        await event.reply(
            "Tidak bisa membaca daftar admin grup ini.\n"
            "Penyebabnya biasanya: ini grup basic (bukan supergroup), "
            "atau akun ini bukan anggota."
        )
        return

    chunks = _format_daftar(f"admin di grup ini ({len(admins)} orang)", admins)
    for teks in chunks:
        await send_limiter.wait()
        await event.reply(teks)

    logger.info("/admins dipakai admin %s, %d admin ditemukan.", akses_pemohon.user_id, len(admins))


async def members_command(event, ctx: Context, akses_pemohon) -> None:
    """Tangani ``/members`` (khusus admin): daftar anggota dan role-nya.

    Args:
        event: Event pesan masuk dari Telethon.
        ctx: Konteks bersama berisi klien Telethon.
        akses_pemohon: Hak akses pengirim perintah.
    """
    if event.is_private:
        await event.reply(PRIVAT)
        return

    keyword = args_of(event.message.text).casefold()
    anggota = await daftar_member(ctx.client, event.chat_id, ctx.me_id, BATAS_MEMBER)

    if not anggota:
        await event.reply(
            "Tidak bisa membaca anggota grup ini. Pastikan akun ini sudah "
            "bergabung dan grupnya adalah supergroup."
        )
        return

    anggota.sort(key=lambda a: a.level, reverse=True)
    if keyword:
        anggota = [
            a
            for a in anggota
            if keyword in bersih(a.display).casefold()
            or keyword in (a.username or "").casefold()
        ]

    admin_n = sum(1 for a in anggota if a.is_admin)
    member_n = len(anggota) - admin_n
    judul_teks = f"anggota grup ({len(anggota)} dari maks {BATAS_MEMBER})"
    if keyword:
        judul_teks += f" - filter: {keyword}"

    for teks in _format_daftar(judul_teks, anggota, PER_BARIS):
        await send_limiter.wait()
        await event.reply(teks)

    await send_limiter.wait()
    await event.reply(
        f"Total: {admin_n} admin/pemilik, {member_n} member."
    )

    logger.info(
        "/members dipakai admin %s, %d anggota.",
        akses_pemohon.user_id,
        len(anggota),
    )


def register(ctx: Context) -> None:
    """Daftarkan handler ``/admins`` dan ``/members`` (khusus admin).

    Args:
        ctx: Konteks bersama yang menyimpan klien Telethon.
    """

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND_ADMINS)))
    @admin_only
    async def _on_admins(event, ctx_, akses) -> None:
        await admins_command(event, ctx_, akses)

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND_MEMBERS)))
    @admin_only
    async def _on_members(event, ctx_, akses) -> None:
        await members_command(event, ctx_, akses)
