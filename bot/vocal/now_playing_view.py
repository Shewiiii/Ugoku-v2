import asyncio
import discord
from discord import ButtonStyle
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from bot.vocal.server_session import ServerSession


class nowPlayingView(discord.ui.View):
    def __init__(
        self,
        bot: discord.bot,
        ctx: discord.ApplicationContext,
        voice_client: discord.voice_client,
        server_session: "ServerSession",
    ) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.ctx = ctx
        self.voice_client = voice_client
        self.server_session: "ServerSession" = server_session

    async def in_active_vc(self, interaction: discord.Interaction) -> None:
        voice = interaction.user.voice
        if not voice:
            return
        return voice.channel == self.ctx.voice_client.channel

    async def update_buttons(
        self, paused: Optional[bool] = None, delay: float = 0.0, edit: bool = True
    ) -> None:
        await asyncio.sleep(delay)
        states_dict = {
            0: {
                "inactive_msg": "Pause",
                "active_msg": "Paused",
                "is_active": paused
                if paused is not None
                else self.voice_client.is_paused(),
            },
            3: {
                "inactive_msg": "Loop",
                "active_msg": "Looping",
                "is_active": self.server_session.loop_current,
            },
            4: {
                "inactive_msg": "Shuffle",
                "active_msg": "Shuffling",
                "is_active": self.server_session.shuffle,
            },
        }
        for key, s in states_dict.items():
            item = self.children[key]
            item.label = s["active_msg"] if s["is_active"] else s["inactive_msg"]
            item.style = (
                ButtonStyle.success if s["is_active"] else ButtonStyle.secondary
            )

        # Update previous and next
        s = self.server_session
        previous = self.children[1]
        skip = self.children[2]
        previous.disabled = len(s.stack_previous) == 0
        skip.disabled = len(s.queue) == 0
        if edit and s.now_playing_message:
            await s.now_playing_message.edit(view=self)

    @discord.ui.button(
        label="Pause",
        style=ButtonStyle.secondary,
    )
    async def pause_button_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        # To avoid "interaction failed message"
        asyncio.create_task(interaction.response.defer())
        if not await self.in_active_vc(interaction):
            return

        if self.voice_client.is_playing():
            pause_cog = self.bot.get_cog("Pause")
            await pause_cog.execute_pause(self.ctx, silent=True)
        else:
            resume_cog = self.bot.get_cog("Resume")
            await resume_cog.execute_resume(self.ctx, silent=True)

    @discord.ui.button(label="Previous", style=ButtonStyle.secondary, disabled=True)
    async def previous_button_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        asyncio.create_task(interaction.response.defer())
        if not await self.in_active_vc(interaction):
            return

        previous_cog = self.bot.get_cog("Previous")
        await previous_cog.execute_previous(self.ctx, silent=True)

    @discord.ui.button(
        label="Skip",
        style=ButtonStyle.secondary,
    )
    async def skip_button_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        asyncio.create_task(interaction.response.defer())
        if not await self.in_active_vc(interaction):
            return

        skip_cog = self.bot.get_cog("Skip")
        await skip_cog.execute_skip(self.ctx, silent=True)

    @discord.ui.button(
        label="Loop",
        style=ButtonStyle.secondary,
    )
    async def loop_button_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        asyncio.create_task(interaction.response.defer())
        if not await self.in_active_vc(interaction):
            return

        loop_cog = self.bot.get_cog("Loop")
        await loop_cog.execute_loop(self.ctx, "Song", silent=True)

    @discord.ui.button(
        label="Shuffle",
        style=ButtonStyle.secondary,
    )
    async def shuffle_button_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        asyncio.create_task(interaction.response.defer())
        if not await self.in_active_vc(interaction):
            return

        shuffle_cog = self.bot.get_cog("Shuffle")
        await shuffle_cog.execute_shuffle(self.ctx, silent=True)

    def close(self) -> None:
        self.server_session = self.bot = self.ctx = self.voice_client = None
        super().close()
