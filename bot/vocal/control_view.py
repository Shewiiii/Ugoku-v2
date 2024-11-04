
import discord


# VIEW (for buttons under the "now playing" embed)
class controlView(discord.ui.View):
    def __init__(
        self,
        bot: discord.bot,
        ctx: discord.ApplicationContext,
        voice_client: discord.voice_client
    ) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.ctx = ctx
        self.voice_client = voice_client

    @discord.ui.button(
        label="Pause/Resume",
        style=discord.ButtonStyle.secondary,
    )
    async def pause_button_callback(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ) -> None:
        # To avoid "interaction failed message"
        await interaction.response.defer()

        # Pause if audio is playing
        if self.voice_client.is_playing():
            pause_cog = self.bot.get_cog('Pause')
            await pause_cog.execute_pause(self.ctx, send=True)

        # Resume if audio is paused
        else:
            resume_cog = self.bot.get_cog('Resume')
            await resume_cog.execute_resume(self.ctx, send=True)

    @discord.ui.button(
        label="Play previous",
        style=discord.ButtonStyle.secondary,
    )
    async def previous_button_callback(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ) -> None:
        await interaction.response.defer()

        previous_cog = self.bot.get_cog('Previous')
        await previous_cog.execute_previous(self.ctx, send=True)

    @discord.ui.button(
        label="Skip",
        style=discord.ButtonStyle.secondary,
    )
    async def skip_button_callback(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ) -> None:
        await interaction.response.defer()

        skip_cog = self.bot.get_cog('Skip')
        await skip_cog.execute_skip(self.ctx, send=True)

    @discord.ui.button(
        label="Loop song",
        style=discord.ButtonStyle.secondary,
    )
    async def loop_button_callback(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ) -> None:
        await interaction.response.defer()

        loop_cog = self.bot.get_cog('Loop')
        await loop_cog.execute_loop(self.ctx, 'Song', send=True)

    @discord.ui.button(
        label="Shuffle",
        style=discord.ButtonStyle.secondary,
    )
    async def shuffle_button_callback(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ) -> None:
        await interaction.response.defer()

        shuffle_cog = self.bot.get_cog('Shuffle')
        await shuffle_cog.execute_shuffle(self.ctx, send=True)
