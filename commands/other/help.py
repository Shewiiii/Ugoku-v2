import discord
from discord.ext import commands

# MADE WITH CHATGPT
# Inspired by https://docs.google.com/spreadsheets/d/1bhPYT3Z-WOlu0x1llrwOXc3lcO9RzXmrbfi08Mbt2rk


class HelpDropdown(discord.ui.Select):
    def __init__(self):
        # Dropdown options with emojis
        options = [
            discord.SelectOption(
                label="Music Bot",
                description="Shows music-related commands",
                emoji="🎵"
            ),
            discord.SelectOption(
                label="Chatbot / LLM",
                description="Shows chatbot and LLM-related commands",
                emoji="💬"
            ),
            discord.SelectOption(
                label="Misc",
                description="Shows miscellaneous commands",
                emoji="🌀"
            )
        ]

        super().__init__(
            placeholder="Choose a category...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        """Callback that fires when the user picks an option from the dropdown."""
        selected = self.values[0]

        if selected == "Music Bot":
            embed = discord.Embed(
                title="Music Bot Commands",
                description="Works on server Only !",
                color=discord.Color.blue()
            )
            # /play
            embed.add_field(
                name="/play",
                value=(
                    "Play any song / playlist / album (Spotify, Deezer, YouTube, or Onsei)\n"
                    "Example: ``/play pikasonic lockdown``\n"
                ),
                inline=False
            )
            # /shuffle
            embed.add_field(
                name="/shuffle",
                value=(
                    "Shuffle / unshuffle the queue\n"
                ),
                inline=False
            )
            # /loop
            embed.add_field(
                name="/loop",
                value=(
                    "Repeat / un-repeat the queue\n"
                ),
                inline=False
            )
            # /clear
            embed.add_field(
                name="/clear",
                value=(
                    "Clear the current queue and stop the song playing\n"
                ),
                inline=False
            )
            # /leave
            embed.add_field(
                name="/leave",
                value=(
                    "Leave the current voice channel\n"
                ),
                inline=False
            )
            # /lyrics
            embed.add_field(
                name="/lyrics",
                value=(
                    "Get the lyrics of the current song or any song\n"
                    "Example: ``/lyrics pikasonic lockdown English``\n"
                ),
                inline=False
            )
            # /pause
            embed.add_field(
                name="/pause",
                value=(
                    "Pause the current song\n"
                ),
                inline=False
            )
            # /resume
            embed.add_field(
                name="/resume",
                value=(
                    "Resume the current song\n"
                ),
                inline=False
            )
            # /seek
            embed.add_field(
                name="/seek",
                value=(
                    "Forward to any position in the song (seconds)\n"
                    "Example: ``/seek 60``\n"
                ),
                inline=False
            )
            # /previous
            embed.add_field(
                name="/previous",
                value=(
                    "Play the previous song\n"
                ),
                inline=False
            )
            # /skip
            embed.add_field(
                name="/skip",
                value=(
                    "Skip the current song\n"
                ),
                inline=False
            )
            # /spdl
            embed.add_field(
                name="/spdl",
                value=(
                    "Download a song from Spotify\n"
                    "Example: ``/spdl https://open.spotify.com/track/3Q1UYQcegXHTlfexW2zVoQ``\n"
                ),
                inline=False
            )
            # /dzdl
            embed.add_field(
                name="/dzdl",
                value=(
                    "Download a song from Deezer\n"
                    "Example: ``/dzdl 24/7 Shining``\n"
                ),
                inline=False
            )
            # /audio-effect
            embed.add_field(
                name="/audio-effect",
                value=(
                    "Modify the audio effect of the currently playing song\n"
                    "Example: ``/audio-effect bass boost (mono)``\n"
                ),
                inline=False
            )
            # /audio-bitrate
            embed.add_field(
                name="/audio-bitrate",
                value=(
                    "Modify the audio bitrate of the currently playing song\n"
                    "Can be useful for limited internet connections\n"
                    "Example: ``/audio-bitrate 128``\n"
                ),
                inline=False
            )

        elif selected == "Chatbot / LLM":
            embed = discord.Embed(
                title="Chatbot / LLM Commands",
                color=discord.Color.green()
            )
            # /ask
            embed.add_field(
                name="/ask",
                value=(
                    "Ask Ugoku Anything\n"
                    "Example: ``/ask Write a Python code to display the current time``\n"
                    "Works on: Server / Personal"
                ),
                inline=False
            )
            # /summarize
            embed.add_field(
                name="/summarize",
                value=(
                    "Summarize a text or a YouTube video\n"
                    "Example: ``/summarize https://www.youtube.com/watch?v=Km2DNLbB-6o``\n"
                    "Works on: Server / Personal"
                ),
                inline=False
            )
            # /reset_chatbot
            embed.add_field(
                name="/reset_chatbot",
                value=(
                    "Reset the chatbot history. Does not remove Pinecone entries\n"
                    "Example: ``/reset_chatbot``\n"
                    "Works on: Server / Personal"
                ),
                inline=False
            )
            # /translate
            embed.add_field(
                name="/translate",
                value=(
                    "Translate anything to any language\n"
                    "Example: ``/translate イレイナちゃんはかわいい``\n"
                    "Works on: Server / Personal"
                ),
                inline=False
            )
            # - (activate the chatbot)
            embed.add_field(
                name="-",
                value=(
                    "Activate the chatbot\n"
                    "Example: ``-Hi, who are you ?``\n"
                    "Works on: Server Only"
                ),
                inline=False
            )
            # -- (activate chatbot continuous mode)
            embed.add_field(
                name="--",
                value=(
                    "Activate the chatbot - Continuous mode\n"
                    "Example: ``--Hi, who are you ?``\n"
                    "Works on: Server Only"
                ),
                inline=False
            )

        else:  # "Misc"
            embed = discord.Embed(
                title="Misc Commands",
                color=discord.Color.purple()
            )
            # /ping
            embed.add_field(
                name="/ping",
                value=(
                    "Check Ugoku's response time\n"
                    "Example: ``/ping``\n"
                    "Works on: Server / Personal"
                ),
                inline=False
            )
            # /get-stickers
            embed.add_field(
                name="/get-stickers",
                value=(
                    "Download any sticker set from Line\n"
                    "Example: ``/get-stickers https://store.line.me/stickershop/product/28492189/en``\n"
                    "Works on: Server / Personal"
                ),
                inline=False
            )
            # /echo
            embed.add_field(
                name="/echo",
                value=(
                    "Repeat your message\n"
                    "Example: ``/echo Hibiki is cute``\n"
                    "Works on: Server / Personal"
                ),
                inline=False
            )
            # /danbooru
            embed.add_field(
                name="/danbooru",
                value=(
                    "Get any image from a tag on danbooru (SFW only)\n"
                    "Example: ``/danbooru nanashi_mumei``\n"
                    "Works on: Server / Personal"
                ),
                inline=False
            )

        # Update the original message with the new embed
        await interaction.response.edit_message(embed=embed, view=self.view)


# A View that holds the dropdown
class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(HelpDropdown())


class Help(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name="help",
        description="Show help menu.",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install
        }
    )
    async def help_command(self, ctx: discord.ApplicationContext) -> None:
        """Slash command to show the help menu with a dropdown."""
        embed = discord.Embed(
            title="Help Menu",
            description="Select a category from the dropdown below.",
            color=discord.Color.blurple()
        )
        view = HelpView()
        await ctx.respond(
            embed=embed,
            view=view,
            ephemeral=True
        )


def setup(bot):
    bot.add_cog(Help(bot))
