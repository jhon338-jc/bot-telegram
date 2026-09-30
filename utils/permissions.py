"""Deteksi role, status, dan hak akses user Telegram.

Modul ini adalah sumber kebenaran tunggal untuk pertanyaan "siapa ini dan
apa haknya". Empat tingkat role dibedakan:

- **pemilik bot** - akun yang menjalankan userbot ini (``ctx.me_id``).
  Semua hak akses miliknya, dimanapun perintah dikirim.
- **pemilik grup** - pembuat grup/supergroup tempat perintah dikirim.
- **admin** - admin grup, atau user yang ID-nya terdaftar di ``ADMIN_IDS``
  pada ``.env``.
- **member** - anggota biasa.

Ditambah kondisi khusus: akun bot, user yang sudah dibanned dari grup, dan
user yang bukan anggota grup. Setiap user juga bisa diperiksa status online,
nomor telepon, status premium, dan hak admin lengkapnya.
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from telethon.tl import types
from telethon.tl.custom import ParticipantPermissions
from telethon.tl.types import User

import config
from utils.context import Context
from utils.tampilan import bersih, potong

logger = logging.getLogger(__name__)

# Kunci role, dipakai untuk perbandingan dan penyimpanan di database.
PEMILIK_BOT = "pemilik_bot"
PEMILIK_GRUP = "pemilik_grup"
ADMIN_GRUP = "admin_grup"
ADMIN_DAFTAR = "admin_daftar"
MEMBER = "member"
BOT = "bot"
LUAR = "luar"
DILARANG = "dilarang"

# Urutan dari yang paling berkuasa, untuk membandingkan "siapa lebih tinggi".
TINGKAT: dict[str, int] = {
    PEMILIK_BOT: 100,
    PEMILIK_GRUP: 80,
    ADMIN_GRUP: 60,
    ADMIN_DAFTAR: 50,
    MEMBER: 20,
    BOT: 10,
    LUAR: 5,
    DILARANG: 0,
}

# Nama hak admin Telegram -> label Bahasa Indonesia.
LABEL_HAK: dict[str, str] = {
    "change_info": "ubah info grup",
    "post_messages": "kirim sebagai channel",
    "edit_messages": "edit pesan",
    "delete_messages": "hapus pesan",
    "ban_users": "ban / kick user",
    "invite_users": "undang user",
    "pin_messages": "pin pesan",
    "add_admins": "tambah admin",
    "anonymous": "anonim",
    "manage_call": "kelola suara",
}

DENIED: str = (
    "AKSES DITOLAK\n"
    "==================================\n"
    "Perintah ini hanya untuk pemilik bot dan admin.\n"
    "\n"
    "Role kamu  : {role}\n"
    "\n"
    "Supaya bisa memakai perintah admin:\n"
    "1. Jadi admin di grup ini, atau\n"
    "2. Minta pemilik bot menambahkan ID kamu ke ADMIN_IDS.\n"
    "3. Cek ID kamu dengan /id.\n"
)


@dataclass(frozen=True)
class Akses:
    """Snapshot lengkap hak akses satu user pada satu chat."""

    user_id: int
    display: str
    username: str | None
    role: str
    is_bot: bool
    is_owner_bot: bool
    is_admin_daftar: bool
    telegram_admin: bool
    is_creator: bool
    in_group: bool
    status: str
    was_online: str
    phone: str | None
    premium: bool
    restricted: bool
    permissions: ParticipantPermissions | None = field(default=None, compare=False)

    @property
    def is_admin(self) -> bool:
        """``True`` bila user boleh memakai fitur khusus admin."""
        return self.is_owner_bot or self.telegram_admin or self.is_admin_daftar

    @property
    def can_manage(self) -> bool:
        """``True`` bila user boleh memakai perintah admin."""
        return self.is_admin

    @property
    def level(self) -> int:
        """Angka tingkatan role, makin besar makin berkuasa."""
        return TINGKAT.get(self.role, 0)

    @property
    def mention(self) -> str:
        """Sebutan yang bisa diketik user di grup."""
        return f"@{self.username}" if self.username else self.display

    @property
    def role_label(self) -> str:
        """Nama role dalam bahasa manusia."""
        if self.is_owner_bot:
            return "pemilik bot ini"
        if self.is_creator:
            return "pemilik grup"
        if self.telegram_admin:
            return "admin grup"
        if self.is_admin_daftar:
            return "admin (dari ADMIN_IDS)"
        if self.is_bot:
            return "akun bot"
        if self.role == DILARANG:
            return "sudah dibanned dari grup"
        if self.role == LUAR:
            return "bukan anggota grup"
        return "member biasa"

    def hak_lines(self) -> list[str]:
        """Ubah hak admin menjadi daftar baris yang mudah dibaca.

        Returns:
            Daftar baris seperti ``"bisa hapus pesan"``. Kosong bila user
            bukan admin.
        """
        perms = self.permissions
        if not perms or not perms.is_admin:
            return []

        baris: list[str] = []
        for nama, label in LABEL_HAK.items():
            nilai = getattr(perms, nama, None)
            if nilai is not None and nilai:
                baris.append(f"  bisa {label}")
        if perms.is_creator:
            baris.insert(0, "  semua hak (pemilik grup)")
        if not baris:
            baris.append("  tidak punya hak khusus yang ditampilkan")
        return baris


def _fmt_waktu(nilai) -> str:
    """Format waktu Telegram menjadi string lokal yang ringkas.

    Args:
        nilai: Objek ``datetime`` dari Telethon.

    Returns:
        String seperti ``30 Sep 2026 14:03``.
    """
    if nilai is None:
        return "-"
    try:
        return nilai.astimezone().strftime("%d %b %Y %H:%M")
    except (ValueError, OSError, AttributeError):
        return str(nilai)


def status_user(user: User | None) -> tuple[str, str]:
    """Ringkas status online sebuah user.

    Args:
        user: Objek ``User`` dari Telethon.

    Returns:
        Tuple ``(status, terakhir_seen)``.
    """
    if user is None:
        return "tidak diketahui", "-"

    status = getattr(user, "status", None)
    if isinstance(status, types.UserStatusOnline):
        return "online", "-"
    if isinstance(status, types.UserStatusOffline):
        return "offline", _fmt_waktu(getattr(status, "was_online", None))
    if isinstance(status, types.UserStatusRecently):
        return "baru saja online", "-"
    if isinstance(status, types.UserStatusLastWeek):
        return "online minggu lalu", "-"
    return "tidak diketahui", "-"


async def _ambil_permissions(client, chat_id: int, user_id: int):
    """Ambil hak akses user di sebuah grup tanpa membiarkan error merambat.

    Args:
        client: Klien Telethon.
        chat_id: ID grup.
        user_id: ID user yang diperiksa.

    Returns:
        Objek ``ParticipantPermissions`` atau ``None`` bila tidak tersedia.
    """
    try:
        return await client.get_permissions(chat_id, user_id)
    except Exception as exc:  # noqa: BLE001 - hak akses bersifat opsional
        logger.debug("get_permissions gagal untuk %s di %s: %s", user_id, chat_id, exc)
        return None


def _role_dari_permissions(perms, is_owner_bot: bool, is_admin_daftar: bool, is_bot: bool) -> str:
    """Tentukan kunci role dari objek hak akses Telegram.

    Args:
        perms: ``ParticipantPermissions`` atau ``None``.
        is_owner_bot: Apakah user adalah akun yang menjalankan bot.
        is_admin_daftar: Apakah user ada di ``ADMIN_IDS``.
        is_bot: Apakah user adalah akun bot.

    Returns:
        Salah satu konstanta role di modul ini.
    """
    if is_owner_bot:
        return PEMILIK_BOT
    if perms is None:
        # Di luar grup (chat pribadi) hak akses Telegram tidak ada. User yang
        # terdaftar di ADMIN_IDS tetap dianggap admin, selain itu "luar".
        return ADMIN_DAFTAR if is_admin_daftar else LUAR
    if perms.is_banned:
        return DILARANG
    if perms.is_creator:
        return PEMILIK_GRUP
    if perms.is_admin:
        return ADMIN_GRUP
    if is_admin_daftar:
        return ADMIN_DAFTAR
    if is_bot:
        return BOT
    return MEMBER


async def periksa(
    client,
    chat_id: int | None,
    user: User,
    owner_id: int,
    *,
    in_group: bool,
    perms=None,
) -> Akses:
    """Bangun :class:`Akses` untuk satu user pada satu chat.

    Args:
        client: Klien Telethon.
        chat_id: ID chat tempat pemeriksaan dilakukan.
        user: Objek ``User`` yang diperiksa.
        owner_id: ID akun yang menjalankan userbot.
        in_group: ``True`` bila ``chat_id`` adalah grup/supergroup.
        perms: Hak akses yang sudah diketahui pemanggil. Bila ``None``,
            diambil dari Telegram sesuai ``in_group``.

    Returns:
        Snapshot hak akses yang sudah lengkap.
    """
    is_owner_bot = user.id == owner_id
    is_admin_daftar = config.is_admin(user.id)
    is_bot = bool(getattr(user, "bot", False))

    if perms is None and in_group and chat_id is not None:
        perms = await _ambil_permissions(client, chat_id, user.id)

    role = _role_dari_permissions(perms, is_owner_bot, is_admin_daftar, is_bot)
    status, terakhir = status_user(user)

    nama = " ".join(filter(None, [user.first_name, user.last_name])) or f"user {user.id}"
    return Akses(
        user_id=user.id,
        display=nama,
        username=user.username,
        role=role,
        is_bot=is_bot,
        is_owner_bot=is_owner_bot,
        is_admin_daftar=is_admin_daftar,
        telegram_admin=bool(perms and perms.is_admin),
        is_creator=bool(perms and perms.is_creator),
        in_group=in_group,
        status=status,
        was_online=terakhir,
        phone=getattr(user, "phone", None),
        premium=bool(getattr(user, "premium", False)),
        restricted=bool(getattr(user, "restriction_reason", None)),
        permissions=perms,
    )


async def periksa_pemohon(event, ctx: Context) -> Akses:
    """Periksa user yang mengirim perintah.

    Args:
        event: Event pesan dari Telethon.
        ctx: Konteks bersama.

    Returns:
        Hak akses pengirim pada chat tempat perintah dikirim.
    """
    user = await event.get_sender()
    if user is None:
        return Akses(
            user_id=0,
            display="tidak diketahui",
            username=None,
            role=LUAR,
            is_bot=False,
            is_owner_bot=False,
            is_admin_daftar=False,
            telegram_admin=False,
            is_creator=False,
            in_group=False,
            status="tidak diketahui",
            was_online="-",
            phone=None,
            premium=False,
            restricted=False,
        )
    return await periksa(
        ctx.client,
        event.chat_id,
        user,
        ctx.me_id,
        in_group=not event.is_private,
    )


async def cari_user(ctx: Context, argumen: str, chat_id: int | None) -> User | None:
    """Cari user berdasarkan ID, username, atau reply.

    Args:
        ctx: Konteks bersama.
        argumen: Teks argumen perintah, misal ``"@jhon_338"`` atau ``"12345"``.
        chat_id: ID chat untuk mencari user yang relevan di grup.

    Returns:
        Objek ``User``, atau ``None`` bila tidak ditemukan.
    """
    teks = (argumen or "").strip()
    if not teks:
        return None

    if teks.lstrip("-").isdigit():
        try:
            return await ctx.client.get_entity(int(teks))
        except Exception as exc:  # noqa: BLE001
            logger.debug("get_entity id %s gagal: %s", teks, exc)
            return None

    username = teks.lstrip("@")
    for attempt in (username, f"@{username}"):
        try:
            return await ctx.client.get_entity(attempt)
        except Exception as exc:  # noqa: BLE001
            logger.debug("cari user %s gagal: %s", attempt, exc)
    return None


async def daftar_admin(client, chat_id: int, owner_id: int) -> list[Akses]:
    """Kumpulkan admin dan pemilik grup.

    Args:
        client: Klien Telethon.
        chat_id: ID grup.
        owner_id: ID akun yang menjalankan userbot.

    Returns:
        Daftar hak akses admin, pemilik grup lebih dulu.
    """
    hasil: list[Akses] = []
    try:
        part = await client.get_participants(
            chat_id, filter=types.ChannelParticipantsAdmins()
        )
    except Exception as exc:  # noqa: BLE001 - grup basic tidak mendukung filter
        logger.debug("ambil admin %s gagal: %s", chat_id, exc)
        return hasil

    for peserta in part:
        user = getattr(peserta, "user", None)
        if user is None:
            continue
        akses = await periksa(client, chat_id, user, owner_id, in_group=True)
        hasil.append(akses)

    hasil.sort(key=lambda a: a.level, reverse=True)
    return hasil


async def daftar_member(client, chat_id: int, owner_id: int, batas: int) -> list[Akses]:
    """Kumpulkan anggota grup beserta role-nya.

    Args:
        client: Klien Telethon.
        chat_id: ID grup.
        owner_id: ID akun yang menjalankan userbot.
        batas: Jumlah maksimum anggota yang diambil.

    Returns:
        Daftar hak akses anggota, admin lebih dulu.
    """
    hasil: list[Akses] = []
    try:
        async for peserta in client.iter_participants(chat_id, limit=batas):
            user = getattr(peserta, "user", None)
            if user is None:
                continue
            akses = await periksa(client, chat_id, user, owner_id, in_group=True)
            hasil.append(akses)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ambil member %s gagal: %s", chat_id, exc)
    return hasil


def denied_text(akses: Akses) -> str:
    """Susun pesan penolakan sesuai role pemohon.

    Args:
        akses: Hak akses pemohon.

    Returns:
        Pesan penolakan dalam bahasa Indonesia.
    """
    return DENIED.format(role=akses.role_label)


def admin_only(func):
    """Dekorator pembatas: hanya pemilik bot dan admin yang boleh memanggil.

    Fungsi yang didekorasi harus menerima ``(event, ctx, akses)``.

    Args:
        func: Fungsi async handler dengan tiga parameter.

    Returns:
        Fungsi async pembungkus yang menolak pemohon non-admin.
    """

    @functools.wraps(func)
    async def wrapper(event, ctx: Context):
        akses = await periksa_pemohon(event, ctx)
        if not akses.can_manage:
            logger.info(
                "Akses ditolak untuk user %s (%s) di chat %s.",
                akses.user_id,
                akses.role,
                event.chat_id,
            )
            await event.reply(denied_text(akses))
            return None
        return await func(event, ctx, akses)

    return wrapper


def ringkas_akses(akses: Akses) -> str:
    """Satu baris ringkasan role untuk daftar.

    Args:
        akses: Hak akses user.

    Returns:
        String seperti ``"admin grup"``.
    """
    if akses.is_owner_bot:
        return "pemilik bot"
    if akses.is_creator:
        return "pemilik grup"
    if akses.telegram_admin:
        return "admin grup"
    if akses.is_admin_daftar:
        return "admin (ADMIN_IDS)"
    if akses.is_bot:
        return "akun bot"
    if akses.role == DILARANG:
        return "sudah banned"
    if akses.role == LUAR:
        return "bukan anggota"
    return "member"


def nama_mention(akses: Akses) -> str:
    """Sebutan yang bisa diketik user untuk menyebut sebuah akun.

    Args:
        akses: Hak akses user.

    Returns:
        ``@username`` bila ada, selain itu nama tampilan atau ID.
    """
    if akses.username:
        return f"@{bersih(akses.username)}"
    return potong(bersih(akses.display) or str(akses.user_id), 32)


def waktu_sekarang() -> str:
    """Waktu lokal saat ini dalam format ISO singkat.

    Returns:
        String timestamp untuk disimpan di database.
    """
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
