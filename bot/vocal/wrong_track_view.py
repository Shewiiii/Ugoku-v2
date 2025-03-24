import asyncio
import discord
from discord.ui import View

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from bot.vocal.server_session import ServerSession


class WrongTrackView(View):
    def __init__(
        self,
        ctx: discord.ApplicationContext,
        display_name: str,
        session: "ServerSession",
        original_message: str,
        user_query: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.ctx: discord.ApplicationContext = ctx
        self.session: "ServerSession" = session
        self.original_message = original_message
        self.display_name: str = display_name
        self.user_query: Optional[str] = user_query

    @discord.ui.button(label="Wrong track ?", style=discord.ButtonStyle.secondary)
    async def wrong_button_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        if interaction.user.id != self.ctx.user.id:
            return

        skip_cog = self.session.bot.get_cog("Skip")
        search_cog = self.session.bot.get_cog("Search")
        asyncio.create_task(
            interaction.response.edit_message(content=self.original_message, view=None)
        )

        if not self.session.queue:
            return

        if str(self.session.queue[0]) == self.display_name:
            asyncio.create_task(skip_cog.execute_skip(self.ctx, silent=True))
        else:
            for i, track in enumerate(self.session.queue):
                if str(track) == self.display_name:
                    self.session.queue.pop(i)
                    break
            asyncio.create_task(
                self.session.update_now_playing(self.ctx, edit_only=True)
            )

        asyncio.create_task(
            search_cog.execute_search(
                self.ctx,
                type="track",
                query=self.user_query if self.user_query else self.display_name,
                interaction=interaction,
            )
        )

    def close(self) -> None:
        self.ctx = self.session = self.original_message = None
