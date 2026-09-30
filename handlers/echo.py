"""Handler untuk perintah /echo: mengulang teks yang dikirim user."""

from __future__ import annotations

import logging

from utils.commands import args_of, command_pattern, new_message
from utils.context import Context

logger = logging.getLogger(__name__)

COMMAND = "echo"
USAGE = "Gunakan format: /echo <teks> — contoh: /echo Halo dunia!"


async def echo(event, ctx: Context) -> None:
    """Tangani perintah ``/echo``: balas dengan teks dari argumen.

    Args:
        event: Event pesan masuk dari Telethon.
        ctx: Konteks bersama (tidak dipakai pada perintah ini).
    """
    text = args_of(event.message.text)
    if not text:
        await event.reply(USAGE)
        logger.info("User %s memakai /echo tanpa argumen.", event.sender_id)
        return

    await event.reply(text)
    logger.info("User %s memakai /echo: %r", event.sender_id, text)


def register(ctx: Context) -> None:
    """Daftarkan handler ``/echo`` ke klien.

    Args:
        ctx: Konteks bersama yang menyimpan klien Telethon.
    """

    @ctx.client.on(new_message(pattern=command_pattern(COMMAND)))
    async def _on_echo(event) -> None:
        await echo(event, ctx)
