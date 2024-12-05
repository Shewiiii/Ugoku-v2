import discord
from discord.ext import commands
from bot.jpdb.jpdb import Jpdb, jpdb_sessions


class JpdbReview(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name="review",
        description='Review your cards from JPDB !',
        integration_types={
            discord.IntegrationType.guild_install,
        }
    )
    async def review(
        self,
        ctx: discord.ApplicationContext,
        deck_id: discord.Option(
            int,
            required=False,
            description=(
                "Specify the id of the deck you want to review."
                "Defaults to the first one in your list."
            )
        ),  # type: ignore
        api_key: discord.Option(
            str,
            required=False,
            description=(
                "Your JPDB API key you can find in the settings. "
                "Will be saved in memory for your next review."
            )
        ),  # type: ignore
    ) -> None:
        try:
            session: Jpdb = await jpdb_sessions.get_session(ctx, api_key)
        except:
            await ctx.respond('Please enter a valid API key !', ephemeral=True)
            return
        await ctx.respond('Loading !', ephemeral=True)
        await session.get_all_vocab(deck_id)
        session.sort_vocab_by_frequency()
        await session.show_card()

def setup(bot):
    bot.add_cog(JpdbReview(bot))
