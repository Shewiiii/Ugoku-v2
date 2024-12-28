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
            choices=['default']+[effect for effect in IMPULSE_RESPONSE_PARAMS],

        ),  # type: ignore
        effect_only: discord.Option(
            bool,
            description="Remove the original audio from the mix.",
            default=False
        ),  # type: ignore
        dry: discord.Option(
            int,
            description="[VOLUME WARNING] Amount of signal before processing (from 1 to 10).",
            default=0
        ),  # type: ignore
        wet: discord.Option(
            int,
            description="[VOLUME WARNING] Amount of signal after processing (from 1 to 10).",
            default=0
        )  # type: ignore
    ) -> None:
        guild_id = ctx.guild.id
        session = sm.server_sessions.get(guild_id)
        if not session:
            await ctx.respond("No active session!")
            return

        if wet > 10 or dry > 10:
            await ctx.respond("Incorrect wet or dry values !")
            return

        p = IMPULSE_RESPONSE_PARAMS.get(effect)
        session.audio_effect.effect = effect if p else None
        wet_value = wet or p.get('wet', 0) if p else 0
        dry_value = dry or p.get('dry', 0) if p else 10
        volume_value = p.get('volume_multiplier', 1) if p else 1

        # If not default effect
        if p:
            attrs = {
                'left_ir_file': p.get('left_ir_file', ''),
                'right_ir_file': p.get('right_ir_file', ''),
                'effect_only': effect_only,
                'wet': wet_value,
                'dry': dry_value,
                'volume_multiplier': volume_value
            }
            for attr, value in attrs.items():
                setattr(session.audio_effect, attr, value)

        current_pos = session.time_elapsed + \
            int((datetime.now() - session.last_played_time).total_seconds())
        await ctx.respond(
            f"Applying the {effect} effect!\n"
            f"> Dry: {dry_value}\n"
            f"> Wet: {wet_value}\n"
            f"> Volume multiplier: {volume_value}"
        )
        await session.seek(current_pos, quiet=True)


def setup(bot):
    bot.add_cog(AudioEffects(bot))
