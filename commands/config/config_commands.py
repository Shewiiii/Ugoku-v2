import discord
from discord.ext import commands
import logging
import re

from bot.config import sqlite_config_manager
from bot.utils import split_into_chunks


whitelist_choice = [
    "onsei_server",
    "chatbot_server",
    "gemini_server",
    "premium_gemini_user_id",
]

# Dictionary for user-friendly display names
WHITELIST_DISPLAY_NAMES = {
    "onsei_server": "Onsei Server Whitelist",
    "chatbot_server": "Chatbot Server Whitelist",
    "gemini_server": "Gemini Server Whitelist",
    "premium_gemini_user_id": "Gemini premium user IDs",
}


class DatabaseSettingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    database_cmds = discord.SlashCommandGroup(
        "database", "Commands for managing bot database configurations."
    )

    @database_cmds.command(
        name="add_emote",
        description="Add or update a chatbot emote in the database (Owner only).",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    @commands.is_owner()
    async def add_emote(
        self,
        ctx: discord.ApplicationContext,
        name: discord.Option(
            str, description="The keyword for the emote (e.g. happy, sad)."
        ),  # type: ignore
        emote_value: discord.Option(
            str,
            description=(
                "The emote snowflake (e.g. <:emote_name:12345>). "
                'Send an emote then put "\\" before to get it.'
            ),
        ),  # type: ignore
    ):
        try:
            if not re.fullmatch(r"<a?:[A-Za-z0-9_]+:\d+>", emote_value):
                await ctx.respond(
                    "Invalid emote format. Please use the snowflake format "
                    "(for example `<:emote_name:12345>`).",
                    ephemeral=True,
                )
                return
            sqlite_config_manager.add_or_update_chatbot_emote(name, emote_value)
            await ctx.respond(
                f"Added `{emote_value}` in the database !",
                ephemeral=True,
            )
        except Exception as e:
            logging.error(f"Error in add_emote command: {e}", exc_info=True)
            await ctx.respond(f"Error updating emote in database: {e}", ephemeral=True)

    @database_cmds.command(
        name="remove_emote",
        description="Remove a chatbot emote from the database (Owner only).",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    @commands.is_owner()
    async def remove_emote(
        self,
        ctx: discord.ApplicationContext,
        name: discord.Option(str, description="The keyword of the emote to remove."),  # type: ignore
    ):
        try:
            if sqlite_config_manager.remove_chatbot_emote(name):
                await ctx.respond(
                    f"Chatbot emote '{name}' has been removed from the database.",
                    ephemeral=True,
                )
            else:
                await ctx.respond(
                    f"Chatbot emote '{name}' not found in the database.", ephemeral=True
                )
        except Exception as e:
            logging.error(f"Error in remove_emote command: {e}", exc_info=True)
            await ctx.respond(
                f"Error removing emote from database: {e}", ephemeral=True
            )

    @database_cmds.command(
        name="add_to_whitelist",
        description="Add a server/user/channel ID to a whitelist in the database (Owner only).",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    @commands.is_owner()
    async def add_to_whitelist(
        self,
        ctx: discord.ApplicationContext,
        list_name: discord.Option(
            str,
            description="The whitelist to modify.",
            choices=whitelist_choice,
        ),  # type: ignore
        id: discord.Option(
            str,  # str here because integers can't be too long
            description="The ID to add.",
        ),  # type: ignore
    ):
        try:
            sqlite_config_manager.add_to_whitelist(
                list_name, id
            )  # list_name is now a string from whitelist_choice
            display_list_name = WHITELIST_DISPLAY_NAMES.get(
                list_name, list_name.replace("_", " ").title()
            )
            await ctx.respond(
                f"Server ID {id} added to {display_list_name} in the database.",
                ephemeral=True,
            )
        except ValueError:
            await ctx.respond("The server ID must be an integer !")
        except Exception as e:
            logging.error(f"Error in add_to_whitelist command: {e}", exc_info=True)
            await ctx.respond(
                f"Error adding to whitelist in database: {e}", ephemeral=True
            )

    @database_cmds.command(
        name="remove_from_whitelist",
        description="Remove a server ID from a whitelist in the database (Owner only).",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    @commands.is_owner()
    async def remove_from_whitelist(
        self,
        ctx: discord.ApplicationContext,
        list_name: discord.Option(
            str,
            description="The whitelist to modify.",
            choices=whitelist_choice,
        ),  # type: ignore
        server_id: discord.Option(
            str,  # str here because integers can't be too long
            description="The server ID to remove.",
        ),  # type: ignore
    ):
        try:
            server_id = int(server_id)
            display_list_name = WHITELIST_DISPLAY_NAMES.get(
                list_name, list_name.replace("_", " ").title()
            )
            if sqlite_config_manager.remove_from_whitelist(
                list_name, server_id
            ):  # list_name is a string
                await ctx.respond(
                    f"Server ID {server_id} removed from {display_list_name} in the database.",
                    ephemeral=True,
                )
            else:
                await ctx.respond(
                    f"Server ID {server_id} not found in {display_list_name} in the database.",
                    ephemeral=True,
                )
        except ValueError:
            await ctx.respond("The server ID must be an integer !")
        except Exception as e:
            logging.error(f"Error in remove_from_whitelist command: {e}", exc_info=True)
            await ctx.respond(
                f"Error removing from whitelist in database: {e}", ephemeral=True
            )

    @database_cmds.command(
        name="backend_config",
        description="View current configurations from the database (Owner only).",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    @commands.is_owner()
    async def backend_config(
        self,
        ctx: discord.ApplicationContext,
    ):
        try:
            embed = discord.Embed(
                title="Bot Database Configurations", color=discord.Color.blue()
            )

            # Emote field
            emotes = sqlite_config_manager.get_all_chatbot_emotes()
            if emotes:
                emotes_value = "\n".join(
                    [f"`{name}`: {value}" for name, value in emotes.items()]
                )
                chunks = split_into_chunks(emotes_value)
                field_name = "Chatbot Emotes"
                for chunk in chunks:
                    embed.add_field(name=field_name, value=chunk, inline=False)
                    field_name = ""
            else:
                embed.add_field(
                    name="Chatbot Emotes", value="No emotes configured.", inline=False
                )

            # Whitelist fields
            for value, name in WHITELIST_DISPLAY_NAMES.items():
                ids = sqlite_config_manager.get_whitelist(value)
                chunks = split_into_chunks("\n".join(str(id) for id in list(ids)))
                if not chunks:
                    chunks = ["Whitelist is empty."]
                field_name = name
                for chunk in chunks:
                    embed.add_field(name=field_name, value=chunk, inline=False)
                    field_name = ""

            await ctx.respond(embed=embed, ephemeral=True)

        except Exception as e:
            logging.error(f"Error in view_config command: {e}", exc_info=True)
            await ctx.respond(f"Error viewing configurations: {e}", ephemeral=True)


def setup(bot: discord.Bot):
    bot.add_cog(DatabaseSettingsCog(bot))
