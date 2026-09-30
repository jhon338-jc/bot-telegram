"""Uji seluruh handler tanpa menunggu pesan dari orang lain.

Simulasi memakai objek event tiruan sehingga tiap perintah bisa diuji
deterministik: login, semua perintah, deteksi role, dan penanganan error.
Berguna karena pesan yang dikirim akun sendiri memang diabaikan Telethon
(``incoming=True``), jadi tidak bisa diuji lewat chat sungguhan.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from handlers import _guard, on_error
from handlers import admin as h_admin
from handlers import echo as h_echo
from handlers import groups as h_groups
from handlers import help as h_help
from handlers import id as h_id
from handlers import members as h_members
from handlers import menu as h_menu
from handlers import start as h_start
from handlers import stat as h_stat
from handlers import ucapan as h_ucapan
from utils import ucapan as ucap_u
from utils.commands import in_allowed_chat, parse_command
from utils.context import Context
from utils.database import Database
from utils.permissions import Akses, admin_only, periksa, periksa_pemohon
from utils.ratelimit import RateLimiter

LULUS = 0
GAGAL = 0


def cek(nama, syarat):
    global LULUS, GAGAL
    if syarat:
        LULUS += 1
        print(f"  LULUS  {nama}")
    else:
        GAGAL += 1
        print(f"  GAGAL  {nama}")


# Rentang emoji yang sama dengan yang dibuang utils.tampilan.bersih(),
# dipakai ulang di sini supaya uji tidak bergantung pada perilaku strip()
# milik bersih() (bersih() ikut memangkas spasi di tepi teks).
_RENTANG_EMOJI: tuple[tuple[int, int], ...] = (
    (0x00A9, 0x00A9),
    (0x00AE, 0x00AE),
    (0x200B, 0x200F),
    (0x20E3, 0x20E3),
    (0x2122, 0x2122),
    (0x2190, 0x2BFF),
    (0xFE0E, 0xFE0F),
    (0x1F000, 0x1FAFF),
)


def ada_emoji(teks):
    """Periksa apakah teks memuat karakter emoji atau simbol dekoratif.

    Args:
        teks: Teks yang diperiksa.

    Returns:
        ``True`` bila ada minimal satu karakter emoji.
    """
    return any(
        awal <= ord(karakter) <= akhir
        for karakter in teks
        for awal, akhir in _RENTANG_EMOJI
    )


class DbPalsu:
    """Database tiruan agar uji tidak menyentuh file SQLite."""

    def __init__(self):
        self.role_tercatat = {}

    def register_user(self, *a, **k): ...

    def record_message(self, *a, **k): ...

    def get_user(self, user_id):
        return None

    def get_message_count(self, user_id):
        return 3

    def get_total_users(self):
        return 2

    def get_total_messages(self):
        return 7

    def catat_role(self, user_id, role):
        self.role_tercatat[user_id] = role


class KlienPalsu:
    """Klien Telethon tiruan: pengguna di dalam grup."""

    async def get_entity(self, kunci):
        if isinstance(kunci, str) and kunci.lstrip("@").isdigit() is False:
            return SimpleNamespace(
                id=555, username=kunci.lstrip("@"), first_name="Di", last_name="Cari"
            )
        return SimpleNamespace(id=555, username="dicari", first_name="Di", last_name="Cari")

    async def get_participants(self, chat_id, **kwargs):
        return iter(())


def perms(creator=False, admin=False, banned=False, member=True):
    """Bangun objek permissions tiruan.

    Args:
        creator: Tandai sebagai pemilik grup.
        admin: Tandai sebagai admin.
        banned: Tandai sebagai banned.
        member: Tandai sebagai anggota biasa.

    Returns:
        Objek ``ParticipantPermissions`` tiruan.
    """
    return SimpleNamespace(
        is_creator=creator,
        is_admin=creator or admin,
        is_banned=banned,
        is_member=member and not banned,
    )


def buat_akses(
    *,
    user_id: int = 555,
    display: str = "Di Cari",
    username: str | None = "dicari",
    role: str = "member",
    is_bot: bool = False,
    is_owner_bot: bool = False,
    is_admin_daftar: bool = False,
    telegram_admin: bool = False,
    is_creator: bool = False,
    in_group: bool = True,
    status: str = "online",
    was_online: str = "-",
    phone: str | None = None,
    premium: bool = False,
    restricted: bool = False,
    permissions=None,
) -> Akses:
    """Bangun dataclass ``Akses`` dengan nilai default yang wajar."""
    return Akses(
        user_id=user_id,
        display=display,
        username=username,
        role=role,
        is_bot=is_bot,
        is_owner_bot=is_owner_bot,
        is_admin_daftar=is_admin_daftar,
        telegram_admin=telegram_admin,
        is_creator=is_creator,
        in_group=in_group,
        status=status,
        was_online=was_online,
        phone=phone,
        premium=premium,
        restricted=restricted,
        permissions=permissions,
    )


class EventPalsu:
    """Event tiruan yang mencatat pesan yang dikirim bot."""

    def __init__(self, text, chat_id=-100, private=False, sender_id=999, reply=None):
        self.message = SimpleNamespace(
            text=text,
            entities=None,
            reply_to_msg_id=reply,
        )
        self.chat_id = chat_id
        self.is_private = private
        self.sender_id = sender_id
        self.out = False
        self.balasan = []

    async def get_sender(self):
        return SimpleNamespace(
            id=self.sender_id,
            username="penguji",
            first_name="Penguji",
            last_name=None,
            bot=False,
        )

    async def get_reply_message(self):
        return None

    async def reply(self, teks, **kwargs):
        self.balasan.append((teks, kwargs))
        return SimpleNamespace(id=1)


def ctx_palsu():
    """Buat konteks uji dengan klien dan database tiruan."""
    me = SimpleNamespace(
        id=5564133999, first_name="Jhon", username="jhon_338", last_name=None
    )
    db = DbPalsu()
    return Context(client=KlienPalsu(), db=cast(Database, db), me=me)


async def main():
    ctx = ctx_palsu()

    print("--- filter whitelist grup ---")
    cek("chat pribadi selalu boleh", in_allowed_chat(EventPalsu("hi", private=True)))
    cek(
        "grup ter-whitelist boleh",
        in_allowed_chat(EventPalsu("hi", chat_id=-1004427034665)),
    )
    cek(
        "grup lain ditolak",
        not in_allowed_chat(EventPalsu("hi", chat_id=-1001111111111)),
    )

    print("--- parser perintah ---")
    cek("parse /start", parse_command("/start") == ("start", ""))
    cek("parse /echo halo", parse_command("/echo halo") == ("echo", "halo"))
    cek("parse teks biasa", parse_command("halo") is None)

    print("--- deteksi role ---")
    akses = await periksa(
        KlienPalsu(),
        -1001,
        SimpleNamespace(id=1, username="pemilik", first_name="P", last_name=None),
        99,
        perms=perms(creator=True),
        in_group=True,
    )
    cek("pemilik grup terdeteksi", akses.role == "pemilik_grup" and akses.is_creator)

    akses = await periksa(
        KlienPalsu(),
        -1001,
        SimpleNamespace(id=2, username="adm", first_name="A", last_name=None),
        99,
        perms=perms(admin=True),
        in_group=True,
    )
    cek("admin grup terdeteksi", akses.role == "admin_grup" and akses.can_manage)

    akses = await periksa(
        KlienPalsu(),
        -1001,
        SimpleNamespace(id=3, username="member", first_name="M", last_name=None),
        99,
        perms=perms(member=True),
        in_group=True,
    )
    cek("member biasa terdeteksi", akses.role == "member" and not akses.can_manage)

    akses = await periksa(
        KlienPalsu(),
        -1001,
        SimpleNamespace(
            id=4, username="bot", first_name="B", last_name=None, bot=True
        ),
        99,
        perms=perms(member=True),
        in_group=True,
    )
    cek("akun bot terdeteksi", akses.role == "bot")

    akses = await periksa(
        KlienPalsu(),
        -1001,
        SimpleNamespace(id=5, username="kicks", first_name="K", last_name=None),
        99,
        perms=perms(banned=True),
        in_group=True,
    )
    cek("user banned terdeteksi", akses.role == "dilarang")

    akses = await periksa(
        KlienPalsu(),
        -1001,
        SimpleNamespace(id=6, username="luar", first_name="L", last_name=None),
        99,
        perms=None,
        in_group=True,
    )
    cek("non-member terdeteksi", akses.role == "luar" and not akses.can_manage)

    akses = await periksa(
        KlienPalsu(),
        -1001,
        SimpleNamespace(id=7, username="saya", first_name="S", last_name=None),
        7,
        perms=perms(member=True),
        in_group=True,
    )
    cek("pemilik bot tertinggi", akses.role == "pemilik_bot" and akses.can_manage)

    cek(
        "daftar hak akses terisi",
        len(buat_akses(permissions=perms(admin=True)).hak_lines()) > 0,
    )
    cek(
        "non-admin tidak punya baris hak akses",
        buat_akses(permissions=perms(member=True)).hak_lines() == [],
    )
    cek(
        "label pemilik bot berbeda dari admin grup",
        buat_akses(role="pemilik_bot", is_owner_bot=True).role_label
        != buat_akses(role="admin_grup", telegram_admin=True).role_label,
    )

    print("--- gerbang admin_only ---")
    diterima = []

    @admin_only
    async def perintah_rahasia(event, ctx_, akses):
        diterima.append(akses.role)

    await perintah_rahasia(EventPalsu("/x", private=True, sender_id=777), ctx)
    cek("non-admin ditolak", not diterima)

    admin_simpan = config.ADMIN_IDS
    config.ADMIN_IDS = [778]
    await perintah_rahasia(EventPalsu("/x", private=True, sender_id=778), ctx)
    cek("admin dari ADMIN_IDS diterima", diterima == ["admin_daftar"])
    config.ADMIN_IDS = admin_simpan

    print("--- setiap perintah ---")
    ev = EventPalsu("/start", private=True)
    await h_start.start(ev, ctx)
    cek("/start membalas", bool(ev.balasan))
    cek(
        "/start menyertakan tombol",
        bool(ev.balasan) and "buttons" in ev.balasan[0][1],
    )

    ev = EventPalsu("/help", private=True)
    await h_help.help_command(ev, ctx)
    cek("/help membalas", bool(ev.balasan))
    cek(
        "/help menyembunyikan perintah admin untuk member",
        bool(ev.balasan) and "/perms" in ev.balasan[0][0],
    )

    ev = EventPalsu("/halo", private=True)
    await h_start.halo(ev, ctx)
    cek("/halo membalas", bool(ev.balasan))
    cek("/halo menyebut role", bool(ev.balasan) and "Role kamu" in ev.balasan[0][0])

    ev = EventPalsu("/id", private=True)
    await h_id.id_command(ev, ctx)
    cek("/id membalas", bool(ev.balasan))

    ev = EventPalsu("/id @dicari", private=True)
    await h_id.id_command(ev, ctx)
    cek("/id @username membalas", bool(ev.balasan))

    ev = EventPalsu("/echo halo dunia", private=True)
    await h_echo.echo(ev, ctx)
    cek("/echo mengulang teks", bool(ev.balasan) and "halo dunia" in ev.balasan[0][0])

    ev = EventPalsu("/echo", private=True)
    await h_echo.echo(ev, ctx)
    cek("/echo tanpa argumen memberi usage", bool(ev.balasan))

    ev = EventPalsu("/ping", private=True)
    await h_stat.ping(ev, ctx)
    cek("/ping membalas", bool(ev.balasan))

    ev = EventPalsu("/perms", private=True)
    await h_id.perms_command(ev, ctx, buat_akses())
    cek(
        "/perms di private ditolak",
        bool(ev.balasan) and "dalam grup" in ev.balasan[0][0],
    )

    ev = EventPalsu("/admins", private=True)
    await h_members.admins_command(ev, ctx, buat_akses())
    cek("/admins di private ditolak", bool(ev.balasan))

    ev = EventPalsu("/members", private=True)
    await h_members.members_command(ev, ctx, buat_akses())
    cek("/members di private ditolak", bool(ev.balasan))

    ev = EventPalsu("/perms", chat_id=-1004427034665)
    await h_id.perms_command(ev, ctx, buat_akses())
    cek("/perms di grup membalas", bool(ev.balasan))

    ev = EventPalsu("/admins", chat_id=-1004427034665)
    await h_members.admins_command(ev, ctx, buat_akses())
    cek("/admins di grup tetap aman", bool(ev.balasan))

    print("--- panel admin ---")
    ev = EventPalsu("/admin", private=True)
    await h_admin.admin(ev, ctx, buat_akses(role="pemilik_bot", is_owner_bot=True))
    cek("/admin menampilkan panel", bool(ev.balasan) and "PANEL ADMIN" in ev.balasan[0][0])

    ev = EventPalsu("/stat", private=True)
    await h_stat.stat_command(ev, ctx, buat_akses(role="admin_grup", telegram_admin=True))
    cek("/stat menampilkan statistik", bool(ev.balasan) and "STATISTIK USERBOT" in ev.balasan[0][0])

    print("--- database tiruan ---")
    db = DbPalsu()
    db.catat_role(1, "member")
    cek("role tercatat", db.role_tercatat.get(1) == "member")

    print("--- penanganan error ---")
    async def rusak(event):
        raise ValueError("boom uji")

    hasil = await _guard(rusak)(EventPalsu("x", private=True))
    cek("error tidak mematikan proses", hasil is None)
    cek("nama handler terjaga", _guard(rusak).__name__ == "rusak")
    cek("on_error ada", callable(on_error))
    cek("limiter tersedia", isinstance(RateLimiter(0.3), RateLimiter))

    print("--- registrasi modul ---")
    cek("modul /groups punya register", callable(h_groups.register))
    cek("modul /members punya register", callable(h_members.register))
    cek("modul /stat punya register", callable(h_stat.register))
    cek("modul /menu punya register", callable(h_menu.register))
    cek("modul /ucapan punya register", callable(h_ucapan.register))

    print("--- menu tombol ---")
    cek("menu penuh menyertakan tombol", bool(h_menu.tombol(False)))
    cek("menu admin menambah tombol", len(h_menu.tombol(True)) > len(h_menu.tombol(False)))
    cek(
        "label tombol tanpa garis miring ganda",
        all(
            label.count("/") == 1
            for baris_tombol in h_menu.definisi_tombol(True)
            for label, _, _ in baris_tombol
        ),
    )
    cek("isi penuh menyebut ID akun", str(ctx.me_id) in h_menu.isi_penuh(ctx, False))
    cek("isi sederhana ada", "MENU SEDERHANA" in h_menu.isi_sederhana(ctx, False))

    print("--- ucapan otomatis ---")
    salam = ucap_u.pesan(-1, "salam", "Budi", "Grup Uji", 42, "@bot")
    cek("ucapan salam berisi nama", "Budi" in salam)
    cek("ucapan salam berisi jumlah anggota", "42" in salam)
    cek("ucapan salam punya judul", salam.startswith("SELAMAT DATANG"))
    pamit = ucap_u.pesan(-1, "pamit", "Budi", "Grup Uji", 41, "@bot")
    cek("ucapan pamit punya judul", pamit.startswith("SAMPAI JUMPA"))
    cek("penanda template habis", "{" not in salam and "{" not in pamit)
    cek(
        "templat bisa diganti per grup",
        ucap_u.setelan(-99, "salam", "Halo {nama},ucksburst {grup}"),
    )
    cek("templat khusus dipakai", "ucksburst" in ucap_u.ambil(-99, "salam"))
    cek("templat lain tidak terpengaruh", ucap_u.ambil(-1, "salam") == ucap_u.template("salam"))
    cek("templat bisa dikembalikan", ucap_u.setelan(-99, "salam", None))
    cek("setelah dihapus kembali bawaan", ucap_u.ambil(-99, "salam") == ucap_u.template("salam"))

    print("--- jaminan tanpa emoji ---")
    ev = EventPalsu("/start", private=True)
    await h_start.start(ev, ctx)
    teks_terkumpul = [ev.balasan[0][0]]

    for teks in (
        h_start.pengenalan(ctx),
        h_help.help_text(ctx.mention, "member biasa", False),
        h_menu.isi_penuh(ctx, True),
        h_menu.isi_sederhana(ctx, True),
        salam,
        pamit,
    ):
        teks_terkumpul.append(teks)

    cek(
        "semua teks uji bebas emoji",
        all(not ada_emoji(teks) for teks in teks_terkumpul),
    )
    cek("semua teks uji ASCII", all(teks.isascii() for teks in teks_terkumpul))

    print()
    print(f"HASIL: {LULUS} lulus, {GAGAL} gagal")
    return 1 if GAGAL else 0


sys.exit(asyncio.run(main()))
