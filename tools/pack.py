"""Sinkronisasi folder ``data/`` ke repo GitHub privat dalam bentuk terenkripsi.

Folder ``data/`` berisi file session Telethon, database SQLite, dan template
ucapan per grup. Isinya setara akses penuh ke akun Telegram, jadi tidak pernah
ikut masuk repo publik. Modul ini membungkus folder tersebut menjadi satu
berkas ``data.tar.gz.enc``, lalu mengirimkannya lewat GitHub Contents API ke
repo privat.

Perintah:
    python tools/pack.py push    # unggah data/ ke repo privat
    python tools/pack.py pull    # unduh data/ dari repo privat
    python tools/pack.py check   # cek isi data/ + uji enkripsi, tanpa jaringan

Environment (semuanya lewat GitHub Secrets di repo publik):
    DATA_REPO  "owner/nama-repo" repo privat, mis. "jhon338-jc/bot-telegram-data"
    DATA_PAT   token GitHub yang boleh tulis pada repo DATA_REPO saja
    ENC_PASS   frasa sandi enkripsi; di PC diisi lewat environment

Kenapa pakai Contents API dan bukan ``git clone``: modul ini jalan di PC
tanpa git, di runner tanpa checkout kedua, dan tidak pernah menyalin isi repo
privat ke disk runner.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import io
import json
import os
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

BERKAS = "data.tar.gz.enc"
KUA = "https://api.github.com"
# Penanda format + pengikat tambahan, supaya berkas hasil enkripsi tidak
# bisa dipakai ulang di konteks lain walau frasa sandinya bocor.
MAGIC = b"UGAB1"
AAD = b"userbot-data:v1"
PANJANG_SALT = 16
PANJANG_NONCE = 12
# scrypt: butuh 128 * r * n = 32 MB memori per pemanggilan, jadi maxmem
# dinaikkan di atas default OpenSSL (32 MB) yang bakalan ditolak.
KOSUT_SCRYPT = {"n": 1 << 15, "r": 8, "p": 1, "dklen": 32, "maxmem": 64 << 20}


class PackError(RuntimeError):
    """Kegagalan yang bisa diperbaiki sendiri oleh user."""


def sandi() -> str:
    """Baca frasa sandi dari environment.

    Returns:
        Frasa sandi yang tidak kosong.

    Raises:
        PackError: Bila ``ENC_PASS`` belum diisi.
    """
    nilai = os.environ.get("ENC_PASS", "")
    if not nilai:
        raise PackError(
            "ENC_PASS belum diisi. Isi lewat GitHub Secret (server) atau "
            "environment (PC)."
        )
    return nilai


def kredensial() -> tuple[str, str]:
    """Baca repo tujuan dan token dari environment.

    Returns:
        Tuple ``(owner/repo, token)``.

    Raises:
        PackError: Bila ``DATA_REPO`` atau ``DATA_PAT`` belum diisi.
    """
    repo = os.environ.get("DATA_REPO", "").strip()
    token = os.environ.get("DATA_PAT", "").strip()
    hilang = [
        nama
        for nama, nilai in (("DATA_REPO", repo), ("DATA_PAT", token))
        if not nilai
    ]
    if hilang:
        raise PackError(
            "Environment belum lengkap: " + ", ".join(hilang) + ". "
            "Keduanya harus diisi lewat GitHub Secret."
        )
    if repo.count("/") != 1:
        raise PackError(f"DATA_REPO harus berformat 'owner/nama-repo', dapat: {repo}")
    return repo, token


def kunci(frasa: str, salt: bytes) -> bytes:
    """Turunkkan frasa sandi menjadi kunci enkripsi 32 byte.

    Args:
        frasa: Frasa sandi dari environment.
        salt: Garam acak 16 byte.

    Returns:
        Kunci turunan siap pakai.
    """
    return hashlib.scrypt(
        frasa.encode("utf-8"), salt=salt, **KOSUT_SCRYPT
    )


def tutup(isi: bytes, frasa: str) -> bytes:
    """Enkripsi satu bundel data.

    Args:
        isi: Data mentah yang mau disimpan.
        frasa: Frasa sandi.

    Returns:
        Berkas terenkripsi: magic, salt, nonce, lalu ciphertext.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = os.urandom(PANJANG_SALT)
    nonce = os.urandom(PANJANG_NONCE)
    ciphertext = AESGCM(kunci(frasa, salt)).encrypt(nonce, isi, AAD)
    return MAGIC + salt + nonce + ciphertext


def buka(gumpalan: bytes, frasa: str) -> bytes:
    """Dekripsi satu bundel data.

    Args:
        gumpalan: Isi berkas terenkripsi.
        frasa: Frasa sandi.

    Returns:
        Data asli sebelum dienkripsi.

    Raises:
        PackError: Bila format berkas rusak atau frasa sandinya salah.
    """
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    kepala = len(MAGIC) + PANJANG_SALT + PANJANG_NONCE
    if len(gumpalan) < kepala or not gumpalan.startswith(MAGIC):
        raise PackError("Format berkas terenkripsi tidak dikenali.")
    salt = gumpalan[len(MAGIC) : len(MAGIC) + PANJANG_SALT]
    nonce = gumpalan[len(MAGIC) + PANJANG_SALT : kepala]
    try:
        return AESGCM(kunci(frasa, salt)).decrypt(nonce, gumpalan[kepala:], AAD)
    except InvalidTag:
        raise PackError(
            "Frasa sandi salah, atau berkas sudah rusak. ENC_PASS di server "
            "harus sama persis dengan yang dipakai saat push."
        ) from None


def pemasang_aman(member: tarfile.TarInfo) -> bool:
    """Periksa satu anggota arsip sebelum diekstrak.

    Menolak path absolut, ``..``, tautan simbolik, dan device node supaya
    bundel yang rusak atau disisipi orang lain tidak menulis di luar
    folder ``data/``.

    Args:
        member: Anggota arsip yang akan diekstrak.

    Returns:
        ``True`` bila aman ditulis ke disk.
    """
    if member.issym() or member.islnk() or member.isdev():
        return False
    bagian = Path(member.name).parts
    return not (
        member.name.startswith(("/", "\\"))
        or os.path.isabs(member.name)
        or ".." in bagian
    )


def kemas() -> bytes:
    """Kompres seluruh isi folder ``data/``.

    Returns:
        Bundel tar.gz berisi direktori ``data/``.
    """
    if not DATA_DIR.is_dir():
        raise PackError(f"Folder {DATA_DIR} tidak ada. Jalankan bot sekali di PC dulu.")
    buffer = io.BytesIO()
    # mtime dinormalkan supaya bundel hanya berubah kalau isinya berubah.
    with tarfile.open(fileobj=buffer, mode="w:gz") as arsip:
        for path in sorted(DATA_DIR.rglob("*")):
            if not path.is_file() or path.name == "stop.flag":
                continue
            info = arsip.gettarinfo(str(path), arcname=f"data/{path.relative_to(DATA_DIR).as_posix()}")
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with path.open("rb") as f:
                arsip.addfile(info, f)
    return buffer.getvalue()


def tulis(path: Path, isi: bytes) -> None:
    """Tulis satu berkas di dalam folder ``data/``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(isi)


def ungkap(bundel: bytes) -> int:
    """Ekstrak bundel terenkripsi ke folder ``data/`` lokal.

    Args:
        bundel: Hasil dekripsi berkas ``data.tar.gz.enc``.

    Returns:
        Banyaknya berkas yang ditulis.

    Raises:
        PackError: Bila bundel bukan arsip yang aman.
    """
    ditulis = 0
    with tarfile.open(fileobj=io.BytesIO(bundel), mode="r:gz") as arsip:
        for member in arsip.getmembers():
            if not pemasang_aman(member):
                raise PackError(f"Anggota arsip ditolak: {member.name}")
            tujuan = BASE_DIR / member.name
            if member.isdir():
                tujuan.mkdir(parents=True, exist_ok=True)
                continue
            handle = arsip.extractfile(member)
            if handle is None:
                continue
            tulis(tujuan, handle.read())
            ditulis += 1
    return ditulis


def panggil_api(metode: str, jalur: str, token: str, payload: dict | None = None) -> dict:
    """Panggil GitHub Contents API.

    Args:
        metode: ``GET`` atau ``PUT``.
        jalur: Jalur relatif, misal ``repos/{repo}/contents/{berkas}``.
        token: Token GitHub.
        payload: Badan permintaan untuk ``PUT``.

    Returns:
        Respons GitHub dalam bentuk dict.

    Raises:
        PackError: Bila GitHub menolak atau tidak bisa dihubungi.
    """
    request = urllib.request.Request(
        KUA + "/" + jalur,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        method=metode,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "telegram-userbot-pack",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as jawaban:
            isi = jawaban.read().decode("utf-8")
            return json.loads(isi) if isi else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(detail).get("message", detail)
        except json.JSONDecodeError:
            pass
        if exc.code == 404 and metode == "GET":
            raise PackError(
                f"Repo privat {path_repo()} belum berisi {BERKAS}. Di PC jalankan "
                "perintah: python tools/pack.py push"
            ) from None
        if exc.code == 403:
            raise PackError(
                "GitHub menolak token (403). Cek DATA_PAT: token harus punya "
                "izin tulis (Contents: read and write) pada repo privat saja."
            ) from None
        raise PackError(f"GitHub API {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise PackError(f"Tidak bisa menghubungi GitHub: {exc.reason}") from None


def path_repo() -> str:
    """Kembalikan ``owner/nama-repo`` tujuan.

    Returns:
        Nilai ``DATA_REPO`` dari environment.

    Raises:
        PackError: Bila ``DATA_REPO`` belum diisi.
    """
    repo = os.environ.get("DATA_REPO", "").strip()
    if not repo:
        raise PackError("DATA_REPO belum diisi.")
    return repo


def tarik(frasa: str) -> int:
    """Unduh bundel terenkripsi lalu ekstrak ke ``data/``.

    Args:
        frasa: Frasa sandi.

    Returns:
        Banyaknya berkas yang ditulis.
    """
    repo, token = kredensial()
    respons = panggil_api(
        "GET", f"repos/{repo}/contents/{BERKAS}", token
    )
    if respons.get("encoding") != "base64":
        raise PackError("Respons GitHub tidak berisi file base64.")
    try:
        gumpalan = base64.b64decode(respons["content"])
    except (KeyError, binascii.Error) as exc:
        raise PackError(f"Isi {BERKAS} rusak: {exc}") from None

    ditulis = ungkap(buka(gumpalan, frasa))
    session = (DATA_DIR / "userbot.session").exists()
    print(f"Tarik {BERKAS} dari {repo}: {ditulis} berkas, session ada: {session}")
    if not session:
        raise PackError(
            "Bundel terenkripsi tidak berisi userbot.session. di PC: "
            "python main.py --qr"
        )
    return ditulis


def dorong(frasa: str) -> None:
    """Kompres, enkripsi, lalu unggah ``data/`` ke repo privat.

    Args:
        frasa: Frasa sandi.

    Raises:
        PackError: Bila ``data/userbot.session`` tidak ada, sehingga tidak
            ada yang layak diunggah.
    """
    if not (DATA_DIR / "userbot.session").exists():
        # Penjaga penting: di runner, ``push`` tetap jalan meski ``pull``
        # gagal. Tanpa penjaga ini, folder data yang kosong menimpa bundel
        # yang sudah benar di repo privat.
        raise PackError(
            "data/userbot.session tidak ada, jadi tidak ada yang layak "
            "dorong. Jangan Dorong dari mesin yang gagal menarik data."
        )
    repo, token = kredensial()
    gumpalan = tutup(kemas(), frasa)
    isi = base64.b64encode(gumpalan).decode("ascii")
    jalur = f"repos/{repo}/contents/{BERKAS}"

    sha = None
    try:
        sha = panggil_api("GET", jalur, token).get("sha")
    except PackError as exc:
        if "belum berisi" not in str(exc):
            raise

    payload = {
        "message": "sinkronisasi data userbot",
        "content": isi,
        "branch": "main",
    }
    if sha:
        payload["sha"] = sha
    panggil_api("PUT", jalur, token, payload)
    print(f"Dorong {BERKAS} ke {repo}: {len(gumpalan)} byte terenkripsi.")


def cek() -> int:
    """Periksa isi ``data/`` dan uji enkripsi tanpa menyentuh jaringan.

    Returns:
        ``0`` bila data siap diunggah, selain itu ``1``.
    """
    print("Cek data userbot")
    print("=" * 64)
    if not DATA_DIR.is_dir():
        print(f"  Folder data  : TIDAK ADA ({DATA_DIR})")
        return 1
    session = DATA_DIR / "userbot.session"
    print(f"  Session      : {'ada' if session.exists() else 'TIDAK ADA'}")
    print(f"  Ukuran       : {session.stat().st_size} byte" if session.exists() else "")
    isi = sorted(p.relative_to(DATA_DIR).as_posix() for p in DATA_DIR.rglob("*") if p.is_file())
    print(f"  Isi data/    : {len(isi)} berkas")
    for nama in isi[:12]:
        print(f"    - {nama}")
    if len(isi) > 12:
        print(f"    ... {len(isi) - 12} berkas lain")

    if os.environ.get("ENC_PASS"):
        try:
            contoh = b"userbot-data: uji enkripsi"
            if buka(tutup(contoh, sandi()), sandi()) != contoh:
                print("  Enkripsi     : GAGAL (hasil tidak cocok)")
                return 1
            print("  Enkripsi     : aman (seal -> open cocok)")
        except PackError as exc:
            print(f"  Enkripsi     : GAGAL ({exc})")
            return 1
    else:
        print("  Enkripsi     : dilewati (ENC_PASS belum diisi)")

    print("=" * 64)
    if not session.exists():
        print("Belum ada session. Jalankan: python main.py --qr")
        return 1
    print("Siap. Unggah dengan: python tools/pack.py push")
    return 0


def main() -> int:
    """Titik masuk skrip.

    Returns:
        Exit code untuk skrip.
    """
    parser = argparse.ArgumentParser(
        prog="tools/pack.py",
        description="Sinkronisasi data/ terenkripsi ke repo GitHub privat.",
    )
    parser.add_argument(
        "aksi",
        choices=("push", "pull", "check"),
        help="push unggah, pull unduh, check periksa tanpa jaringan",
    )
    args = parser.parse_args()

    try:
        if args.aksi == "check":
            return cek()
        if args.aksi == "pull":
            tarik(sandi())
            return 0
        dorong(sandi())
        return 0
    except PackError as exc:
        print(f"GAGAL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())