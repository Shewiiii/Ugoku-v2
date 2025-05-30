import asyncio
from typing import Optional
import discord
import httpx
import time
from config import DEFAULT_EMBED_COLOR

from bot.jpdb.word_api import word_api
from bot.utils import split_into_chunks


class JpdbFrontView(discord.ui.View):
    def __init__(
        self, card: dict, jpdb_session: dict, back_embed: discord.Embed
    ) -> None:
        super().__init__(timeout=None)
        self.jpdb_session = jpdb_session
        self.back_embed = back_embed
        self.card = card

    @discord.ui.button(label="Show answer", style=discord.ButtonStyle.secondary)
    async def show_answer_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        if self.jpdb_session.user_id != interaction.user.id:
            return
        asyncio.create_task(interaction.response.defer())
        back_view = JpdbBackView(self.card, self.jpdb_session, self.back_embed)
        await interaction.edit_original_response(embed=self.back_embed, view=back_view)


class JpdbBackView(discord.ui.View):
    def __init__(self, card: dict, jpdb_session, back_embed: discord.Embed) -> None:
        super().__init__(timeout=None)
        self.jpdb_session = jpdb_session
        self.back_embed = back_embed
        self.card = card
        self.colors = {
            "something": discord.Color.red(),
            "hard": discord.Color.orange(),
            "okay": discord.Color.green(),
            "easy": discord.Color.blurple(),
        }

    async def callback(self, interaction: discord.Interaction, grade: str) -> None:
        if self.jpdb_session.user_id != interaction.user.id:
            return
        asyncio.create_task(interaction.response.defer())
        self.back_embed.colour = self.colors[grade]
        await interaction.edit_original_response(view=None, embed=self.back_embed)
        await self.jpdb_session.grade_card(self.card["vid"], self.card["sid"], grade)
        await self.jpdb_session.show_card()

    @discord.ui.button(label="Again", style=discord.ButtonStyle.danger)
    async def again_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        await self.callback(interaction, "something")

    @discord.ui.button(label="Hard", style=discord.ButtonStyle.secondary)
    async def hard_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        await self.callback(interaction, "hard")

    @discord.ui.button(label="Okay", style=discord.ButtonStyle.green)
    async def okay_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        await self.callback(interaction, "okay")

    @discord.ui.button(label="Easy", style=discord.ButtonStyle.blurple)
    async def easy_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        await self.callback(interaction, "easy")

    @discord.ui.button(label="Expand", style=discord.ButtonStyle.gray)
    async def expand_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        """Add all the info contained in the card dict to the embed."""
        if self.jpdb_session.user_id != interaction.user.id:
            return
        asyncio.create_task(interaction.response.defer())

        embed = self.back_embed
        # Set variables
        top_request = self.card.get("top")
        if top_request == 0:
            top = "Never used"
        else:
            top = f"Overall: Top {top_request}"
        alt_forms_request = self.card.get("alt_forms")
        if not alt_forms_request:
            alt_forms = "None"
        else:
            alt_forms = ", ".join(alt_forms_request)

        # Add extra fields
        embed.add_field(name="Alt forms", value=alt_forms, inline=True).add_field(
            name="Kanji used", value="\n".join(self.card.get("kanji")), inline=True
        ).add_field(
            name="Word types",
            value="\n> - ".join(self.card.get("types", "?")),
            inline=True,
        ).add_field(
            name="Frequency",
            value=("\n> ".join([top] + self.card.get("other_frequencies"))),
            inline=True,
        )
        self.remove_item(button)
        await interaction.edit_original_response(embed=embed, view=self)


class Jpdb:
    def __init__(
        self,
        user_id: int,
        api_key: str,
        init_message: discord.WebhookMessage,
        ctx: Optional[discord.ApplicationContext] = None,
    ) -> None:
        self.user_id = user_id
        self.api_key = api_key
        self.session = httpx.AsyncClient(follow_redirects=True)
        self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})
        self.base_url = "https://jpdb.io/api/v1/"
        self.vocab = []
        self.review_cards = []
        self.ctx = ctx
        self.init_message = init_message

    async def check_api_key(self) -> None:
        ping = await self.session.get(f"{self.base_url}ping")
        if ping.status_code == 403:
            raise ValueError("Invalid JPDB API key")

    async def get_all_vocab(self, deck_id: Optional[int] = None) -> list:
        """Save all the vocabulary from "All vocabulary" special deck into self.vocab variable.
        Should be executed once per deck.
        Fields:
            vid (int)
            sid (int)
            spelling (str)
            reading (str)
            frequency_rank (int): across jpdb's corpus
            card_state (list): 'due', 'new', 'known'...
            due_at (int): Seconds since epoch
            alt_spellings (list)
            meanings_chunks (list)
        """
        # Get the first deck id if not given
        if not deck_id:
            special_decks_response = await self.session.post(
                f"{self.base_url}list-user-decks", json={"fields": ["id"]}
            )
            special_decks_response.raise_for_status()
            deck_id = special_decks_response.json()["decks"][0][0]

        # First request to '/deck/list-vocabulary'
        list_vocab_response = await self.session.post(
            f"{self.base_url}deck/list-vocabulary", json={"id": deck_id}
        )
        list_vocab_response.raise_for_status()
        list_vocab_data = list_vocab_response.json()

        # Second request to '/lookup-vocabulary'
        lookup_payload = {
            "list": list_vocab_data["vocabulary"],
            "fields": [
                "vid",
                "sid",
                "spelling",
                "reading",
                "frequency_rank",
                "card_state",
                "due_at",
                "alt_spellings",
                "meanings_chunks",
            ],
        }

        lookup_response = await self.session.post(
            f"{self.base_url}lookup-vocabulary", json=lookup_payload
        )
        lookup_response.raise_for_status()
        lookup_data = lookup_response.json()

        # put data lists into a dicts
        vocab_dicts = []
        for item in lookup_data["vocabulary_info"]:
            vocab_dicts.append(
                {
                    "vid": item[0],
                    "sid": item[1],
                    "spelling": item[2],
                    "reading": item[3],
                    "frequency_rank": item[4],
                    "card_state": item[5],
                    "due_at": item[6],
                    "alt_spellings": item[7],
                    "meanings_chunks": item[8],
                }
            )

        self.vocab = vocab_dicts

    def sort_vocab_by_frequency(self) -> list:
        if not self.vocab:
            return []
        self.vocab.sort(
            key=lambda x: x["frequency_rank"]
            if x["frequency_rank"] is not None
            else float("inf")
        )
        return self.vocab

    def get_cards(self, card_state: str, limit: int = 9999) -> list:
        if self.vocab is None:
            return
        cards = []
        i = 0
        for card in self.vocab:
            if (
                card_state in card["card_state"]
                and "redundant" not in card["card_state"]
            ):
                cards.append(card)
                i += 1
                if i >= limit:
                    break

        return cards

    def get_new_cards(self, limit=20) -> list:
        return self.get_cards("new", limit)

    def get_due_cards(self) -> list:
        due_cards = []
        current_timestamp = int(time.time())
        for card in self.vocab:
            if card["due_at"] and card["due_at"] < current_timestamp:
                due_cards.append(card)
        return due_cards

    def update_review_cards(self) -> list:
        self.review_cards = self.get_due_cards()
        if not self.review_cards:
            self.review_cards = self.get_new_cards()
        return self.review_cards

    async def grade_card(self, vid: int, sid: int, grade: str) -> None:
        """Allowed values: nothing, something, hard, okay, easy (or pass/fail)."""
        review_response = await self.session.post(
            f"{self.base_url}review", json={"vid": vid, "sid": sid, "grade": grade}
        )
        review_response.raise_for_status()

        # Lookup the card again to get the due date
        lookup_response = await self.session.post(
            f"{self.base_url}lookup-vocabulary",
            json={
                "list": [[vid, sid]],
                "fields": ["due_at"],
            },
        )
        lookup_response.raise_for_status()
        lookup_data = lookup_response.json()

        # Find the good card to update (should be at the very beginning)
        for i, card in enumerate(self.vocab):
            if card.get("vid") == vid and card.get("sid") == sid:
                self.vocab[i]["due_at"] = lookup_data["vocabulary_info"][0][0]
                break

    def create_front_embed(
        self,
        card: dict,
        sentences: dict,
    ) -> discord.Embed:
        embed = (
            discord.Embed(
                title=card.get("spelling", "?"),
                description=sentences.get("jp", ""),
                url=(
                    f"https://jpdb.io/vocabulary/{card.get('vid')}/"
                    f"{card.get('spelling')}/{card.get('reading')}"
                ),
                color=discord.Colour.from_rgb(*DEFAULT_EMBED_COLOR),
            )
            .add_field(name="Top", value=f"{card.get('top')}", inline=True)
            .add_field(
                name="Due",
                value=f"{self.get_day_delta(card.get('due_at'))} days ago",
                inline=True,
            )
            .add_field(name="Remaining", value=f"{len(self.review_cards)}", inline=True)
            .set_author(name="jpdb", icon_url=self.ctx.author.avatar.url)
        )
        return embed

    def create_back_embed(self, card: dict, sentences: dict) -> discord.Embed:
        jp_sentence = sentences.get("jp", "")
        en_sentence = sentences.get("en", "")
        reading = card.get("reading", "")
        embed = discord.Embed(
            title=card.get("spelling", "?"),
            description="\n".join([reading, jp_sentence, en_sentence]),
            url=(
                f"https://jpdb.io/vocabulary/{card.get('vid')}/"
                f"{card.get('spelling')}/{card.get('reading')}"
            ),
            color=discord.Colour.from_rgb(*DEFAULT_EMBED_COLOR),
        )
        # Meanings
        meanings = "\n".join(
            f"{i + 1}. {', '.join(meaning_chunk)}"
            for i, meaning_chunk in enumerate(card.get("meanings_chunks", []))
        )
        splitted: list = split_into_chunks(meanings)
        embed.add_field(name="Meanings", value=splitted[0], inline=False)
        for part in splitted[1:]:
            embed.add_field(name="", value=part, inline=False)
        # Other fields
        embed.add_field(
            name="Top", value=f"{card.get('top', '0')}", inline=True
        ).add_field(
            name="Due",
            value=f"{self.get_day_delta(card.get('due_at'))} days ago",
            inline=True,
        ).add_field(
            name="Pitch accent", value=card.get("pitch", ""), inline=True
        ).set_author(name="jpdb", icon_url=self.ctx.author.avatar.url)
        return embed

    def get_front_view(self, card: dict, sentences: dict) -> JpdbFrontView:
        back_embed = self.create_back_embed(card, sentences)
        view = JpdbFrontView(card, self, back_embed)
        return view

    async def show_card(self) -> None:
        review_cards = self.update_review_cards()
        if not review_cards or not self.ctx:
            await self.ctx.send(
                "Congratulations ! You reviewed all your cards in the current deck~"
            )
            return
        card: dict = review_cards[0]
        word = review_cards[0]["spelling"]
        if "pitch" not in card:
            # Complete the card dict
            card.update(await word_api.get(word))
        sentences = await word_api.generate_example_sentence(word, card["meanings"])
        embed = self.create_front_embed(card, sentences)
        view = self.get_front_view(card, sentences)
        await self.init_message.edit(content="", embed=embed, view=view)

    @staticmethod
    def get_day_delta(timestamp: int) -> int:
        """Returns de delta between the current timestamp and the given one in days."""
        if not timestamp:
            return 0
        current_timestamp = int(time.time())
        delta = int((current_timestamp - timestamp) / (3600 * 24))
        return delta


class JpdbSessions:
    def __init__(self) -> None:
        self.jpdb_sessions = {}

    async def get_session(
        self,
        ctx: discord.ApplicationContext,
        init_message: discord.WebhookMessage,
        api_key: Optional[str] = None,
    ) -> Jpdb:
        user_id = ctx.author.id
        session: Jpdb = self.jpdb_sessions.get(user_id)
        if session:
            session.ctx = ctx
            session.init_message = init_message
            return session
        elif not api_key:
            raise ValueError("No API key provided")

        # Else, create a new session
        session = Jpdb(user_id, api_key, ctx=ctx, init_message=init_message)
        # Raise a ValueError if invalid
        await session.check_api_key()
        self.jpdb_sessions[user_id] = session
        return session


jpdb_sessions = JpdbSessions()
