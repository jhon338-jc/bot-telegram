"""Perintah ``/menu``: menu tombol untuk userbot.

Dua tampilan tersedia:

- **Menu penuh** (dikirim sebagai foto) - dipakai setiap kali ``/menu``
  dipanggil. Foto profil bot ditampilkan bersama daftar tombol.
- **Menu sederhana** - versi teks pendek tanpa foto, untuk akses cepat.

Gambar yang dikirim ditentukan berurutan:

1. ``MENU_IMAGE`` di ``.env``, yaitu path relatif dari folder project.
2. Berkas gambar pertama di ``data/foto/`` (jpg, jpeg, png, webp).
3. Foto profil Telegram akun ini, diunduh ke cache lalu dikirim ulang.

Semua teks dan label tombol tanpa emoji.
"""

from __future__ import annotations

import logging
from pathlib import Path

from telethon.tl.custom import Button

import config
from utils.commands import command_pattern, new_message
from utils.context import Context
from utils.permissions import periksa_pemohon
from utils.ratelimit import send_limiter
from utils.tampilan import baris, judul, potong, sub

logger = logging.getLogger(__name__)

COMMAND = "menu"

AKAR: Path = config.BASE_DIR

_GAMBAR_DIJKAN: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp")

# Nama berkas cache foto profil, tidak boleh dianggap gambar menu custom.
_NAMA_CACHE: frozenset[str] = frozenset({"profil.jpg"})

# Nama cache foto profil yang diunduh sekali lalu dipakai ulang.
_CACHE_FOTO: Path | None = None

# Definisi tombol dipisah dari objek Button supaya label, urutan, dan
# keterangannya bisa dibaca tanpa menyentuh Telethon (Button.text adalah
# classmethod, jadi labelnya tidak bisa diambil dari objek hasil).
# Format: (label, perintah yang dikirim saat ditekan, keterangan).
TOMBOL_UMUM: tuple[tuple[tuple[str, str, str], ...], ...] = (
    (
        ("/ID SAYA", "/id", "Lihat ID, status, dan role kamu"),
        ("/HALO", "/halo", "Sapaan personal beserta role"),
    ),
    (
        ("/PING", "/ping", "Cek bot masih responsif"),
        ("/HELP", "/help", "Daftar semua perintah"),
    ),
    (
        ("/GROUPS", "/groups", "Daftar grup yang diikuti akun ini"),
        ("/ECHO", "/echo", "Ulangi teks yang kamu kirim"),
    ),
    (
        ("/MENU SEDERHANA", "/menu sederhana", "Menu versi teks singkat"),
    ),
)

TOMBOL_ADMIN: tuple[tuple[tuple[str, str, str], ...], ...] = (
    (
        ("/ADMIN", "/admin", "Panel admin dan konfigurasi"),
        ("/PERMS", "/perms", "Hak akses user di grup ini"),
    ),
    (
        ("/MEMBERS", "/members", "Daftar anggota grup beserta role"),
        ("/ADMINS", "/admins", "Daftar admin dan pemilik grup"),
    ),
    (
        ("/SALAM", "/salam", "Atur ucapan selamat datang"),
        ("/PAMIT", "/pamit", "Atur ucapan perpisahan"),
    ),
)


def definisi_tombol(boleh_admin: bool) -> list[tuple[tuple[str, str, str], ...]]:
    """Gabungkan definisi tombol umum dan admin sesuai hak pemohon.

    Args:
        boleh_admin: ``True`` bila tombol admin ikut ditampilkan.

    Returns:
        Daftar baris tombol, tiap baris berisi beberapa definisi tombol.
    """
    daftar = list(TOMBOL_UMUM)
    if boleh_admin:
        daftar.extend(TOMBOL_ADMIN)
    return daftar


def tombol(boleh_admin: bool) -> list[list[Button]]:
    """Bangun objek tombol Telethon dari definisinya.

    Args:
        boleh_admin: ``True`` bila tombol admin ikut ditampilkan.

    Returns:
        Daftar baris tombol siap pakai pada ``event.reply``.
    """
    return [
        [Button.text(perintah, resize=True) for _, perintah, _ in baris_tombol]
        for baris_tombol in definisi_tombol(boleh_admin)
    ]


def _cari_gambar() -> Path | None:
    """Cari berkas gambar menu di project.

    Returns:
        Path gambar yang bisa dikirim, atau ``None`` bila tidak ada.
    """
    if config.MENU_IMAGE:
        kandidat = Path(config.MENU_IMAGE)
        if not kandidat.is_absolute():
            kandidat = AKAR / kandidat
        if kandidat.is_file():
            return kandidat
        logger.warning("MENU_IMAGE tidak ditemukan: %s", kandidat)

    if config.IMAGE_DIR.is_dir():
        for suffix in _GAMBAR_DIJKAN:
            # Cache foto profil dilewati: kalau ikut terambil, gambar custom
            # milik user akan tersembunyi oleh hasil unduhan otomatis.
            found = sorted(
                Path(item)
                for item in config.IMAGE_DIR.glob(f"*{suffix}")
                if Path(item).name.lower() not in _NAMA_CACHE
            )
            if found:
                return found[0]

    return None


async def _foto_profil(ctx: Context) -> Path | None:
    """Unduh foto profil Telegram sekali lalu pakai cache-nya.

    Returns:
        Path gambar di cache, atau ``None`` bila akun tidak punya foto.
    """
    global _CACHE_FOTO
    if _CACHE_FOTO is not None and _CACHE_FOTO.is_file():
        return _CACHE_FOTO

    config.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    tujuan = config.IMAGE_DIR / "profil.jpg"
    try:
        hasil = await ctx.client.download_profile_photo(ctx.me, file=str(tujuan))
    except Exception as exc:  # noqa: BLE001 - foto profil bersifat opsional
        logger.warning("Gagal unduh foto profil: %s", exc)
        return None

    if hasil:
        _CACHE_FOTO = Path(hasil)
        return _CACHE_FOTO
    return None


async def gambar_menu(ctx: Context) -> Path | None:
    """Tentukan sumber gambar untuk ``/menu``.

    Args:
        ctx: Konteks bersama berisi klien Telethon.

    Returns:
        Path gambar yang siap dikirim, atau ``None`` bila tidak ada sumber
        gambar sama sekali (menu tetap dikirim sebagai teks).
    """
    lokal = _cari_gambar()
    if lokal is not None:
        return lokal
    return await _foto_profil(ctx)


def tombol(boleh_admin: bool) -> list[list[Button]]:
    """Bangun objek tombol Telethon dari definisinya.

    Args:
        boleh_admin: ``True`` bila tombol admin ikut ditampilkan.

    Returns:
        Daftar baris tombol siap pakai pada ``event.reply``.
    """
    return [
        [Button.text(perintah, resize=True) for _, perintah, _ in baris_tombol]
        for baris_tombol in definisi_tombol(boleh_admin)
    ]


def keterangan_tombol(boleh_admin: bool) -> list[str]:
    """Terjemahkan definisi tombol menjadi teks keterangan yang rapi.

    Args:
        boleh_admin: ``True`` bila tombol admin ikut ditampilkan.

    Returns:
        Baris ``"LABEL - keterangan"`` untuk setiap tombol.
    """
    hasil: list[str] = []
    for baris_tombol in definisi_tombol(boleh_admin):
        for label, _, keterangan in baris_tombol:
            hasil.append(f"{label:<20} - {keterangan}")
    return hasil


def isi_penuh(ctx: Context, boleh_admin: bool) -> str:
    """Susun teks lengkap untuk foto ``/menu``.

    Args:
        ctx: Konteks bersama berisi profil akun.
        boleh_admin: ``True`` bila pemohon adalah admin.

    Returns:
        Teks menu penuh siap kirim.
    """
    bagian = [
        judul(f"menu {ctx.display_name}"),
        "",
        baris("ID akun", ctx.me_id),
        baris(
            "Username",
            f"@{ctx.username}" if ctx.username else "tidak punya username",
        ),
        baris("Di grup", f"sebut {ctx.mention} atau reply pesan bot"),
        "",
        sub("cara pakai", 26),
        "1. Ketuk tombol di bawah foto ini.",
        "2. Semua perintah tetap bisa diketik manual, contoh /menu.",
        "3. Foto ini cuma tombol pintasan, bukan pengganti perintah.",
        "",
        sub("tombol yang tampil", 26),
    ]
    bagian.extend(keterangan_tombol(boleh_admin))
    bagian.extend(
        [
            "",
            "Ketuk MENU SEDERHANA untuk versi teks singkat.",
            "Ketuk HELP untuk daftar lengkap semua perintah.",
        ]
    )
    return "\n".join(bagian)


def isi_sederhana(ctx: Context, boleh_admin: bool) -> str:
    """Susun teks versi singkat untuk tombol ``/MENU SEDERHANA``.

    Args:
        ctx: Konteks bersama berisi profil akun.
        boleh_admin: ``True`` bila pemohon adalah admin.

    Returns:
        Teks menu singkat siap kirim.
    """
    bagian = [
        judul("menu sederhana"),
        baris("Akun", ctx.display_name),
        baris("ID", ctx.me_id),
        "",
    ]
    for baris_tombol in definisi_tombol(boleh_admin):
        bagian.append(" | ".join(label for label, _, _ in baris_tombol))
    bagian.extend(
        [
            "",
            "Ketuk MENU SEDERHANA lagi untuk refresh.",
            "Butuh daftar lengkap? Ketuk HELP.",
        ]
    )
    return "\n".join(bagian)


async def kirim_menu(event, ctx: Context, *, sederhana: bool = False) -> None:
    """Kirim menu lengkap atau sederhana sesuai tombol yang ditekan.

    Args:
        event: Event pesan masuk dari Telethon.
        ctx: Konteks bersama berisi klien, database, dan profil akun.
        sederhana: ``True`` untuk menu teks singkat tanpa foto.
    """
    akses = await periksa_pemohon(event, ctx)
    boleh_admin = akses.can_manage

    if sederhana:
        await send_limiter.wait()
        await event.reply(
            isi_sederhana(ctx, boleh_admin),
            buttons=tombol(boleh_admin),
        )
        return

    gambar = await gambar_menu(ctx)
    teks = isi_penuh(ctx, boleh_admin)

    await send_limiter.wait()
    if gambar is None:
        logger.info("Foto menu belum ada, /menu dikirim sebagai teks polos.")
        await event.reply(teks, buttons=tombol(boleh_admin))
        return

    # Telethon tidak punya parameter `caption` terpisah: teks di photo
    # dikirim sebagai argumen pesan biasa, sementara file-nya lewat `file`.
    await event.reply(
        potong(teks, 1000),
        file=gambar,
        buttons=tombol(boleh_admin),
    )
    logger.info("/menu dikirim ke %s (foto: %s).", event.chat_id, gambar.name)


def register(ctx: Context) -> None:
    """Daftarkan handler ``/menu`` beserta handler tombol singkat.

    Args:
        ctx: Konteks bersama yang menyimpan klien Telethon.
    """

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND)))
    async def _on_menu(event) -> None:
        await kirim_menu(event, ctx)

    @ctx.client.on(new_message(pattern=command_pattern("menu sederhana")))
    async def _on_menu_sederhana(event) -> None:
        await kirim_menu(event, ctx, sederhana=True)
