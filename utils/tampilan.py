"""Utilitas tampilan teks untuk semua balasan bot.

Aturan tampilan project ini:

- **Tanpa emoji sama sekali.** Judul memakai huruf kapital dengan garis
  ``=`` di bawahnya, dan isi memakai label rata kiri dengan ``:`` sebagai
  pemisah. Tidak ada simbol dekoratif apa pun.
- **Rapi di layar sempit.** Lebar label dikunci agar kolom selalu lurus
  walaupun isi varies panjang.
- **Aman dari emoji yang lolos.** :func:`bersih` menyaring karakter emoji
  atau simbol dekoratif yang mungkin terbawa dari data Telegram (misal
  nama grup atau nama depan user), sehingga tidak ada ":" atau "." polos
  yang ikut hilang karena masih terikat di dalam teks emoji.
"""

from __future__ import annotations

LEBAR_JUDUL: int = 34
LEBAR_LABEL: int = 18
LEBAR_PANJANG: int = 40

# Rentang karakter yang dibuang oleh bersih(): emoji, tanda varyasi,
# zero-width joiner, dan beberapa blok simbol dekoratif.
_RENTANG_BUANG: tuple[tuple[int, int], ...] = (
    (0x00A9, 0x00A9),  # copyright
    (0x00AE, 0x00AE),  # registered
    (0x200B, 0x200F),  # zero-width + directional marks
    (0x2028, 0x202F),  # line/paragraph separator
    (0x20E3, 0x20E3),  # combining enclosing keycap
    (0x2122, 0x2122),  # trademark
    (0x2190, 0x21FF),  # arrows
    (0x2300, 0x23FF),  # misc technical (termometer, hourglass, ...)
    (0x2460, 0x24FF),  # enclosed alphanumerics
    (0x25A0, 0x27BF),  # geometric shapes + misc symbols + dingbats
    (0x2934, 0x2935),  # arrows
    (0x2B00, 0x2BFF),  # misc symbols and arrows
    (0x3030, 0x3030),  # wavy dash
    (0x303D, 0x303D),  # part alternation mark
    (0x3297, 0x3297),  # circled congratulation
    (0x3299, 0x3299),  # circled secret
    (0xFE0E, 0xFE0F),  # emoji variation selectors
    (0x1F000, 0x1FAFF),  # emoji blocks
    (0x1F1E6, 0x1F1FF),  # regional indicators (flag halves)
)


import re

# Runtunan spaks yang tertinggal setelah emoji dibuang.
_SPASI_BERUNTUN = re.compile(r"[ \t]{2,}")


def bersih(teks: str) -> str:
    """Buang karakter emoji dan simbol dekoratif dari sebuah teks.

    Dipakai untuk data yang berasal dari Telegram (nama grup, nama user)
    supaya tidak merusak tata letak balasan bot. Spasi ganda yang tertinggal
    ikut dirapatkan agar kolom tetap lurus.

    Args:
        teks: Teks mentah, boleh ``None``.

    Returns:
        Teks yang sudah dibersihkan. ``None`` menjadi string kosong.
    """
    if not teks:
        return ""
    keluar = []
    for karakter in teks:
        kode = ord(karakter)
        if any(awal <= kode <= akhir for awal, akhir in _RENTANG_BUANG):
            continue
        keluar.append(karakter)
    return _SPASI_BERUNTUN.sub(" ", "".join(keluar)).strip()


def judul(teks: str, lebar: int = LEBAR_JUDUL) -> str:
    """Buat judul bagian: huruf kapital dengan garis ``=`` di bawahnya.

    Args:
        teks: Judul bagian.
        lebar: Panjang garis pemisah.

    Returns:
        Dua baris: judul kapital dan garis pemisah.
    """
    return f"{bersih(teks).upper()}\n{'=' * lebar}"


def sub(teks: str, lebar: int = LEBAR_JUDUL) -> str:
    """Buat subjudul dengan garis ``-`` yang lebih pendek.

    Args:
        teks: Judul subbagian.
        lebar: Panjang garis pemisah.

    Returns:
        Dua baris: judul kapital dan garis pemisah tipis.
    """
    return f"{bersih(teks).upper()}\n{'-' * lebar}"


def baris(label: str, nilai: object, lebar: int = LEBAR_LABEL) -> str:
    """Buat satu baris ``label : nilai`` dengan kolom lurus.

    Args:
        label: Nama field, misal ``"ID akun"``.
        nilai: Isi field.
        lebar: Lebar kolom label.

    Returns:
        String satu baris.
    """
    return f"{bersih(label):<{lebar}} : {bersih(str(nilai))}"


def daftar(baris_baris: list[str], lebar: int = LEBAR_JUDUL) -> str:
    """Buat daftar bernomor dengan pemisah ``|``.

    Args:
        baris_baris: Satu baris teks per item.
        lebar: Lebar garis pemisah bagian.

    Returns:
        Blok daftar siap tempel, atau string kosong bila daftarnya kosong.
    """
    if not baris_baris:
        return ""
    isi = "\n".join(
        f"{nomor}. {bersih(isi_baris)}" for nomor, isi_baris in enumerate(baris_baris, 1)
    )
    return f"{garis(lebar)}\n{isi}"


def garis(lebar: int = LEBAR_JUDUL) -> str:
    """Buat garis pemisah tipis.

    Args:
        lebar: Panjang garis.

    Returns:
        Garis ``-`` sepanjang ``lebar``.
    """
    return "-" * lebar


def potong(teks: str, panjang: int = 60) -> str:
    """Potong teks panjang dan tambahkan penanda tiga titik.

    Args:
        teks: Teks asal.
        panjang: Panjang maksimum sebelum dipotong.

    Returns:
        Teks yang tidak lebih dari ``panjang`` karakter.
    """
    bersih_teks = bersih(teks)
    if len(bersih_teks) <= panjang:
        return bersih_teks
    return bersih_teks[: panjang - 3] + "..."


def blok(judul_teks: str, isi_baris: list[str], lebar: int = LEBAR_JUDUL) -> str:
    """Rakit judul + garis + isi baris ``label : nilai``.

    Args:
        judul_teks: Judul bagian.
        isi_baris: Pasangan ``(label, nilai)`` untuk setiap baris.
        lebar: Lebar garis pemisah judul.

    Returns:
        Blok teks siap kirim.
    """
    bagian = [judul(judul_teks, lebar)]
    bagian.extend(baris(label, nilai) for label, nilai in isi_baris)
    return "\n".join(bagian)
