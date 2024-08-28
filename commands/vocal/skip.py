from discord.ext import commands
import discord

from bot.vocal import ServerSession, server_sessions


class Skip(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='skip',
        description='Skip the current song.'
    )
    async def skip(self, ctx: discord.ApplicationContext) -> None:
        guild_id = ctx.guild.id

        if guild_id not in server_sessions:
            await ctx.respond('No songs in queue!')
            return

        session: ServerSession = server_sessions[guild_id]

        if session.queue:
            if session.loop_current:
                session.queue.pop(0)

            session.skipped = True
            if len(session.queue) == 1:
                session.voice_client.stop()
            else:
                # Less latency, ffmpeg process not terminated
                session.voice_client.pause()
                await session.play_next(ctx)
            await ctx.respond('Skipped!')
        else:
            await ctx.respond('No songs in queue!')


def setup(bot):
    bot.add_cog(Skip(bot))
