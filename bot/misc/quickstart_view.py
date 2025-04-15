import discord
from discord.ui import View
from typing import Optional

from config import DEFAULT_EMBED_COLOR, CHATBOT_PREFIX, ALLOW_CHATBOT_IN_DMS


class QuickstartView(View):
    def __init__(self, timeout: Optional[int] = 1800) -> None:
        super().__init__(timeout=timeout)
        self.page = 0
        self.embed = discord.Embed(
            title="Quickstart", color=discord.Colour.from_rgb(*DEFAULT_EMBED_COLOR)
        ).add_field(
            name="",
            value="",
        )

        self.greetings = {
            "name": "",
            "value": (
                "Heya, I am **Ugoku** ! A minimalist bot trying to bring fun in your server~\n"
                "I can play music in a voice channel, download songs, emotes or stickers for you, chat and more !\n"
                "I don't have any silly Premium paywall, all the features can be used for free :yellow_heart: \n\n"
                "-# You can reinvoke this embed at any time with `/quickstart`."
            ),
            "inline": False,
        }
        self.play_songs_field = {
            "name": "Play songs",
            "value": "- First, hop in a voice channel and try to play a song with `/play` !"
            " You can also play your song files with `/play-custom` :musical_note: \n"
            '- With the "Now playing" view, control the queue has never been easier :sparkles:\n'
            "- You can also paste Spotify, Youtube or Soundcloud URLs for convenience.\n"
            '- If you explicitely want to play a song from a particular source, you can use the "Service" option.\n'
            "- The effect button applies the `Raum size 100%, decay 2s` effect using convolution, for an immersive sound :ringed_planet:\n"
            "- See the full command list in the music category (/help).\n"
            "I've been optimized to be fast, intuitive, and deliver the best audio quality available !",
            "inline": False,
        }
        self.chatbot_field = {
            "name": "Chatbot",
            "value": "Unfortunately, only whitelisted servers can use the chatbot, but you can "
            + ("still DM me or " if ALLOW_CHATBOT_IN_DMS else "")
            + "ask me to whitelist it at ugokuchanbot@gmail.com !\n"
            f"Otherwise, just add `{CHATBOT_PREFIX}` before sending your message, and I will respond to you as best as I can~\n"
            "You can also try to add `!` before your message, so I can search on google for you !\n\n"
            "*psst, you can also [fork the repo](https://github.com/Shewiiii/Ugoku-v2), as the project is open-source !*",
            "inline": False,
        }
        self.misc_field = {
            "name": "Misc features",
            "value": (
                "I also have random features, here are some of them:\n"
                "- You can download songs from Deezer, Spotify or Youtube with the commands \n`/dzdl`, `/spdl`, `/ytdlp`\n"
                "- Get random images from Danbooru tags using \n`/danbooru` \n(be careful, I filter NSFW results, but the site does not !)\n"
                "- Get the direct URL of stickers or emotes your friends have sent using \n`/get-emotes`\n"
                "- Download stickers from LINE with \n`/get-stickers`"
            ),
            "inline": False,
        }
        self.learn_more = {
            "name": "Wanna know more ?",
            "value": "You can learn more about me with the /help command !",
            "inline": False,
        }

    def update_buttons(self) -> None:
        """Disable or enable 'next' and 'previous' buttons based on the current page."""
        self.children[0].disabled = self.page <= 0
        self.children[1].disabled = self.page >= 4

        # Labels (page, (text previous, text next))
        labels = {
            0: ("Previous", "Next: Play songs"),
            1: ("Previous: Greetings", "Next: Chatbot"),
            2: ("Previous: Play songs", "Next: Misc features"),
            3: ("Previous: Chatbot", "Next: Learn more"),
            4: ("Previous: Learn more", "End !"),
        }
        self.children[0].label = labels[self.page][0]
        self.children[1].label = labels[self.page][1]

    def update_embed(self) -> None:
        page_field_dict = {
            0: self.greetings,
            1: self.play_songs_field,
            2: self.chatbot_field,
            3: self.misc_field,
            4: self.learn_more,
        }
        field = self.embed.fields[0]
        data = page_field_dict[self.page]
        field.name = data["name"]
        field.value = data["value"]
        field.inline = data.get("inline", False)

    async def update(self, interaction: Optional[discord.Interaction] = None) -> None:
        """Update the embed and buttons in response to a button interaction."""
        self.update_buttons()
        self.update_embed()
        if interaction:
            await interaction.response.edit_message(embed=self.embed, view=self)

    async def display(self, respond_func, ephemeral: bool = False) -> None:
        """Display the queue view in response to a command."""
        await self.update(interaction=None)
        if ephemeral:
            await respond_func(embed=self.embed, view=self, ephemeral=True)
        else:
            await respond_func(embed=self.embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        """Update the page on 'previous' click."""
        self.page -= 1
        await self.update(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        """Update the page on 'Next' click."""
        self.page += 1
        await self.update(interaction)
