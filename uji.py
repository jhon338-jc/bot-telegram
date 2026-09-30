"""Uji cepat: jalankan userbot sebentar dan kirim pesan ke diri sendiri.

Dipakai sebagai verifikasi bahwa login, handler, dan limiter bekerja.
Tidak mengubah kode project; file ini hanya alat bantu sekali pakai.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from handlers import register_handlers
from utils.context import Context
from utils.database import Database
from utils.login import build_client, ensure_login
from utils.ratelimit import send_limiter

TESTS = ["/start", "/help", "/info", "/echo halo userbot", "pesan biasa otomatis"]


async def main() -> None:
    started = time.perf_counter()
    db = Database(config.DATABASE_PATH)
    db.connect()

    client = build_client()
    me = await ensure_login(client)

    ctx = Context(client=client, db=db, me=me)
    register_handlers(ctx)

    print(f"LOGIN  : {me.first_name} (ID {me.id}) dalam {time.perf_counter()-started:.2f} dtk")
    print("MENGIRIM pesan uji ke chat sendiri...\n")

    for text in TESTS:
        await send_limiter.wait()
        await client.send_message("me", text)
        print(f"  terkirim: {text}")
        await asyncio.sleep(1.2)

    print("\nTunggu balasan masuk (5 dtk)...")
    await asyncio.sleep(5)
    print(f"Total {time.perf_counter()-started:.2f} dtk. Selesai.")

    await client.disconnect()
    db.close()


asyncio.run(main())
