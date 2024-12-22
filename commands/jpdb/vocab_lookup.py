import discord
from discord.ext import commands
from bot.jpdb.word_api import word_api

from config import DEFAULT_EMBED_COLOR
from bot.utils import split_into_chunks
from bot.jpdb.convert_to_romaji import convert_to_romaji


class JpdbLookup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def create_embed(api_request: dict) -> discord.Embed:
        reading = api_request.get('reading', '?')
        romaji = convert_to_romaji(reading)
        word = api_request.get('word', '?')
        embed = discord.Embed(
            title=word,
            url=f"https://jpdb.io/search?q={word}",
            description='\n'.join([reading, romaji]),
            color=discord.Colour.from_rgb(*DEFAULT_EMBED_COLOR)
        )
        # Split the meanings
        meanings = '\n'.join(
            meaning
            for meaning in api_request.get('meanings')
        )
        splitted: list = split_into_chunks(meanings)
        embed.add_field(
            name="Meanings",
            value=splitted[0],
            inline=False
        )
        for part in splitted[1:]:
            embed.add_field(
                name="",
                value=part,
                inline=False
            )
        # Other fields
        # Set variables
        top_request = api_request.get('top')
        if top_request == 0:
            top = "Never used"
        else:
            top = f"Overall: Top {top_request}"
        alt_forms_request = api_request.get('alt_forms')
        if not alt_forms_request:
            alt_forms = "None"
        else:
            alt_forms = ', '.join(alt_forms_request)

        # Add extra fields
        embed.add_field(
            name='Alt forms',
            value=alt_forms,
            inline=True
        ).add_field(
            name='Kanji used',
            value='\n'.join(api_request.get('kanji')),
            inline=True
        ).add_field(
            name='Pitch accent',
            value=api_request.get('pitch'),
            inline=True
        ).add_field(
            name='Frequency',
            value=(
                f'\n> '.join([top]+api_request.get('other_frequencies'))
            ),
            inline=True
        ).add_field(
            name='Word types',
            value='\n> - '.join(api_request.get('types', '?')),
            inline=True
        )
        return embed

    @commands.slash_command(
        name="jpsearch",
        description='Search a Japanese word in a dictionary.',
        integration_types={
            discord.IntegrationType.guild_install,
        }
    )
    async def lookup(
        self,
        ctx: discord.ApplicationContext,
        word: discord.Option(
            str,
            description=(
                "The word you want to lookup. Can be romaji, kana or kanji."
            )
        ),  # type: ignore
    ) -> None:
        await ctx.defer()
        api_request = await word_api.get(word)
        if not api_request:
            await ctx.respond("Word not found !")
            return
        await ctx.respond(embed=self.create_embed(api_request))


def setup(bot):
    bot.add_cog(JpdbLookup(bot))
