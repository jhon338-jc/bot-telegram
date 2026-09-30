"""Pemeriksa cepat karakter asing (CJK/SILA) yang tidak sengaja masuk kode."""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

KECUALI = (
    "EMOJI",
    "BOX DRAWINGS",
    "ARROW",
    "GEAR",
    "CROSS MARK",
    "BULLET",
    "DASH",
    "CHECK MARK",
    "LEFT-POINTING",
    "RIGHT-POINTING",
    "DEGREE",
    "HEAVY",
    "DOUBLE ANGLE",
    "HORIZONTAL ELLIPSIS",
    "MIDDLE DOT",
    "ZERO WIDTH",
)

BATAS_ATAS = 0x2100


def main() -> int:
    """Jalankan pemeriksaan dan kembalikan jumlah anomali."""
    total = 0
    for path in sorted(Path(".").rglob("*.py")):
        if "venv" in path.parts or "__pycache__" in path.parts:
            continue
        teks = path.read_text(encoding="utf-8", errors="replace")
        for nomor, baris in enumerate(teks.splitlines(), 1):
            for karakter in baris:
                kode = ord(karakter)
                if kode <= 127 or kode > 0xFFFF:
                    continue
                if kode >= BATAS_ATAS and not any(
                    k in unicodedata.name(karakter, "") for k in KECUALI
                ):
                    continue
                if any(k in unicodedata.name(karakter, "") for k in KECUALI):
                    continue
                print(f"{path}:{nomor} U+{kode:04X} {karakter} -> {baris.strip()[:70]}")
                total += 1
    print(f"anomali: {total}")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
