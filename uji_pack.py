"""Uji ``tools/pack.py`` tanpa jaringan dan tanpa menyentuh data asli.

Yang diperiksa:
- enkripsi ``tutup``/``buka`` bolak-balik, termasuk frasa sandi salah
- format berkas terenkripsi (magic, salt, nonce, tag autentikasi)
- kompres ``data/`` lalu ekstrak balik tanpa kehilangan berkas
- penolakan arsip berbahaya (``../``, path absolut, symlink)
- pesan ``PackError`` yang bisa ditindaklanjuti

Jalankan:
    venv\\Scripts\\python.exe uji_pack.py

Semua tes memakai folder sementara, jadi ``data/`` asli tidak pernah
dibaca atau ditulis.
"""

from __future__ import annotations

import io
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tools.pack as pack  # noqa: E402

FRASA = "frasa-sandi-uji-12345"
LULUS = 0
GAGAL = 0


def cek(nama: str, hasil: bool) -> None:
    """Catat hasil satu tes.

    Args:
        nama: Keterangan tes.
        hasil: ``True`` bila tes lulus.
    """
    global LULUS, GAGAL
    if hasil:
        LULUS += 1
        print(f"  LULUS  {nama}")
    else:
        GAGAL += 1
        print(f"  GAGAL  {nama}")


def folder_sementara() -> Path:
    """Buat folder sementara untuk satu tes.

    Returns:
        Path folder yang sudah dibuat.
    """
    return Path(tempfile.mkdtemp(prefix="uji-pack-"))


def ditolak(aksi) -> bool:
    """Jalankan aksi dan kembalikan True bila PackError muncul.

    Args:
        aksi: Fungsi tanpa argumen yang harus ditolak.

    Returns:
        ``True`` bila aksi memang ditolak.
    """
    try:
        aksi()
    except pack.PackError:
        return True
    return False


def uji_enkripsi() -> None:
    """Enkripsi bolak-balik plus penanganan sandi salah dan berkas rusak."""
    isi = b"userbot-data: contoh isi session"
    gumpalan = pack.tutup(isi, FRASA)

    cek("berkas diawali magic", gumpalan.startswith(pack.MAGIC))
    cek(
        "ukuran = magic + salt + nonce + ciphertext + tag",
        len(gumpalan)
        == len(pack.MAGIC)
        + pack.PANJANG_SALT
        + pack.PANJANG_NONCE
        + len(isi)
        + 16,
    )
    cek("dekripsi kembali persis sama", pack.buka(gumpalan, FRASA) == isi)
    cek("isi tidak ditemukan polos di dalam berkas", isi not in gumpalan)
    cek("dua kali enkripsi beda salt", pack.tutup(isi, FRASA) != gumpalan)

    cek("frasa sandi salah ditolak", ditolak(lambda: pack.buka(gumpalan, "salah")))
    cek(
        "berkas terpotong ditolak",
        ditolak(lambda: pack.buka(gumpalan[:-4], FRASA)),
    )
    cek(
        "berkas acak ditolak",
        ditolak(lambda: pack.buka(b"bukan bundle sama sekali", FRASA)),
    )
    cek(
        "satu byte diubah dideteksi tag autentikasi",
        ditolak(
            lambda: pack.buka(gumpalan[:-1] + bytes([gumpalan[-1] ^ 1]), FRASA)
        ),
    )


def isi_data_sementara(data: Path) -> None:
    """Buat isi ``data/`` palsu untuk dipakai tes."""
    (data / "foto").mkdir(parents=True)
    (data / "userbot.session").write_bytes(b"SQLite format 3\x00" + b"\x00" * 64)
    (data / "bot.db").write_bytes(b"database" * 100)
    (data / "bot.db-wal").write_bytes(b"wal")
    (data / "ucapan.json").write_text('{"-100": "halo"}', encoding="utf-8")
    (data / "foto" / "profil.jpg").write_bytes(b"\xff\xd8\xff" + b"jpeg" * 50)
    (data / "stop.flag").write_text("2026-01-01T00:00:00", encoding="utf-8")


def uji_kemas() -> None:
    """Kompres ``data/`` dan pastikan isinya utuh serta aman."""
    akar = folder_sementara()
    try:
        data = akar / "data"
        isi_data_sementara(data)

        asli_base, asli_data = pack.BASE_DIR, pack.DATA_DIR
        pack.BASE_DIR, pack.DATA_DIR = akar, data
        try:
            bundel = pack.kemas()
        finally:
            pack.BASE_DIR, pack.DATA_DIR = asli_base, asli_data

        cek("bundel tidak kosong", len(bundel) > 0)
        cek("bundel bisa dibuka sebagai tar.gz", _bisa_buka(bundel))

        with tarfile.open(fileobj=io.BytesIO(bundel), mode="r:gz") as arsip:
            nama = {m.name for m in arsip.getmembers()}
        cek("session ikut terbundel", "data/userbot.session" in nama)
        cek("database ikut terbundel", "data/bot.db" in nama)
        cek("gambar ikut terbundel", "data/foto/profil.jpg" in nama)
        cek("stop.flag tidak ikut", "data/stop.flag" not in nama)
        cek(
            "semua nama relatif dan tanpa '..'",
            all(not n.startswith("/") and ".." not in Path(n).parts for n in nama),
        )

        # Ekstrak ke folder kosong, lalu bandingkan byte per byte.
        tujuan = akar / "hasil"
        pack.BASE_DIR = tujuan
        try:
            ditulis = pack.ungkap(bundel)
        finally:
            pack.BASE_DIR = asli_base
        cek("jumlah berkas hasil ekstrak", ditulis == 5)

        for relatif, asal in (
            ("data/userbot.session", data / "userbot.session"),
            ("data/bot.db", data / "bot.db"),
            ("data/ucapan.json", data / "ucapan.json"),
            ("data/foto/profil.jpg", data / "foto" / "profil.jpg"),
        ):
            hasil = (tujuan / relatif).read_bytes()
            cek(f"isi {relatif} utuh setelah ekstrak", hasil == asal.read_bytes())
        cek(
            "stop.flag tidak muncul setelah ekstrak",
            not (tujuan / "data" / "stop.flag").exists(),
        )
    finally:
        shutil.rmtree(akar, ignore_errors=True)


def uji_arsip_berbahaya() -> None:
    """Bundel berisi path traversal harus ditolak, bukan diekstrak."""
    for nama_berbahaya in (
        "../bocor.txt",
        "data/../../bocor.txt",
        "/tmp/bocor.txt",
    ):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as arsip:
            isi = b"bocor"
            info = tarfile.TarInfo(nama_berbahaya)
            info.size = len(isi)
            arsip.addfile(info, io.BytesIO(isi))
        cek(
            f"ditolak: {nama_berbahaya}",
            ditolak(lambda: pack.ungkap(buffer.getvalue())),
        )

    # Symlink ke /etc/passwd juga harus ditolak.
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as arsip:
        info = tarfile.TarInfo("data/jahat")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        arsip.addfile(info)
    cek("ditolak: symlink", ditolak(lambda: pack.ungkap(buffer.getvalue())))
    cek(
        "symlink tidak pernah ditulis ke disk",
        not (Path(tempfile.gettempdir()) / "jahat").exists(),
    )


def _bisa_buka(bundel: bytes) -> bool:
    """Coba buka bundel sebagai tar.gz.

    Args:
        bundel: Data hasil kompresi.

    Returns:
        ``True`` bila arsipnya valid.
    """
    try:
        with tarfile.open(fileobj=io.BytesIO(bundel), mode="r:gz") as arsip:
            arsip.getmembers()
    except tarfile.TarError:
        return False
    return True


def uji_dorong_tanpa_session() -> None:
    """``push`` harus menolak saat session tidak ada (penjaga anti-blan overwrite)."""
    akar = folder_sementara()
    try:
        data = akar / "data"
        data.mkdir(parents=True)
        (data / "bot.db").write_bytes(b"database tanpa session")

        asal_base, asli_data = pack.BASE_DIR, pack.DATA_DIR
        pack.BASE_DIR, pack.DATA_DIR = akar, data
        try:
            pesan = ""
            try:
                pack.dorong(FRASA)
            except pack.PackError as exc:
                pesan = str(exc)
        finally:
            pack.BASE_DIR, pack.DATA_DIR = asal_base, asli_data

        cek("dorong ditolak tanpa userbot.session", "tidak ada" in pesan)
        cek("penjaga menolak sebelum butuh token", "session" in pesan)
    finally:
        shutil.rmtree(akar, ignore_errors=True)


def main() -> int:
    """Jalankan seluruh tes.

    Returns:
        Exit code 0 bila semua tes lulus.
    """
    print("--- enkripsi ---")
    uji_enkripsi()
    print("--- kemas ---")
    uji_kemas()
    print("--- arsip berbahaya ---")
    uji_arsip_berbahaya()
    print("--- dorong tanpa session ---")
    uji_dorong_tanpa_session()
    print(f"HASIL: {LULUS} lulus, {GAGAL} gagal")
    return 0 if GAGAL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())