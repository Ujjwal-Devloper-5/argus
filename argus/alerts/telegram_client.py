"""
Argus Alert Engine — Telegram bot dispatcher.

Responsibilities:
  - Sends text + photo + video_note alerts to a Telegram chat.
  - Attaches InlineKeyboardMarkup buttons for interactive prompts.
  - Listens for button callbacks (polling) and routes them to the handler.

Requires: python-telegram-bot >= 21.0 (async-native)
"""
from __future__ import annotations

import io
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

CallbackHandler = Callable[[str, str], Awaitable[None]]  # (callback_data, user_id) -> None


class TelegramClient:
    """
    Thin async wrapper around python-telegram-bot.

    Lifecycle:
        client = TelegramClient(config, callback_handler)
        await client.start()   # start polling
        await client.send(alert)
        await client.stop()    # graceful shutdown
    """

    def __init__(self, config, callback_handler: CallbackHandler | None = None) -> None:
        self._cfg = config
        self._callback_handler = callback_handler
        self._app = None  # telegram.ext.Application, lazy-initialized

    async def start(self) -> None:
        """Initialize the Telegram Application and start polling for callbacks."""
        try:
            from telegram.ext import Application, CallbackQueryHandler
            builder = Application.builder().token(self._cfg.bot_token.get_secret_value())
            self._app = builder.build()
            if self._callback_handler:
                self._app.add_handler(CallbackQueryHandler(self._handle_callback))
            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling(drop_pending_updates=True)
            logger.info("Telegram bot started")
        except Exception as exc:
            logger.error("Failed to start Telegram bot", error=str(exc))

    async def stop(self) -> None:
        """Gracefully stop polling and shutdown."""
        try:
            if self._app:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
                logger.info("Telegram bot stopped")
        except Exception as exc:
            logger.warning("Error during Telegram bot shutdown", error=str(exc))

    async def send(self, alert) -> bool:
        """Dispatch an Alert to the configured Telegram chat. Returns True on success."""
        if not self._app:
            logger.warning("Telegram app not initialized — skipping send")
            return False
        try:
            chat_id = self._cfg.chat_id
            keyboard = self._build_keyboard(alert)
            text = self._format_text(alert)

            if alert.thumbnail:
                await self._app.bot.send_photo(
                    chat_id=chat_id,
                    photo=io.BytesIO(alert.thumbnail),
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            else:
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            logger.info("Alert sent via Telegram", alert_id=alert.alert_id, kind=alert.kind)
            return True
        except Exception as exc:
            logger.error("Telegram send failed", alert_id=alert.alert_id, error=str(exc))
            return False

    async def edit_message_reply_markup(self, chat_id: str, message_id: int, text: str) -> None:
        """Edit a previously sent message after a button is clicked."""
        try:
            if self._app:
                await self._app.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    parse_mode="HTML",
                )
        except Exception as exc:
            logger.warning("Failed to edit Telegram message", error=str(exc))

    def _build_keyboard(self, alert):
        """Build InlineKeyboardMarkup from alert buttons, or None."""
        if not alert.buttons:
            return None
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            rows = [[InlineKeyboardButton(b.label, callback_data=b.callback_data)] for b in alert.buttons]
            return InlineKeyboardMarkup(rows)
        except ImportError:
            return None

    def _format_text(self, alert) -> str:
        severity_emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(alert.severity.value, "📢")
        lines = [
            f"{severity_emoji} <b>{alert.title}</b>",
            "",
            alert.body,
        ]
        if alert.camera_name:
            lines.append(f"\n📷 Camera: <code>{alert.camera_name}</code>")
        return "\n".join(lines)

    async def _handle_callback(self, update, context) -> None:
        """Internal callback query handler — routes to user-provided handler."""
        try:
            query = update.callback_query
            await query.answer()  # Acknowledge to Telegram immediately
            if self._callback_handler and query.data:
                user_id = str(query.from_user.id) if query.from_user else "unknown"
                await self._callback_handler(query.data, user_id)
                await query.edit_message_reply_markup(reply_markup=None)
        except Exception as exc:
            logger.warning("Error handling Telegram callback", error=str(exc))
