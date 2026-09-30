"""Templat dan penyimpanan ucapan otomatis per grup.

Ucapan selamat datang dan perpisahan bisa berbeda tiap grup, jadi teksnya
disimpan di ``data/ucapan.json`` dengan kunci ``chat_id``. Templatnya memakai
penanda sederhana sehingga mudah diubah tanpa menyentuh kode:

- ``{nama}`` - nama tampilan user yang bergabung atau keluar.
- ``{grup}`` - nama grup.
- ``{jumlah}`` - jumlah anggota grup setelah perubahan.
- ``{baris}`` - pemisah garis ``-``, dipakai untuk merapikan blok.

Semua teks tanpa emoji: judul memakai huruf kapital bergaris ``=`` dan isi
memakai label rata kiri.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import config
from utils.tampilan import bersih, judul, potong

logger = logging.getLogger(__name__)

SELAMAT_DATANG: str = (
    "{judul}\n"
    "\n"
    "Selamat datang, {nama}, di {grup}.\n"
    "\n"
    "{baris}\n"
    "Status    : sudah bergabung\n"
    "Anggota   : {jumlah} orang\n"
    "\n"
    "Baca aturan grup dulu. Mention {ctx} kalau butuh bantuan."
)

PERPISAHAN: str = (
    "{judul}\n"
    "\n"
    "Sampai jumpa, {nama}.\n"
    "\n"
    "{baris}\n"
    "Status    : sudah keluar dari {grup}\n"
    "Anggota   : {jumlah} orang tersisa\n"
    "\n"
    "Terima kasih sudah membantu di grup ini."
)

PENANDA: tuple[str, ...] = ("{nama}", "{grup}", "{jumlah}", "{baris}", "{ctx}")

_TOKEN = re.compile(r"\{(nama|grup|jumlah|baris|ctx|judul)\}")

# Batas aman agar template yang terlalu panjang tidak menabrak limit pesan
# Telegram (4096 karakter) setelah dirender.
BATAS_PANJANG: int = 900

_cache: dict[int, dict[str, str]] | None = None

_JENIS: tuple[str, str] = ("salam", "pamit")


def _path() -> Path:
    """Lokasi berkas penyimpanan ucapan.

    Returns:
        Path berkas JSON, foldernya sudah dipastikan ada.
    """
    path = config.DATA_DIR / "ucapan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _muat() -> dict[int, dict[str, str]]:
    """Baca seluruh ucapan yang tersimpan dari disk.

    Returns:
        Dictionary ``chat_id -> {"salam": ..., "pamit": ...}``.
        Kosong bila berkas belum ada atau isinya rusak.
    """
    global _cache
    if _cache is not None:
        return _cache

    hasil: dict[int, dict[str, str]] = {}
    path = _path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for kunci, nilai in data.items():
                    if not isinstance(nilai, dict):
                        continue
                    simpan = {
                        slot: str(nilai[slot])[:BATAS_PANJANG]
                        for slot in _JENIS
                        if isinstance(nilai.get(slot), str) and nilai[slot].strip()
                    }
                    if simpan:
                        hasil[int(kunci)] = simpan
        except (OSError, ValueError, TypeError) as exc:
            logger.warning(
                "Gagal membaca %s: %s - pakai template bawaan.", path.name, exc
            )

    _cache = hasil
    return hasil


def _tulis(data: dict[int, dict[str, str]]) -> None:
    """Tulis seluruh ucapan ke disk.

    Args:
        data: Isi terbaru yang akan ditulis.
    """
    global _cache
    _cache = data
    path = _path()
    try:
        path.write_text(
            json.dumps(
                {str(kunci): nilai for kunci, nilai in data.items()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.error("Gagal menulis %s: %s", path.name, exc)


def template(jenis: str) -> str:
    """Ambil template bawaan untuk sebuah jenis ucapan.

    Urutan prioritas: teks kustom per grup, lalu nilai dari ``.env``
    (``WELCOME_TEXT`` / ``GOODBYE_TEXT``), lalu template bawaan di sini.

    Args:
        jenis: ``"salam"`` atau ``"pamit"``.

    Returns:
        String template, atau string kosong bila jenis tidak dikenal.
    """
    if jenis == "salam":
        return config.WELCOME_TEXT or SELAMAT_DATANG
    if jenis == "pamit":
        return config.GOODBYE_TEXT or PERPISAHAN
    return ""


def setelan(chat_id: int, jenis: str, teks: str | None) -> bool:
    """Simpan atau hapus template khusus untuk satu grup.

    Args:
        chat_id: ID grup.
        jenis: ``"salam"`` atau ``"pamit"``.
        teks: Teks baru. ``None`` atau string kosong berarti kembali ke
            template bawaan.

    Returns:
        ``True`` bila ada perubahan yang berhasil disimpan.
    """
    if jenis not in _JENIS:
        return False

    data = {kunci: dict(nilai) for kunci, nilai in _muat().items()}
    isi = dict(data.get(chat_id, {}))

    if teks is None or not teks.strip():
        if jenis not in isi:
            return False
        isi.pop(jenis)
    else:
        isi[jenis] = teks.strip()[:BATAS_PANJANG]

    if isi:
        data[chat_id] = isi
    else:
        data.pop(chat_id, None)

    _tulis(data)
    return True


def ambil(chat_id: int, jenis: str) -> str:
    """Ambil template yang berlaku untuk satu grup.

    Args:
        chat_id: ID grup.
        jenis: ``"salam"`` atau ``"pamit"``.

    Returns:
        Template milik grup bila ada, selain itu template bawaan.
    """
    return _muat().get(chat_id, {}).get(jenis) or template(jenis)


def render(
    teks: str,
    nama: str,
    grup: str,
    jumlah: int,
    ctx_teks: str = "-",
) -> str:
    """Ganti penanda dalam template dengan data nyata.

    Args:
        teks: Template yang berisi penanda.
        nama: Nama user yang bergabung atau keluar.
        grup: Nama grup.
        jumlah: Jumlah anggota grup setelah perubahan.
        ctx_teks: Sebutan akun bot untuk ditampilkan di template.

    Returns:
        Teks final siap kirim, tanpa emoji dan tanpa penanda tersisa.
    """
    nilai = {
        "nama": potong(bersih(nama), 40) or "user",
        "grup": potong(bersih(grup), 40) or "grup ini",
        "jumlah": str(jumlah),
        "baris": "-" * 20,
        "ctx": potong(bersih(ctx_teks), 40) or "akun ini",
        "judul": "",
    }
    hasil = _TOKEN.sub(lambda cocok: nilai[cocok.group(1)], teks)
    return potong(hasil, 2000)


_JUDUL: dict[str, str] = {
    "salam": "selamat datang",
    "pamit": "sampai jumpa",
}


def pesan(chat_id: int, jenis: str, nama: str, grup: str, jumlah: int, ctx_teks: str) -> str:
    """Render ucapan lengkap dalam satu langkah.

    Penanda ``{judul}`` diganti judul otomatis yang sesuai jenis ucapan,
    jadi template tidak perlu tahu cara membuat garis pemisah.

    Args:
        chat_id: ID grup asal ucapan.
        jenis: ``"salam"`` atau ``"pamit"``.
        nama: Nama user yang bergabung atau keluar.
        grup: Nama grup.
        jumlah: Jumlah anggota grup.
        ctx_teks: Sebutan akun bot.

    Returns:
        String final yang siap dikirim.
    """
    template_teks = ambil(chat_id, jenis).replace(
        "{judul}", judul(_JUDUL.get(jenis, "ucapan"))
    )
    return render(template_teks, nama, grup, jumlah, ctx_teks)


def ringkas(teks: str) -> str:
    """Versi pendek dari sebuah template, untuk ditampilkan ke admin.

    Args:
        teks: Template yang akan diringkas.

    Returns:
        Judul, isi ringkas, dan daftar penanda yang tersedia.
    """
    isi = potong(bersih(teks.replace("\n", " ")), 260)
    return (
        judul("templat aktif")
        + "\n"
        + isi
        + "\n\nPenanda: "
        + ", ".join(PENANDA)
        + "\n{judul} diganti otomatis menjadi judul dengan garis pemisah."
    )
