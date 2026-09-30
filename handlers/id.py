"""Perintah ``/id`` dan ``/perms`` untuk melihat detail user.

``/id`` terbuka untuk semua user: menampilkan identitas, status online,
nomor telepon, status premium, dan role lengkap (pemilik bot, pemilik
grup, admin, atau member). Jika argumen diisi, user yang ditunjuk yang
diperiksa; bila tidak, pemeriksaannya adalah pengirim perintah.

``/perms`` hanya untuk pemilik bot dan admin, dan hanya bermakna di dalam
grup karena hak akses selalu bersifat relatif terhadap chat.

Seluruh isi balasan tanpa emoji, memakai helper di :mod:`utils.tampilan`.
"""

from __future__ import annotations

import logging

from utils.commands import args_of, command_pattern, new_message
from utils.context import Context
from utils.permissions import admin_only, cari_user, periksa, periksa_pemohon
from utils.ratelimit import send_limiter
from utils.tampilan import baris, bersih, judul, potong, sub

logger = logging.getLogger(__name__)

COMMAND_ID = "id"
COMMAND_PERMS = "perms"

USAGE_ID = (
    "Format:\n"
    "/id              detail akun kamu\n"
    "/id @username    detail user tertentu\n"
    "/id 123456789    detail berdasarkan ID numerik"
)

TIDAK_DITEMUKAN = "User `{argumen}` tidak ditemukan.\n\n{usage}"


def _isi(args) -> str:
    """Susun isi pesan detail untuk satu :class:`Akses`.

    Args:
        args: Objek ``Akses`` hasil pemeriksaan.

    Returns:
        Teks multi-baris siap kirim, tanpa emoji.
    """
    username = f"@{bersih(args.username)}" if args.username else "tidak punya username"
    telepon = args.phone or "disembunyikan Telegram"

    baris_wa = [
        baris("ID", args.user_id),
        baris("Username", username),
        baris("Tipe", "akun bot" if args.is_bot else "manusia"),
        baris(
            "Status",
            args.status + (f" (terakhir {args.was_online})" if args.was_online != "-" else ""),
        ),
        baris("Premium", "ya" if args.premium else "-"),
        baris("Telepon", telepon),
        baris("Role", args.role_label),
    ]

    if args.is_owner_bot:
        baris_wa.append(baris("Milik", "akun yang menjalankan bot ini"))
    elif args.is_admin_daftar:
        baris_wa.append(baris("Milik", "terdaftar di ADMIN_IDS"))
    else:
        baris_wa.append(baris("Milik", "-"))

    if args.restricted:
        baris_wa.append(baris("Perhatian", "dibatasi Telegram (spam/flood)"))

    teks = judul(potong(bersih(args.display) or str(args.user_id), 40))
    teks += "\n" + "\n".join(baris_wa)

    if args.in_group:
        teks += "\n" + sub("hak akses di grup ini", 26)
        teks += "\n" + "\n".join(args.hak_lines() or ["  tidak punya hak admin"])

    return teks


async def id_command(event, ctx: Context) -> None:
    """Tangani ``/id``: tampilkan detail user.

    Args:
        event: Event pesan masuk dari Telethon.
        ctx: Konteks bersama berisi klien, database, dan profil akun.
    """
    argumen = args_of(event.message.text)

    if not argumen:
        akses = await periksa_pemohon(event, ctx)
    else:
        user = await cari_user(ctx, argumen, event.chat_id)
        if user is None:
            await event.reply(TIDAK_DITEMUKAN.format(argumen=argumen, usage=USAGE_ID))
            return
        akses = await periksa(
            ctx.client,
            event.chat_id,
            user,
            ctx.me_id,
            in_group=not event.is_private,
        )

    catatan = ctx.db.get_user(akses.user_id)
    isi = _isi(akses)

    if catatan is None:
        isi += "\n\nBelum ada riwayat percakapan dengan user ini."
    else:
        jumlah = ctx.db.get_message_count(akses.user_id)
        if jumlah:
            isi += f"\n\nPesan tercatat: {jumlah}"
        isi += f"\nPertama seen  : {catatan['first_seen']}"
        isi += f"\nTerakhir seen : {catatan['last_seen']}"
        role_terakhir = catatan["last_role"] if "last_role" in catatan.keys() else None
        if role_terakhir and role_terakhir != akses.role:
            isi += (
                f"\nRole terakhir : {role_terakhir} "
                f"(sekarang: {akses.role})"
            )

    await send_limiter.wait()
    await event.reply(isi)
    ctx.db.catat_role(akses.user_id, akses.role)
    logger.info("/id dipakai user %s untuk %s.", event.sender_id, akses.user_id)


async def perms_command(event, ctx: Context, akses_pemohon) -> None:
    """Tangani ``/perms`` (khusus admin): hak akses user di grup ini.

    Args:
        event: Event pesan masuk dari Telethon.
        ctx: Konteks bersama berisi klien dan database.
        akses_pemohon: Hak akses pengirim perintah.
    """
    if event.is_private:
        await event.reply(
            "Hak akses hanya bisa dicek di dalam grup.\n"
            "Kirim perintah ini di grup yang ingin kamu periksa."
        )
        return

    argumen = args_of(event.message.text)
    if argumen:
        user = await cari_user(ctx, argumen, event.chat_id)
        if user is None:
            await event.reply(f"User `{argumen}` tidak ditemukan di grup ini.")
            return
        akses = await periksa(
            ctx.client, event.chat_id, user, ctx.me_id, in_group=True
        )
    else:
        akses = akses_pemohon

    siapa = (
        f"@{bersih(akses.username)}" if akses.username else str(akses.user_id)
    )
    hak = "\n".join(akses.hak_lines() or ["  user ini bukan admin"])

    await send_limiter.wait()
    await event.reply(
        judul("hak akses")
        + "\n"
        + "\n".join(
            [
                baris("User", siapa),
                baris("Nama", potong(bersih(akses.display) or "-", 40)),
                baris("Role", akses.role_label),
            ]
        )
        + "\n"
        + sub("hak di grup ini", 26)
        + "\n"
        + hak
    )
    logger.info("/perms dipakai admin %s untuk %s.", akses_pemohon.user_id, akses.user_id)


def register(ctx: Context) -> None:
    """Daftarkan handler ``/id`` dan ``/perms``.

    Args:
        ctx: Konteks bersama yang menyimpan klien Telethon.
    """

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND_ID)))
    async def _on_id(event) -> None:
        await id_command(event, ctx)

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND_PERMS)))
    @admin_only
    async def _on_perms(event, ctx_, akses) -> None:
        await perms_command(event, ctx_, akses)
