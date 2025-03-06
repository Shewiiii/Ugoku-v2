import discord
from discord.ext import commands

from config import *
import logging


class ConfigCommand(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.slash_command(
        name="config",
        description='Check the current config of the bot.',
        integration_types={
            discord.IntegrationType.guild_install
        }
    )
    async def config(self, ctx: discord.ApplicationContext) -> None:
        e = {True: '✅', False: '❌', 'misc': ":diamond_shape_with_a_dot_inside:"}
        features = '\n'.join([
            f"{e[SPOTIFY_API_ENABLED]} **Spotify API**",
            f"{e[SPOTIFY_ENABLED]} **Spotify client**: Librespot",
            f"{e[DEEZER_ENABLED]} **Deezer service**",
            f"{e[GEMINI_ENABLED]} **Gemini features**",
            f"{e[ALLOW_CHATBOT_IN_DMS]} Chatbot enabled in DMs",
            f"{e[ctx.guild_id in CHATBOT_WHITELIST]} Chatbot enabled in this server",
            f'''{e[PINECONE_ENABLED]} Pinecone features (the chatbot's "memory")''',
        ])
        audio_settings = '\n'.join([
            f"{e['misc']} Inactivity before leaving vc: {AUTO_LEAVE_DURATION}s",
            f"{e['misc']} Default audio volume: {DEFAULT_AUDIO_VOLUME}%",
            f"{e['misc']} Default onsei volume: {DEFAULT_ONSEI_VOLUME}%",
            f"{e['misc']} Default audio bitrate: {DEFAULT_AUDIO_BITRATE}Kbps",

        ])
        chatbot_settings = '\n'.join([
            f"{e['misc']} Chatbot model: {GEMINI_MODEL}",
            f"{e['misc']} Chatbot temperature: {CHATBOT_TEMPERATURE}",
            f"{e[bool(CHATBOT_EMOTES)]} Chatbot emotes",
            f"{e['misc']} Chatbot emote frequency: {CHATBOT_EMOTE_FREQUENCY:.1f}",
            f"{e['misc']} Chatbot history size: {GEMINI_HISTORY_SIZE}",
            f"{e['misc']} Max output token per message: {CHATBOT_MAX_OUTPUT_TOKEN}",
            f"{e['misc']} Max number of recalled messages per response: {PINECONE_RECALL_WINDOW}",
            f"{e['misc']} Max chatbot file size (if supported): \n- {'\n- '.join([f'{type_}: {size_/10**6:.1f}MB' for type_,
                                                                                  size_ in CHATBOT_MAX_CONTENT_SIZE.items()])}",
        ])
        other = '\n'.join([
            f"{e['misc']} Default embed color RGB: {DEFAULT_EMBED_COLOR}",
            f"{e[PREMIUM_CHANNEL_ID is not None]} Upload big files in a boosted server's channel",
            f"{e[bool(IMPULSE_RESPONSE_PARAMS)]} Impulse responses for convolution (audio effects)",
            f"{e['misc']} Include keywords in the onsei folder structure: {', '.join(ONSEI_WHITELIST)}",
            f"{e['misc']} Ignore keywords in the onsei folder structure: {', '.join(ONSEI_BLACKLIST)}",
            f"{e['misc']} Gemini model for other tasks: {GEMINI_MODEL}",
            f"{e['misc']} Supported languages by /translate: {len(LANGUAGES)}",
        ])

        config_embed = discord.Embed(
            title="Current config",
            description="Below is the current front-end configuration used on Ugoku. Read-only.",
            color=discord.Colour.from_rgb(*DEFAULT_EMBED_COLOR)
        ).add_field(
            name="Features",
            value=features,
            inline=False
        ).add_field(
            name="Audio settings",
            value=audio_settings,
            inline=False
        ).add_field(
            name="Chatbot settings",
            value=chatbot_settings,
            inline=False
        ).add_field(
            name="Other",
            value=other,
            inline=False
        )

        await ctx.respond(embed=config_embed)


def setup(bot):
    bot.add_cog(ConfigCommand(bot))
