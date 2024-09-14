import discord
from discord.ext import commands
from bot.vocal.session_manager import session_manager as sm


class Loop(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='loop',
        description='Loop/Unloop what you are listening to in VC.'
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
        session = sm.server_sessions.get(ctx.guild.id)

        if not session:
            await ctx.respond('Ugoku is not connected to any VC!')
            return

        mode = mode.lower()

        if mode == 'song':
            session.loop_current = not session.loop_current

            if session.loop_current:
                response = 'You are now looping the current song!'
            else:
                response = 'You are not looping the current song anymore.'

        elif mode == 'queue':
            session.loop_queue = not session.loop_queue

            if session.loop_queue:
                response = 'You are now looping the queue!'
                # Disable song loop when looping the queue
                session.loop_current = False
            else:
                # Clear loop queue when stopping queue loop
                session.to_loop = []
                response = 'You are not looping the queue anymore.'

        else:
            response = 'oi'

        await ctx.respond(response)


def setup(bot):
    bot.add_cog(Loop(bot))
