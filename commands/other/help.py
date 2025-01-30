import discord
from discord.ext import commands

from config import CHATBOT_PREFIX, GEMINI_MODEL, DEFAULT_EMBED_COLOR


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
            ),
            discord.SelectOption(
                label="Infos",
                description="Learn more about the bot",
                emoji="ℹ️"
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
                    "Example: ``/play Blue Dream Cheel``\n"
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
                    "Example: ``/dzdl Ma Meilleure Ennemie``\n"
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
            # /POP
            embed.add_field(
                name="/pop",
                value=(
                    "Remove songs from the queue\n"
                    "Example: ``/pop Single Nanatsukaze - もしも``\n"
                ),
                inline=False
            )

        elif selected == "Chatbot / LLM":
            embed = discord.Embed(
                title="Chatbot / LLM Commands",
                color=discord.Color.green()
            )
            # Chatbot notes
            embed.add_field(
                name="About the chatbot",
                value=(
                    f"The Ugoku chatbot is based on the {GEMINI_MODEL} model. "
                    "It is an AI character that can respond "
                    "to various types of questions "
                    f"using the bot prefix **{CHATBOT_PREFIX}**, "
                    "the /ask command in allowed servers, "
                    "or by chatting directly in DMs.\n\n"
                    "Please note that **Ugoku can store important "
                    "information told to the bot on a "
                    "[Pinecone](https://www.pinecone.io/) index** "
                    "(birthdate, events, fun facts...), "
                    "to enhance conversations and provide more relevant responses. "
                    "However, this information is strictly private "
                    "and will never be shared across servers or DMs."

                ),
                inline=False
            )
            # /ask
            embed.add_field(
                name="/ask",
                value=(
                    "Ask Ugoku Anything\n"
                    "Example: ``/ask Write a Python code to display the current time``\n"
                    "Works on: **Allowed servers Only**"
                ),
                inline=False
            )
            # /summarize
            embed.add_field(
                name="/summarize",
                value=(
                    "Summarize a text or a YouTube video. **May NOT work on server/VPS hosted bots**\n"
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
                    "Example: ``/translate めっちゃいい曲だね！``\n"
                    "Works on: Server / Personal"
                ),
                inline=False
            )
            # normal prefix (activate the chatbot)
            embed.add_field(
                name=CHATBOT_PREFIX,
                value=(
                    "Activate the chatbot\n"
                    f"Example: ``{CHATBOT_PREFIX}Hi, who are you ?``\n"
                    "Works on: **Allowed servers Only**"
                ),
                inline=False
            )
            # double prefix (activate chatbot continuous mode)
            embed.add_field(
                name=CHATBOT_PREFIX*2,
                value=(
                    "Activate the chatbot - Continuous mode\n"
                    f"Example: ``{CHATBOT_PREFIX*2}Hi, who are you ?``\n"
                    "Works on: **Allowed servers Only**"
                ),
                inline=False
            )

        elif selected == "Misc":
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
        else:
            embed = discord.Embed(
                title="Misc Commands",
                color=discord.Colour.from_rgb(*DEFAULT_EMBED_COLOR)
            )
            embed.add_field(
                name="What is this bot?",
                value=(
                    "Shewi here. Ugoku is a simple bot I made in my spare time for fun.\n"
                    "My initial motivation was to make a music bot that allows "
                    "everyone to download and share songs easily, directly within Discord. "
                    "To my knowledge, no Discord music bot offers high-quality audio, "
                    "and Ugoku's purpose is to fill that niche gap. "
                    "Turns out, I had more fun than expected when coding it, so here we go!"
                ),
                inline=False
            )
            embed.add_field(
                name="Is this legal?",
                value=(
                    "It is not, since it breaks DRM restrictions of music streaming platforms."
                ),
                inline=False
            )
            embed.add_field(
                name="Why does YouTube not work?",
                value=(
                    "YouTube actively tries to block any unauthorized third-party service from its platform. "
                    "Since Ugoku is not hosted on a local server, "
                    "it gets blocked within a few days after changing the VPN server."
                ),
                inline=False
            )
            embed.add_field(
                name='What the "Audio quality" label actually means ?',
                value=(
                    "It is simple as this:\n"
                    "- **Low**: Audio from Youtube, using AAC 128Kpbs or 160Kbps Opus as a source on not autogenerated videos\n"
                    "- **High**: Audio from Spotify, using OGG 320 Kbps as a source\n"
                    "- **Hifi**: Audio from Deezer, using FLAC lossless audio as a source\n"
                    "Important note !\n In order to provide audio to the Discord API, audio *needs* to be "
                    "transcoded to Opus format. Even though Ugoku uses a fixed bitrate of 510Kbps, "
                    "the audio output cannot be bit-perfect."
                ),
                inline=False
            )
            embed.add_field(
                name="Will Deepseek be supported anytime soon?",
                value=(
                    "While Deepseek R1 is an exciting model, "
                    "the output token speed is currently way too low "
                    "to be usable. Deepseek V3 would be more appropriate for a chatbot, "
                    f"but {GEMINI_MODEL} is still superior "
                    "and outputs surprisingly good natural Japanese, which is important to me."
                ),
                inline=False
            )
            embed.add_field(
                name="The Chatbot is a bit...weird sometimes..",
                value=(
                    "I am aware of this issue. Hopefully I will find a good prompt in the future."
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

    @ commands.slash_command(
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
