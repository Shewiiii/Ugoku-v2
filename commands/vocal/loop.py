import discord
from discord.ext import commands
from bot.vocal import server_sessions, ServerSession


class Loop(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='loop',
        description='Loop/Unloop what you are listening to in vc.'
    )
    async def loop(
        self,
        ctx: discord.ApplicationContext,
        mode: discord.Option(
            str,
            choices=['Song', 'Queue'],
            default='Song'
        )  # type: ignore
    ) -> None:
        session = server_sessions.get(ctx.guild.id)

        if not session:
            await ctx.respond('Ugoku is not connected to any vc!')
            return

        mode = mode.lower()
        if mode == 'song':
            session.loop_current = not session.loop_current
            response = 'You are now looping the current song!' if session.loop_current else 'You are not looping the current song anymore.'
            await ctx.respond(response)

        elif mode == 'queue':
            session.loop_queue = not session.loop_queue
            response = 'You are now looping the queue!' if session.loop_queue else 'You are not looping the queue anymore.'
            if not session.loop_queue:
                session.to_loop = []
            await ctx.respond(response)

        else:
            await ctx.respond('oi')


def setup(bot):
    bot.add_cog(Loop(bot))
