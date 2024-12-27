import discord
from discord.ext import commands
from datetime import datetime

from bot.vocal.session_manager import session_manager as sm
from bot.vocal.server_session import ServerSession
from config import IMPULSE_RESPONSE_PARAMS


class AudioEffects(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name='audio-effect',
        description='Apply an audio effect to the now playing song !'
    )
    async def effect(
        self,
        ctx: discord.ApplicationContext,
        effect: discord.Option(
            str,
            description="The audio effect to apply.",
            choices=["default"]+[effect for effect in IMPULSE_RESPONSE_PARAMS],

        ),  # type: ignore
        effect_only: discord.Option(
            bool,
            description="Remove the original audio from the mix.",
            default=False
        )  # type: ignore
    ) -> None:
        guild_id = ctx.guild.id
        session: ServerSession | None = sm.server_sessions.get(guild_id)

        if not session:
            await ctx.respond("No active session!")
            return

        session.audio_effect.effect = effect
        session.audio_effect.effect_only = effect_only
        current_pos: int = (
            session.time_elapsed +
            (datetime.now() - session.last_played_time).seconds
        )
        await ctx.respond(f"Applying the {effect} effect !")
        await session.seek(current_pos, quiet=True)


def setup(bot):
    bot.add_cog(AudioEffects(bot))
