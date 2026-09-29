"""
Argus Alert Engine — Discord bot dispatcher.

Responsibilities:
  - Sends embed messages with image attachments to a Discord channel.
  - Attaches discord.ui.View (buttons/ActionRows) for interactive prompts.
  - Listens for button interactions and routes them to the handler.

Requires: discord.py >= 2.3.0 (async-native with app_commands)
"""
from __future__ import annotations

import asyncio
import contextlib
import io
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import discord

logger = structlog.get_logger(__name__)

CallbackHandler = Callable[[str, str], Awaitable[None]]

SEVERITY_COLOR = {"critical": 0xFF0000, "warning": 0xFF8C00, "info": 0x00BFFF}


class DiscordClient:
    """
    Thin async wrapper around discord.py.

    Lifecycle:
        client = DiscordClient(config, callback_handler)
        await client.start()       # non-blocking background task
        await client.send(alert)
        await client.stop()
    """

    def __init__(self, config, callback_handler: CallbackHandler | None = None) -> None:
        self._cfg = config
        self._callback_handler = callback_handler
        self._client = None  # discord.Client, lazy-initialized
        self._ready = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start Discord bot in a background task."""
        try:
            import discord

            intents = discord.Intents.default()
            self._client = discord.Client(intents=intents)

            @self._client.event
            async def on_ready() -> None:
                logger.info("Discord bot ready", user=str(self._client.user))
                self._ready.set()

            @self._client.event
            async def on_interaction(interaction: discord.Interaction) -> None:
                await self._handle_interaction(interaction)

            self._task = asyncio.create_task(
                self._client.start(self._cfg.bot_token),
                name="argus-discord-bot",
            )
            # Wait up to 15s for the bot to connect
            try:
                await asyncio.wait_for(self._ready.wait(), timeout=15.0)
            except TimeoutError:
                logger.warning("Discord bot did not become ready within 15s")
        except Exception as exc:
            logger.error("Failed to start Discord bot", error=str(exc))

    async def stop(self) -> None:
        """Gracefully close the Discord connection."""
        try:
            if self._client:
                await self._client.close()
            if self._task:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
            logger.info("Discord bot stopped")
        except Exception as exc:
            logger.warning("Error during Discord bot shutdown", error=str(exc))

    async def send(self, alert) -> bool:
        """Dispatch an Alert to the configured Discord channel. Returns True on success."""
        if not self._client or not self._client.is_ready():
            logger.warning("Discord client not ready — skipping send")
            return False
        try:
            import discord
            channel = self._client.get_channel(self._cfg.channel_id_int)
            if channel is None:
                channel = await self._client.fetch_channel(self._cfg.channel_id_int)

            embed = self._build_embed(alert)
            view = self._build_view(alert)
            file = None

            if alert.thumbnail:
                file = discord.File(io.BytesIO(alert.thumbnail), filename="alert_thumb.jpg")
                embed.set_thumbnail(url="attachment://alert_thumb.jpg")

            await channel.send(embed=embed, view=view, file=file)
            logger.info("Alert sent via Discord", alert_id=alert.alert_id, kind=alert.kind)
            return True
        except Exception as exc:
            logger.error("Discord send failed", alert_id=alert.alert_id, error=str(exc))
            return False

    def _build_embed(self, alert) -> discord.Embed:
        import discord
        color = SEVERITY_COLOR.get(alert.severity.value, 0x808080)
        embed = discord.Embed(
            title=alert.title,
            description=alert.body,
            color=color,
            timestamp=alert.created_at,
        )
        if alert.camera_name:
            embed.add_field(name="📷 Camera", value=f"`{alert.camera_name}`", inline=True)
        embed.add_field(name="🔖 Kind", value=alert.kind.value, inline=True)
        embed.set_footer(text="Argus AI Security System")
        return embed

    def _build_view(self, alert) -> discord.ui.View | None:
        if not alert.buttons:
            return None
        try:
            import discord

            class AlertView(discord.ui.View):
                def __init__(self, buttons, handler):
                    super().__init__(timeout=300)
                    for btn in buttons:
                        button = discord.ui.Button(
                            label=btn.label,
                            custom_id=btn.callback_data,
                            style=discord.ButtonStyle.primary,
                        )
                        button.callback = self._make_callback(btn.callback_data, handler)
                        self.add_item(button)

                def _make_callback(self, cb_data: str, handler):
                    async def _cb(interaction: discord.Interaction):
                        await interaction.response.defer()
                        if handler:
                            user_id = str(interaction.user.id) if interaction.user else "unknown"
                            await handler(cb_data, user_id)
                        self.stop()
                    return _cb

            return AlertView(alert.buttons, self._callback_handler)
        except ImportError:
            return None

    async def _handle_interaction(self, interaction) -> None:
        """Fallback interaction handler for non-View interactions."""
        try:
            if not interaction.data:
                return
            custom_id = interaction.data.get("custom_id")
            if custom_id and self._callback_handler:
                user_id = str(interaction.user.id) if interaction.user else "unknown"
                await self._callback_handler(custom_id, user_id)
        except Exception as exc:
            logger.warning("Discord interaction error", error=str(exc))
