"""Ucapan otomatis saat ada anggota yang bergabung atau keluar.

Handler ini memakai ``events.ChatAction`` dari Telethon, yang memicu saat
Telegram mengirim aksi "X bergabung dengan grup" atau "X keluar dari grup".

**Berlaku di semua grup yang diikuti akun ini.** Berbeda dengan perintah
wajib yang memakai :func:`utils.commands.new_message` (terikat
``ALLOWED_GROUP_IDS``), listener di sini sengaja tidak memakai whitelist:
ucapan ikut berjalan di grup mana pun selama akun ini masih anggota.
ucapan ini bisa dimatikan per grup dengan ``/off`` atau semuanya lewat
``WELCOME_ENABLED=0`` / ``GOODBYE_ENABLED=0`` di ``.env``.

Perintah dari modul ini:

- ``/salam`` - lihat atau atur template ucapan selamat datang.
- ``/pamit`` - lihat atau atur template ucapan perpisahan.
- ``/off`` dan ``/on`` - matikan atau nyalakan ucapan di grup ini.

Semua balasan tanpa emoji.
"""

from __future__ import annotations

import logging

from telethon import events
from telethon.tl.types import Channel, Chat

import config
from utils import ucapan
from utils.commands import args_of, command_pattern, new_message
from utils.context import Context
from utils.permissions import admin_only
from utils.ratelimit import send_limiter
from utils.tampilan import baris, judul

logger = logging.getLogger(__name__)

COMMAND_SALAM = "salam"
COMMAND_PAMIT = "pamit"
COMMAND_ON = "on"
COMMAND_OFF = "off"

PRIVAT = "Perintah ini hanya bisa dipakai di dalam grup."

USAGE: str = (
    "Format:\n"
    "/salam                 tampilkan template yang aktif\n"
    "/salam <teks>          ganti template, boleh pakai penanda\n"
    "/salam default         kembali ke template bawaan\n"
    "\n"
    "Penanda yang tersedia:\n"
    "{nama}  {grup}  {jumlah}  {baris}  {ctx}\n"
    "\n"
    "Contoh satu baris:\n"
    "Selamat datang {nama} di {grup}. Anggota sekarang {jumlah} orang."
)

def _display_user(user) -> str:
    """Rakit nama tampilan user dari objek Telethon.

    Args:
        user: Objek ``User`` dari Telethon.

    Returns:
        Nama gabungan first name dan last name, atau ID bila kosong.
    """
    if user is None:
        return "user"
    nama = " ".join(filter(None, [getattr(user, "first_name", None), getattr(user, "last_name", None)]))
    return nama.strip() or str(getattr(user, "id", "user"))


async def _jumlah_anggota(client, chat_id: int) -> int:
    """Hitung jumlah anggota grup, dan bail out bila terlalu besar.

    Args:
        client: Klien Telethon.
        chat_id: ID grup.

    Returns:
        Jumlah anggota, atau ``0`` bila tidak bisa dihitung. Nilai ``0``
        membuat ``{jumlah}`` tidak dipakai pada template.
    """
    try:
        hasil = await client.get_participants(chat_id)
    except Exception as exc:  # noqa: BLE001 - jumlah hanya informatif
        logger.debug("Hitung anggota %s gagal: %s", chat_id, exc)
        return 0
    if len(hasil) > 5000:
        return 0
    return len(hasil)


async def _kirim(ctx: Context, event, jenis: str, nama: str, grup: str) -> None:
    """Susun lalu kirim satu ucapan ke grup asal event.

    Args:
        ctx: Konteks bersama berisi klien dan profil akun.
        event: Event ``ChatAction`` pemicu.
        jenis: ``"salam"`` atau ``"pamit"``.
        nama: Nama user yang bergabung atau keluar.
        grup: Nama grup asal.
    """
    jumlah = await _jumlah_anggota(ctx.client, event.chat_id)
    teks = ucapan.pesan(event.chat_id, jenis, nama, grup, jumlah, ctx.mention)

    await send_limiter.wait()
    try:
        await ctx.client.send_message(event.chat_id, teks)
    except Exception as exc:  # noqa: BLE001 - jangan sampai mematikan listener
        logger.error("Gagal kirim %s di %s: %s", jenis, event.chat_id, exc)
        return

    logger.info("Ucapan %s terkirim di %s untuk %s.", jenis, event.chat_id, nama)


async def on_chat_action(ctx: Context, event) -> None:
    """Kirim ucapan saat ada anggota yang bergabung atau keluar.

    Args:
        ctx: Konteks bersama berisi klien dan profil akun.
        event: Event ``events.ChatAction``.
    """
    if str(event.chat_id) in config.UCAPAN_MATI:
        return

    chat = await event.get_chat()
    if not isinstance(chat, (Channel, Chat)):
        return
    if getattr(chat, "broadcast", False):
        return

    user = await event.get_user()
    if user is None or getattr(user, "bot", False):
        return
    if getattr(user, "id", None) == ctx.me_id:
        return

    nama = _display_user(user)
    grup = getattr(chat, "title", "") or "grup ini"

    if event.user_added:
        if not config.WELCOME_ENABLED:
            return
        await _kirim(ctx, event, "salam", nama, grup)
        return

    if event.user_removed or getattr(event, "user_left", False):
        if not config.GOODBYE_ENABLED:
            return
        await _kirim(ctx, event, "pamit", nama, grup)


async def _lihat(event, slot: str, nama_ucapan: str) -> None:
    """Tampilkan template yang sedang aktif untuk grup ini.

    Args:
        event: Event pesan masuk dari Telethon.
        slot: ``"salam"`` atau ``"pamit"``.
        nama_ucapan: Nama Iterator dalam bahasa manusia.
    """
    if event.is_private:
        await event.reply(PRIVAT)
        return

    await event.reply(
        judul(nama_ucapan)
        + "\n"
        + ucapan.ringkas(ucapan.ambil(event.chat_id, slot))
        + "\n\n"
        + USAGE
    )


async def _atur(event, slot: str, nama_ucapan: str) -> None:
    """Tampilkan atau ubah template ucapan untuk grup ini.

    Args:
        event: Event pesan masuk dari Telethon.
        slot: ``"salam"`` atau ``"pamit"``.
        nama_ucapan: Nama Iterator dalam bahasa manusia.
    """
    if event.is_private:
        await event.reply(PRIVAT)
        return

    argumen = args_of(event.message.text)

    if not argumen:
        await _lihat(event, slot, nama_ucapan)
        return

    if argumen.strip().casefold() in ("default", "bawaan", "reset"):
        diubah = ucapan.setelan(event.chat_id, slot, None)
        await event.reply(
            judul(nama_ucapan)
            + "\n"
            + (
                "Template dikembalikan ke bawaan."
                if diubah
                else "Template sudah memakai bawaan."
            )
        )
        return

    diubah = ucapan.setelan(event.chat_id, slot, argumen)
    await event.reply(
        judul("template disimpan")
        + "\n"
        + "\n".join(
            [
                baris("Jenis", nama_ucapan),
                baris("Panjang", f"{len(argumen)} karakter"),
                baris("Simpan di", "data/ucapan.json"),
            ]
        )
        + "\n\n"
        + ("Teks baru sudah aktif." if diubah else "Gagal menyimpan.")
    )
    logger.info(
        "Template %s diubah di grup %s oleh %s.", slot, event.chat_id, event.sender_id
    )


async def _salam(event, ctx: Context) -> None:
    """Tangani ``/salam`` (khusus admin)."""
    await _atur(event, "salam", "ucapan selamat datang")


async def _pamit(event, ctx: Context) -> None:
    """Tangani ``/pamit`` (khusus admin)."""
    await _atur(event, "pamit", "ucapan perpisahan")


async def _nyala(event, ctx: Context, hidup: bool) -> None:
    """Nyalakan atau matikan ucapan otomatis di grup ini.

    Args:
        event: Event pesan masuk dari Telethon.
        ctx: Konteks bersama (tidak dipakai langsung).
        hidup: ``True`` untuk menyalakan, ``False`` untuk mematikan.
    """
    if event.is_private:
        await event.reply(PRIVAT)
        return

    if hidup:
        config.UCAPAN_MATI.discard(str(event.chat_id))
    else:
        config.UCAPAN_MATI.add(str(event.chat_id))

    status = "AKTIF" if hidup else "DIMATIKAN"
    await event.reply(
        judul("ucapan otomatis")
        + "\n"
        + "\n".join(
            [
                baris("Selamat datang", "AKTIF" if config.WELCOME_ENABLED else "nonaktif"),
                baris("Perpisahan", "AKTIF" if config.GOODBYE_ENABLED else "nonaktif"),
                baris("Status grup ini", status),
            ]
        )
        + "\n\n"
        + "Perintah lain: /salam /pamit /menu"
    )
    logger.info(
        "Ucapan di grup %s dijadikan %s oleh %s.",
        event.chat_id,
        status,
        event.sender_id,
    )


def register(ctx: Context) -> None:
    """Daftarkan listener ChatAction dan perintah ucapan otomatis.

    Args:
        ctx: Konteks bersama berisi klien Telethon.
    """

    @ctx.client.on(events.ChatAction())
    async def _on_action(event) -> None:
        await on_chat_action(ctx, event)

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND_SALAM)))
    @admin_only
    async def _on_salam(event, ctx_) -> None:
        await _salam(event, ctx_)

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND_PAMIT)))
    @admin_only
    async def _on_pamit(event, ctx_) -> None:
        await _pamit(event, ctx_)

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND_ON)))
    @admin_only
    async def _on_on(event, ctx_) -> None:
        await _nyala(event, ctx_, True)

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND_OFF)))
    @admin_only
    async def _on_off(event, ctx_) -> None:
        await _nyala(event, ctx_, False)

    logger.info(
        "Ucapan otomatis aktif di semua grup. Selamat datang %s, perpisahan %s.",
        "ON" if config.WELCOME_ENABLED else "OFF",
        "ON" if config.GOODBYE_ENABLED else "OFF",
    )
