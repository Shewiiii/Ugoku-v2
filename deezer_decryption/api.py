import asyncio
from deezer_decryption.constants import HEADERS
import httpx
import logging
import os
import requests
from spotipy.exceptions import SpotifyException
from spotipy import Spotify
from typing import Optional, Union, Literal

DEEZER_ARL = os.getenv("DEEZER_ARL")

# Simplified and adapted from https://gitlab.com/RemixDev/deezer-py !


class Deezer:
    def __init__(self):
        self.headers = HEADERS
        self.session = httpx.AsyncClient(cookies={"arl": DEEZER_ARL}, http2=True)
        self.base_url = "http://www.deezer.com/ajax/gw-light.php"
        self.params = {}
        self.api_token = None
        self.user_data = None

    async def setup(self) -> None:
        await self.set_api_token()
        logging.info("Deezer API Token set")
        await self.set_user_data()
        logging.info("Deezer User data set")

    async def set_api_token(self) -> None:
        p = {"api_version": "1.0", "api_token": "null", "method": "deezer.getUserData"}
        response = await self.session.post(
            self.base_url, params=p, headers=self.headers
        )
        self.api_token = response.json()["results"]["checkForm"]

    async def set_user_data(self) -> None:
        self.user_data = await self.gw_api_call("deezer.getUserData")

    async def native_api_call(self, method: str, args: Optional[dict] = None) -> dict:
        if args is None:
            args = {}
        request = await self.session.get(
            "https://api.deezer.com/" + method,
            params=args,
            headers=self.headers,
        )
        request.raise_for_status()
        response = request.json()
        return response

    async def gw_api_call(
        self, method: str, args: Optional[dict] = None, params: Optional[dict] = None
    ) -> dict:
        if not self.api_token:
            await self.setup()
        if params is None:
            params = {}
        if args is None:
            args = {}
        p = {"api_version": "1.0", "api_token": self.api_token, "method": method}
        p.update(params)
        response = await self.session.post(
            self.base_url, params=p, headers=self.headers, json=args
        )
        return response.json()["results"]

    async def get_native_track(self, track_id: Union[str, int]) -> dict:
        return await self.native_api_call(f"track/{str(track_id)}")

    async def get_track(self, sng_id: Union[int, str]) -> dict:
        return await self.gw_api_call("song.getData", {"SNG_ID": sng_id})

    async def get_tracks(self, track_ids: list[Union[int, str]]) -> dict:
        return (await self.gw_api_call("song.getListData", {"SNG_IDS": track_ids}))[
            "data"
        ]

    def can_stream_lossless(self) -> bool:
        options = self.user_data["USER"]["OPTIONS"]
        return options["web_lossless"] or options["mobile_lossless"]

    async def search(
        self,
        query,
        index=0,
        limit=10,
        suggest=True,
        artist_suggest=True,
        top_tracks=True,
    ) -> dict:
        return await self.gw_api_call(
            "deezer.pageSearch",
            {
                "query": query,
                "start": index,
                "nb": limit,
                "suggest": suggest,
                "artist_suggest": artist_suggest,
                "top_tracks": top_tracks,
            },
        )

    async def get_stream_urls(
        self,
        track_tokens: list,
        tracks_format: Literal["MP3_128", "MP3_320", "FLAC"] = "FLAC",
    ) -> list[str]:
        if not self.user_data:
            await self.setup()
        license_token = self.user_data["USER"]["OPTIONS"]["license_token"]
        if not license_token:
            return [None] * len(track_tokens)
        # Cannot stream lossless => Free account (with 128kbps as the max mp3 bitrate)
        if not self.can_stream_lossless() and tracks_format != "MP3_128":
            raise ValueError

        request = await self.session.post(
            "https://media.deezer.com/v1/get_url",
            json={
                "license_token": license_token,
                "media": [
                    {
                        "type": "FULL",
                        "formats": [
                            {"cipher": "BF_CBC_STRIPE", "format": tracks_format}
                        ],
                    }
                ],
                "track_tokens": track_tokens,
            },
            headers=self.headers,
        )
        request.raise_for_status()
        response = request.json()
        result = []
        for data in response["data"]:
            if "media" in data and len(data["media"]):
                result.append(data["media"][0]["sources"][0]["url"])
            else:
                result.append(None)
        return result

    def get_stream_url_sync(
        self,
        track_token: str,
        tracks_format: Literal["MP3_128", "MP3_320", "FLAC"] = "FLAC",
    ) -> Optional[str]:
        if not self.user_data:
            self.setup()
        license_token = self.user_data["USER"]["OPTIONS"]["license_token"]
        if not license_token:
            return
        # Cannot stream lossless => Free account (with 128kbps as the max mp3 bitrate)
        if not self.can_stream_lossless() and tracks_format != "MP3_128":
            raise ValueError

        with requests.post(
            "https://media.deezer.com/v1/get_url",
            json={
                "license_token": license_token,
                "media": [
                    {
                        "type": "FULL",
                        "formats": [
                            {"cipher": "BF_CBC_STRIPE", "format": tracks_format}
                        ],
                    }
                ],
                "track_tokens": [track_token],
            },
            headers=self.headers,
        ) as request:
            request.raise_for_status()
            response = request.json()
            result = response["data"][0]

        if "media" in result and len(result["media"]):
            return result["media"][0]["sources"][0]["url"]

    async def parse_spotify_track(
        self, spotify_track_id_or_url: str, sp: Spotify
    ) -> Optional[dict]:
        try:
            track_api = await asyncio.to_thread(sp.track, spotify_track_id_or_url)
            isrc = track_api["external_ids"]["isrc"]
            native_track_api = await self.get_native_track(f"isrc:{isrc}")
            return native_track_api if not native_track_api.get("error") else None
        except SpotifyException:
            return


if __name__ == "__main__":
    api = Deezer()
