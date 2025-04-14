import asyncio
import discord
from discord import ButtonStyle
from typing import Optional, Literal, TYPE_CHECKING

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

        # Extra buttons
        self.extra_buttons_visible = False
        loop_queue = discord.ui.Button(label="Loop queue", style=ButtonStyle.secondary)
        shuffle = discord.ui.Button(label="Shuffle", style=ButtonStyle.secondary)
        effect = discord.ui.Button(label="Effect", style=ButtonStyle.secondary)
        lyrics = discord.ui.Button(label="Lyrics", style=ButtonStyle.secondary)
        leave = discord.ui.Button(label="Leave", style=ButtonStyle.danger)
        loop_queue.callback = lambda interaction: self.loop_callback(
            loop_queue, interaction, "queue"
        )
        shuffle.callback = lambda interaction: self.shuffle_callback(
            shuffle, interaction
        )
        effect.callback = lambda interaction: self.effect_callback(effect, interaction)
        lyrics.callback = lambda interaction: self.lyrics_callback(lyrics, interaction)
        leave.callback = lambda interaction: self.leave_callback(leave, interaction)

        self.extra_buttons = [loop_queue, shuffle, effect, lyrics, leave]

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
            5: {
                "inactive_msg": "Loop queue",
                "active_msg": "Looping queue",
                "is_active": self.server_session.loop_queue,
            },
            6: {
                "inactive_msg": "Shuffle",
                "active_msg": "Shuffling",
                "is_active": self.server_session.shuffle,
            },
            7: {
                "inactive_msg": "Effect",
                "active_msg": "Effect",
                "is_active": self.server_session.audio_effect.effect is not None,
            },
        }
        for key, s in states_dict.items():
            if key < len(self.children):  # Not the case for all the buttons by default
                item = self.children[key]
                item.label = s["active_msg"] if s["is_active"] else s["inactive_msg"]
                item.style = (
                    ButtonStyle.success if s["is_active"] else ButtonStyle.secondary
                )

        # Update button disabling
        s = self.server_session
        previous = self.children[1]
        skip = self.children[2]
        previous.disabled = len(s.stack_previous) == 0
        skip.disabled = len(s.queue) == 0
        if len(self.children) >= 7:
            shuffle = self.children[6]
            shuffle.disabled = len(s.queue) <= 2

        # Edit the view
        if edit and s.now_playing_message:
            await s.now_playing_message.edit(view=self)

    @discord.ui.button(
        label="Pause",
        style=ButtonStyle.secondary,
    )
    async def pause_callback(
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
    async def previous_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        asyncio.create_task(interaction.response.defer())
        if not await self.in_active_vc(interaction):
            return

        cog = self.bot.get_cog("Previous")
        await cog.execute_previous(self.ctx, silent=True)

    @discord.ui.button(
        label="Skip",
        style=ButtonStyle.secondary,
    )
    async def skip_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        asyncio.create_task(interaction.response.defer())
        if not await self.in_active_vc(interaction):
            return

        cog = self.bot.get_cog("Skip")
        await cog.execute_skip(self.ctx, silent=True)

    @discord.ui.button(
        label="Loop",
        style=ButtonStyle.secondary,
    )
    async def loop_callback_(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        await self.loop_callback(button, interaction, "song")

    @discord.ui.button(
        label=">",
        style=ButtonStyle.secondary,
    )
    async def show_more(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        asyncio.create_task(interaction.response.defer())
        if not await self.in_active_vc(interaction):
            return

        if not self.extra_buttons_visible:
            for b in self.extra_buttons:
                self.add_item(b)
            button.label = "<"
        else:
            for b in self.extra_buttons:
                self.remove_item(b)
            button.label = ">"

        self.extra_buttons_visible = not self.extra_buttons_visible
        await self.update_buttons()

    # EXTRA BUTTONS callbacks on ">" click
    async def loop_callback(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction,
        mode: Literal["song", "queue"],
    ) -> None:
        asyncio.create_task(interaction.response.defer())
        if not await self.in_active_vc(interaction):
            return

        cog = self.bot.get_cog("Loop")
        await cog.execute_loop(self.ctx, mode, silent=True)

    async def shuffle_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        asyncio.create_task(interaction.response.defer())
        if not await self.in_active_vc(interaction):
            return

        cog = self.bot.get_cog("Shuffle")
        await cog.execute_shuffle(self.ctx, silent=True)

    async def effect_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        asyncio.create_task(interaction.response.defer())
        if not await self.in_active_vc(interaction):
            return

        cog = self.bot.get_cog("AudioEffects")
        if self.server_session.audio_effect.effect:
            effect = "default"
        else:
            effect = "Raum size 100%, decay 2s"
        await cog.execute_effect(self.ctx, effect=effect, silent=True)
        await self.update_buttons()

    async def lyrics_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        asyncio.create_task(interaction.response.defer())
        if not await self.in_active_vc(interaction):
            return

        cog = self.bot.get_cog("Lyrics")
        await cog.execute_lyrics(self.ctx, query=None, send=True)
        await self.update_buttons()

    async def leave_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        asyncio.create_task(interaction.response.defer())
        if not await self.in_active_vc(interaction):
            return

        cog = self.bot.get_cog("Leave")
        await cog.execute_leave(self.ctx, send=True)

    def close(self) -> None:
        self.clear_items()
        self.server_session = self.bot = self.ctx = self.voice_client = None
