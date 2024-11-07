import discord
from discord.ext import commands
from bot.chatbot import Chat, Prompts

from config import LANGUAGES, CHATBOT_WHITELIST, CHATBOT_ENABLED


class Test(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='translate',
        description='Translate any sentence to a language.',
        integration_types={
            discord.IntegrationType.user_install
        }
    )
    async def translate(
        self,
        ctx: discord.ApplicationContext,
        query: str,
        language: discord.Option(
            str,
            choices=LANGUAGES,
            required=True,
            default='English'

        ),  # type: ignore
        nuance: discord.Option(
            str,
            choices=['Neutral', 'Casual', 'Formal'],
            required=True,
            default='Neutral'

        ),  # type: ignore
        ephemeral: bool = True
    ) -> None:
        prompt = f'''
            Convert these text to {nuance} {language}.
            If there is no text, return nothing.
            Keep emojis (between <>).
            Don't add ANY extra text:
        '''
        await ctx.respond("Translating~", ephemeral=ephemeral)
        response = await Chat.simple_prompt(message=prompt+query)
        await ctx.edit(content=response)

    @commands.slash_command(
        name='ask',
        description='Ask Ugoku anything !',
        integration_types={
            discord.IntegrationType.user_install,
            discord.IntegrationType.guild_install
        }
    )
    async def ask(
        self,
        ctx: discord.ApplicationContext,
        query: str,
        ephemeral: bool = True
    ) -> None:
        if not CHATBOT_ENABLED:
            ctx.respond("Chatbot features are not enabled.")
        if ctx.guild.id not in CHATBOT_WHITELIST:
            await ctx.respond("This server is not allowed to use that command.")
            return

        await ctx.respond("Thinking..", ephemeral=ephemeral)
        response = await Chat.simple_prompt(
            message=query,
            system_prompt=Prompts.system+Prompts.single_question
        )
        await ctx.edit(content=response)


def setup(bot):
    bot.add_cog(Test(bot))
