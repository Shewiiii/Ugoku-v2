from aiohttp_client_cache import CachedSession, SQLiteBackend
from bs4 import BeautifulSoup
import json
import re
from typing import Optional
import typing_extensions as typing


from bot.chatbot.gemini import Gembot
from config import GEMINI_ENABLED, GEMINI_UTILS_MODEL, CACHE_EXPIRY
import google.generativeai as genai


class SentenceLanguage(typing.TypedDict):
    jp: str
    en: str


class JpdbWordApi:
    def __init__(self):
        self.gembot = Gembot(0, GEMINI_UTILS_MODEL) if GEMINI_ENABLED else None

    @staticmethod
    def extract_pitch_accent(pitch_section: BeautifulSoup) -> str:
        if not pitch_section:
            return ""

        pitch_container = pitch_section.find("div", class_="subsection")
        if not pitch_container:
            return ""

        # First pitch accent
        first_pitch = pitch_container.find("div").find("div")

        moras = []
        kana = []
        pitch_pattern = []
        drop_at_end = False

        # Extract moras and kana
        for child_div in first_pitch.find_all("div", recursive=True):
            style = child_div.get("style", "")
            if "linear-gradient" in style:
                moras.append(child_div)
            elif "background-color" in style:
                kana_text = child_div.get_text(strip=True)
                kana.append(kana_text)

        # Map style to pitch
        for mora in moras:
            style = mora.get("style", "")
            if "--pitch-high-s" in style:
                pitch = "H"
            elif "--pitch-low-s" in style:
                pitch = "L"
            else:
                pitch = ""

            if pitch:
                pitch_pattern.append(pitch)

        # Check if the last mora has "margin-right: -2px" to determine
        # if the word is odaka or not
        if moras:
            last_mora_style = moras[-1].get("style", "")
            if "margin-right: -2px" in last_mora_style:
                drop_at_end = True

        # Build the final pattern by mapping pitches to kana chunks
        final_pattern = ""
        for i, kana_chunk in enumerate(kana):
            if i >= len(pitch_pattern):
                break
            pitch = pitch_pattern[i]
            final_pattern += pitch * len(kana_chunk)

        # Append '(L)' if the pitch drops at the end
        if drop_at_end:
            final_pattern += "(L)"

        return final_pattern

    async def get(self, word: str) -> Optional[dict]:
        base_url = "https://jpdb.io/search?q="
        async with CachedSession(
            follow_redirects=True,
            cache=SQLiteBackend("cache", expire_after=CACHE_EXPIRY),
        ) as session:
            request = await session.get(f"{base_url}{word}")
            request.raise_for_status()
            raw = BeautifulSoup(await request.text(), features="html.parser")
        first_result = raw.find(attrs={"class": "vbox"})
        if not first_result:
            return

        word_api = {}
        word_api["word"] = self.parse_word(first_result)
        word_api["reading"] = self.parse_reading(first_result)
        word_api["meanings"] = self.parse_meanings(first_result)
        word_api["kanji"] = self.parse_kanji(first_result)
        word_api["pitch"] = self.extract_pitch_accent(
            first_result.find(class_="subsection-pitch-accent")
        )
        word_api["alt_forms"] = self.parse_alt_forms(first_result)
        word_api["top"], word_api["other_frequencies"] = self.parse_frequencies(
            first_result
        )
        word_api["types"] = self.parse_word_type(first_result)
        return word_api

    def parse_word(self, first_result) -> str:
        ps_div = first_result.find(attrs={"class": "primary-spelling"})
        return ps_div.text

    def parse_reading(self, first_result) -> str:
        ps_div = first_result.find(attrs={"class": "primary-spelling"})
        kana = []
        for ruby in ps_div.find_all("ruby"):
            children = list(ruby.children)
            i = 0
            while i < len(children):
                child = children[i]
                if child.name == "rt":
                    i += 1
                    continue
                base_text = child.string or ""
                rt = ""
                if i + 1 < len(children) and children[i + 1].name == "rt":
                    rt = children[i + 1].string or ""
                if rt.strip():
                    kana.append(rt.strip())
                else:
                    kana.append(base_text)
                i += 2
        return "".join(kana)

    def parse_meanings(self, first_result) -> list:
        meaning_div = first_result.find(class_="subsection-meanings")
        meaning_entries = meaning_div.find_all(class_="description")
        return [m.text for m in meaning_entries]

    def parse_kanji(self, first_result) -> list:
        kanji_div = first_result.find(class_="subsection-composed-of-kanji")
        kanjis = []
        if kanji_div:
            kanji_entries = kanji_div.find(class_="subsection")
            for item in kanji_entries.find_all("div", recursive=False):
                kanji = item.find("div", class_="spelling").a.text
                meaning = item.find("div", class_="description").text
                kanjis.append(f"{kanji} {meaning}")
        return kanjis

    def parse_alt_forms(self, first_result) -> list:
        alt_forms = []
        alt = first_result.find("div", class_="subsection-other-spellings")
        if alt:
            alt_spellings = alt.find_all("div", class_="alt-spelling")
            for alt in alt_spellings:
                a_tag = alt.find("a", class_="plain")
                if a_tag:
                    ruby_tags = a_tag.find_all("ruby")
                    kanji = (
                        "".join(ruby.get_text(strip=True) for ruby in ruby_tags)
                        if ruby_tags
                        else a_tag.get_text(strip=True)
                    )
                    property = alt.find("div", class_="property-text")
                    percentage = (
                        int(property.get_text(strip=True).rstrip("%"))
                        if property
                        else 0
                    )
                    alt_forms.append(f"{kanji} ({percentage}%)")
        return alt_forms

    def parse_frequencies(self, first_result) -> tuple:
        top = 0
        other_freqs = []
        top_tag = first_result.find("div", class_="tag tooltip")
        if top_tag:
            top_text = top_tag.get_text(strip=True)
            match = re.search(r"Top\s+(\d+)", top_text)
            if match:
                top = int(match.group(1))
            data_tooltip = top_tag.get("data-tooltip", "")
            freq_matches = re.findall(r"([\w\s\-‑]+):\s*(\d+)", data_tooltip)
            for category, number in freq_matches:
                category = category.strip().replace("\xa0", " ")
                number = int(number.replace(",", ""))
                other_freqs.append(f"{category}: Top {number}")
        return top, other_freqs

    def parse_word_type(self, first_result) -> list:
        pos = first_result.find_all("div", class_="part-of-speech")
        types = []
        for part in pos:
            types.append(", ".join(div.text for div in part.find_all("div")))
        return types

    async def generate_example_sentence(
        self, word: str, meaning: Optional[list] = [""]
    ) -> dict:
        """Generate a sentence example with Gemini."""
        sentences = {"jp": "", "en": ""}
        if self.gembot:
            request = await self.gembot.model.generate_content_async(
                "Send simple jp sentence and en translation "
                f"that includes the word {word} ({meaning[0]})."
                "Don't send anything else. "
                "Put the whole word in bold in the correct language.",
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=SentenceLanguage,
                    candidate_count=1,
                    temperature=1,
                ),
            )
            sentences = json.loads(request.candidates[0].content.parts[0].text)
        return sentences


word_api = JpdbWordApi()
