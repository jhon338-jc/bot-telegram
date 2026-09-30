"""Pembatas laju pengiriman pesan otomatis.

Telegram menandai akun yang mengirim pesan terlalu cepat dengan
*flood wait*. Solusi lamanya adalah ``asyncio.sleep`` di setiap balasan,
tetapi itu membuat balasan pertama ikut lambat padahal tidak ada yang
perlu dibatasi.

:class:`RateLimiter` memakai token bucket sederhana: pesan pertama
dikirim langsung, pesan berikutnya hanya menunggu sisa jeda dari
pengiriman terakhir. Jadi bot tetap responsif sekaligus aman.
"""

from __future__ import annotations

import asyncio
import time

import config


class RateLimiter:
    """Jaga jarak minimum antar pesan keluar."""

    def __init__(self, min_interval: float) -> None:
        """Siapkan limiter dengan jeda minimum dalam detik.

        Args:
            min_interval: Jarak minimum antar pengiriman, ``0`` mematikan
                pembatasan.
        """
        self._min_interval = max(0.0, min_interval)
        self._last_sent: float = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> float:
        """Tunggu sampai aman untuk mengirim pesan berikutnya.

        Returns:
            Berapa detik yang benar-benar ditunggu, ``0.0`` bila tidak
            perlu menunggu.
        """
        if self._min_interval == 0.0:
            return 0.0

        async with self._lock:
            now = time.monotonic()
            delay = self._last_sent + self._min_interval - now
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_sent = time.monotonic()
            return max(0.0, delay)


# Satu instance dipakai seluruh handler supaya semua pesan yang keluar
# ikut berbagi batas laju yang sama.
send_limiter = RateLimiter(config.SEND_DELAY)
