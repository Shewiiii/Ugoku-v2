import discord
from discord.ext import commands
import os

from config import (
    SPOTIFY_API_ENABLED,
    SPOTIFY_ENABLED,
    DEEZER_ENABLED,
    GEMINI_ENABLED,
    ALLOW_CHATBOT_IN_DMS,
    CHATBOT_SERVER_WHITELIST,
    PINECONE_ENABLED,
    AUTO_LEAVE_DURATION,
    DEFAULT_AUDIO_BITRATE,
    DEFAULT_ONSEI_VOLUME,
    DEFAULT_EMBED_COLOR,
    DEFAULT_AUDIO_VOLUME,
    DEFAULT_STREAMING_SERVICE,
    GEMINI_MODEL,
    CHATBOT_TEMPERATURE,
    CHATBOT_EMOTES,
    CHATBOT_MAX_CONTENT_SIZE,
    CHATBOT_MAX_OUTPUT_TOKEN,
    CHATBOT_EMOTE_FREQUENCY,
    CHATBOT_TIMEZONE,
    GEMINI_HISTORY_SIZE,
    PINECONE_RECALL_WINDOW,
    PREMIUM_CHANNEL_ID,
    IMPULSE_RESPONSE_PARAMS,
    ONSEI_WHITELIST,
    ONSEI_BLACKLIST,
    LANGUAGES,
)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")


class ConfigCommand(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name="config",
        description="Check the current config of the bot.",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def config(self, ctx: discord.ApplicationContext) -> None:
        e = {True: "✅", False: "❌", "misc": ":diamond_shape_with_a_dot_inside:"}
        features = "\n".join(
            [
                f"{e[SPOTIFY_API_ENABLED]} **Spotify API**",
                f"{e[SPOTIFY_ENABLED]} **Spotify client**: Librespot",
                f"{e[DEEZER_ENABLED]} **Deezer service**",
                f"{e[GEMINI_ENABLED]} **Gemini features**",
                f"{e[ALLOW_CHATBOT_IN_DMS]} Chatbot enabled in DMs",
                f"{e[ctx.guild_id in CHATBOT_SERVER_WHITELIST]} Chatbot enabled in this server",
                f"""{e[PINECONE_ENABLED]} Pinecone features (the chatbot's "memory")""",
            ]
        )
        audio_settings = "\n".join(
            [
                f"{e['misc']} Default Streaming service: {DEFAULT_STREAMING_SERVICE}",
                f"{e['misc']} Inactivity before leaving vc: {AUTO_LEAVE_DURATION}s",
                f"{e['misc']} Default audio volume: {DEFAULT_AUDIO_VOLUME}%",
                f"{e['misc']} Default onsei volume: {DEFAULT_ONSEI_VOLUME}%",
                f"{e['misc']} Default audio bitrate: {DEFAULT_AUDIO_BITRATE}Kbps",
                f"{e[bool(YOUTUBE_API_KEY)]} Youtube playlist URLs support",
            ]
        )
        chatbot_settings = "\n".join(
            [
                f"{e['misc']} Chatbot model: {GEMINI_MODEL}",
                f"{e['misc']} Chatbot temperature: {CHATBOT_TEMPERATURE}",
                f"{e[bool(CHATBOT_EMOTES)]} Chatbot emotes: {len(CHATBOT_EMOTES)}",
                f"{e['misc']} Chatbot emote frequency: {CHATBOT_EMOTE_FREQUENCY:.1f}",
                f"{e['misc']} Chatbot history size: {GEMINI_HISTORY_SIZE}",
                f"{e['misc']} Chatbot timezone: {CHATBOT_TIMEZONE}",
                f"{e['misc']} Max output token per message: {CHATBOT_MAX_OUTPUT_TOKEN}",
                f"{e['misc']} Max number of recalled messages per response: {PINECONE_RECALL_WINDOW}",
                f"{e['misc']} Max chatbot file size (if supported): \n- {
                    '\n- '.join(
                        [
                            f'{type}: {size_ / 10**6:.1f}MB'
                            for type, size_ in CHATBOT_MAX_CONTENT_SIZE.items()
                        ]
                    )
                }",
            ]
        )
        other = "\n".join(
            [
                f"{e['misc']} Default embed color RGB: {DEFAULT_EMBED_COLOR}",
                f"{e[PREMIUM_CHANNEL_ID is not None]} Upload big files in a boosted server's channel",
                f"{e[bool(IMPULSE_RESPONSE_PARAMS)]} Impulse responses for convolution (audio effects)",
                f"{e['misc']} Include keywords in the onsei folder structure: {', '.join(ONSEI_WHITELIST)}",
                f"{e['misc']} Ignore keywords in the onsei folder structure: {', '.join(ONSEI_BLACKLIST)}",
                f"{e['misc']} Gemini model for other tasks: {GEMINI_MODEL}",
                f"{e['misc']} Supported languages by /translate: {len(LANGUAGES)}",
            ]
        )

        config_embed = (
            discord.Embed(
                title="Current config",
                description="Below is the current front-end configuration used on Ugoku. Read-only.",
                color=discord.Colour.from_rgb(*DEFAULT_EMBED_COLOR),
            )
            .add_field(name="Features", value=features, inline=False)
            .add_field(name="Audio settings", value=audio_settings, inline=False)
            .add_field(name="Chatbot settings", value=chatbot_settings, inline=False)
            .add_field(name="Other", value=other, inline=False)
        )

        await ctx.respond(embed=config_embed, ephemeral=True)


def setup(bot):
    bot.add_cog(ConfigCommand(bot))
