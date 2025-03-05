import discord


# VIEW (for buttons under the "now playing" embed)
class controlView(discord.ui.View):
    def __init__(
        self,
        bot: discord.bot,
        ctx: discord.ApplicationContext,
        voice_client: discord.voice_client,
        server_session
    ) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.ctx = ctx
        self.voice_client = voice_client
        self.server_session = server_session

    async def in_active_vc(self, interaction: discord.Interaction) -> None:
        voice = interaction.user.voice
        if not voice:
            return False
        return voice.channel == self.ctx.voice_client.channel

    @discord.ui.button(
        label="Pause",
        style=discord.ButtonStyle.secondary,
    )
    async def pause_button_callback(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ) -> None:
        # To avoid "interaction failed message"
        await interaction.response.defer()
        if not await self.in_active_vc(interaction):
            return

        if self.voice_client.is_playing():
            pause_cog = self.bot.get_cog('Pause')
            if await pause_cog.execute_pause(self.ctx, silent=True):
                button.label = "Resume"
                button.style = discord.ButtonStyle.success

        else:
            resume_cog = self.bot.get_cog('Resume')
            if await resume_cog.execute_resume(self.ctx, silent=True):
                button.label = "Pause"
                button.style = discord.ButtonStyle.secondary

        # Refresh the view
        await interaction.message.edit(view=self)

    @discord.ui.button(
        label="Previous",
        style=discord.ButtonStyle.secondary,
    )
    async def previous_button_callback(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ) -> None:
        await interaction.response.defer()
        if not await self.in_active_vc(interaction):
            return

        previous_cog = self.bot.get_cog('Previous')
        if await previous_cog.execute_previous(self.ctx, silent=True):
            button.label = "Played previous"
            button.style = discord.ButtonStyle.blurple
            # Update the "Skipped" button as well
            for item in self.children:
                if getattr(item, "label", None) == "Skipped":
                    item.label = "Skip"
                    item.style = discord.ButtonStyle.secondary
                    break
            await interaction.message.edit(view=self)

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
        if not await self.in_active_vc(interaction):
            return

        skip_cog = self.bot.get_cog('Skip')
        if await skip_cog.execute_skip(self.ctx, silent=True):
            button.label = "Skipped"
            button.style = discord.ButtonStyle.blurple
            # Update the "Played previous" button as well
            for item in self.children:
                if getattr(item, "label", None) == "Played previous":
                    item.label = "Previous"
                    item.style = discord.ButtonStyle.secondary
                    break
            await interaction.message.edit(view=self)

    @discord.ui.button(
        label="Loop",
        style=discord.ButtonStyle.secondary,
    )
    async def loop_button_callback(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ) -> None:
        await interaction.response.defer()
        if not await self.in_active_vc(interaction):
            return

        loop_cog = self.bot.get_cog('Loop')
        await loop_cog.execute_loop(self.ctx, 'Song', silent=True)

        if self.server_session.loop_current:
            button.label = "Looping"
            button.style = discord.ButtonStyle.success
        else:
            button.label = "Loop"
            button.style = discord.ButtonStyle.secondary

        # Refresh the view
        await interaction.message.edit(view=self)

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
        if not await self.in_active_vc(interaction):
            return

        shuffle_cog = self.bot.get_cog('Shuffle')
        await shuffle_cog.execute_shuffle(self.ctx, send=True)
