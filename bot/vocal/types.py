from typing import List, Optional, Callable, Awaitable, Any, Literal, Tuple, NewType, Dict
from typing_extensions import TypedDict
import discord


class BaseTrackInfo(TypedDict):
    """
    Represents base information about a music track without callable fields.

    Atteributes:
        display_name: The name to display for this track.
        title: The title of the track.
        artist: The artist of the track.
        album: The album the track belongs to, if any.
        cover: URL to the cover art, if available.
        duration: Duration of the track in milliseconds, if known.
        url: URL to the track.
        id: Unique identifier for the track.
    """
    display_name: str
    title: str
    artist: str
    album: Optional[str]
    cover: Optional[str]
    duration: Optional[int]
    url: str
    id: str


class TrackInfo(BaseTrackInfo, total=False):
    """
    Represents information about a music track.

    Attributes:
        source (Callable[[], Awaitable[Any]]): Async function to get the track's audio source.
        embed (Callable[[], Awaitable[discord.Embed]]): Async function to generate an embed for this track.
    """
    source: Callable[[], Awaitable[Any]]
    embed: Callable[[], Awaitable[discord.Embed]]

class SimplifiedTrackInfo(TypedDict):
    title: str
    artist: Optional[str]
    album: Optional[str]
    cover: Optional[str]
    duration: Optional[int]
    url: str


class QueueItem(TypedDict):
    """
    Represents an item in the music queue.

    Attributes:
        track_info (TrackInfo): Information about the track.
        source (Literal['Spotify', 'Custom', 'Onsei']): The source of the track ('Spotify', 'Custom', 'Onsei').
    """
    track_info: TrackInfo
    source: Literal['Spotify', 'Custom', 'Onsei']

class CoverData(TypedDict, total=False):
    """
    Represents cover art data for a track.

    Attributes:
        url (Optional[str]): URL to the cover art image, if available.
        cover_hash (str): Hash of the cover art, if available.
        dominant_rgb (Tuple[int, int, int]): The dominant RGB color of the cover art.
    """
    url: Optional[str]
    cover_hash: str
    dominant_rgb: Optional[Tuple[int, int, int]]


class SpotifyID(TypedDict):
    """
    Represents a Spotify ID and its type.

    Attributes:
        id (str): The Spotify ID.
        type (Literal['track', 'album', 'playlist', 'artist']): The type of the Spotify item ('track', 'album', 'playlist', 'artist').
    """
    id: str
    type: Literal['track', 'album', 'playlist', 'artist']

class CurrentSongInfo(TrackInfo, total=False):
    """
    Represents information about the currently playing song, extending TrackInfo.

    Attributes:
        playback_start_time (str): The time when playback of this song started.
    """
    playback_start_time: str

class ActiveGuildInfo(TypedDict):
    """
    Represents information about an active guild (server) in the music bot.

    Attributes:
        id (str): The unique identifier of the guild.
        name (str): The name of the guild.
        icon (Optional[str]): URL to the guild's icon, if available.
        currentSong (Optional[CurrentSongInfo]): Information about the currently playing song, if any.
        queue (List[SimplifiedTrackInfo]): List of tracks in the queue.
        history (List[TrackInfo]): List of recently played tracks.
    """
    id: str
    name: str
    icon: Optional[str]
    currentSong: Optional['CurrentSongInfo']
    queue: List[SimplifiedTrackInfo]
    history: List[TrackInfo]

LoopMode = Literal['noLoop', 'loopAll', 'loopOne']

# =================== Onsei types ===================

TrackTitle = NewType('TrackTitle', str)
MediaStreamUrl = NewType('MediaStreamUrl', str)

TrackUrlMapping = Dict[TrackTitle, MediaStreamUrl]

class WorkInfo(TypedDict):
    id: int
    source_id: str
    source_type: Literal['DLSITE']

class AudioFileInfo(TypedDict):
    type: Literal['audio']
    hash: str
    title: str
    work: WorkInfo
    workTitle: str
    mediaStreamUrl: str
    mediaDownloadUrl: str
    streamLowQualityUrl: Optional[str]
    duration: float
    size: int

class ImageFileInfo(TypedDict):
    type: Literal['image']
    hash: str
    title: str
    work: WorkInfo
    workTitle: str
    mediaStreamUrl: str
    mediaDownloadUrl: str
    size: int

class FolderInfo(TypedDict):
    type: Literal['folder']
    title: str
    children: List['OnseiAPIResponse']

class OnseiAPIResponse(TypedDict):
    """
    Represents the response from the Onsei API.

    Attributes:
        type (Literal['folder', 'audio', 'image']): The type of the item.
        title (str): The title of the item.
        children (Optional[List[OnseiAPIResponse]]): List of child items for folders.
        hash (Optional[str]): Unique hash for audio and image files.
        work (Optional[WorkInfo]): Information about the work the file belongs to.
        workTitle (Optional[str]): Title of the work.
        mediaStreamUrl (Optional[str]): URL for streaming the media.
        mediaDownloadUrl (Optional[str]): URL for downloading the media.
        streamLowQualityUrl (Optional[str]): URL for streaming low quality version (audio only).
        duration (Optional[float]): Duration of the audio file in seconds.
        size (Optional[int]): Size of the file in bytes.
        error (Optional[str]): Error message, if any.
    """
    type: Literal['folder', 'audio', 'image']
    title: str
    children: Optional[List['OnseiAPIResponse']]
    hash: Optional[str]
    work: Optional[WorkInfo]
    workTitle: Optional[str]
    mediaStreamUrl: Optional[str]
    mediaDownloadUrl: Optional[str]
    streamLowQualityUrl: Optional[str]
    duration: Optional[float]
    size: Optional[int]
    error: Optional[str]

# =================== Spotify types ===================
class SpotifyAlbum(TypedDict):
    """
    Represents a simplified Spotify album.
    """
    name: str
    cover: Optional[str]
    url: str

# =================== Code wall zone ===================
# Types below are for future use, I'm tired of logging them out every time I need them
class SpotifyAlbumAPI(TypedDict):
    """
    Represents a Spotify album directly from the Spotify API.

    Attributes:
        album_type (str): The type of the album (e.g., 'album', 'single', 'compilation').
        total_tracks (int): The total number of tracks in the album.
        available_markets (List[str]): A list of country codes where the album is available.
        external_urls (dict): External URLs for this album, including Spotify URL.
        href (str): A link to the Web API endpoint providing full details of the album.
        id (str): The Spotify ID for the album.
        images (List[dict]): A list of album cover art images in various sizes.
        name (str): The name of the album.
        release_date (str): The date the album was first released.
        release_date_precision (str): The precision with which release_date is known.
        type (str): The object type (e.g., 'album').
        uri (str): The Spotify URI for the album.
        artists (List[dict]): The artists of the album.
        tracks (dict): Information about the tracks of the album.
        copyrights (List[dict]): The copyright statements of the album.
        external_ids (dict): Known external IDs for the album.
        genres (List[str]): A list of genres the album is associated with.
        label (str): The label associated with the album.
        popularity (int): The popularity of the album, represented as an integer.
    """
    album_type: str
    total_tracks: int
    available_markets: List[str]
    external_urls: dict
    href: str
    id: str
    images: List[dict]
    name: str
    release_date: str
    release_date_precision: str
    type: str
    uri: str
    artists: List[dict]
    tracks: dict
    copyrights: List[dict]
    external_ids: dict
    genres: List[str]
    label: str
    popularity: int


class SpotifyArtistAPI(TypedDict):
    """
    Represents a Spotify artist directly from the Spotify API.

    Attributes:
        tracks (List[dict]): A list of track objects associated with the artist. Each track contains:
            album (dict): Information about the album the track belongs to.
            artists (List[dict]): List of artists involved in the track.
            available_markets (List[str]): List of markets where the track is available.
            disc_number (int): The disc number (usually 1 unless the album consists of more than one disc).
            duration_ms (int): The track length in milliseconds.
            explicit (bool): Whether or not the track has explicit lyrics.
            external_ids (dict): Known external IDs for the track.
            external_urls (dict): Known external URLs for this track.
            href (str): A link to the Web API endpoint providing full details of the track.
            id (str): The Spotify ID for the track.
            is_local (bool): Whether this track is a local file or not.
            is_playable (bool): Whether the track is playable in the given market.
            name (str): The name of the track.
            popularity (int): The popularity of the track. The value will be between 0 and 100, with 100 being the most popular.
            preview_url (str): A link to a 30 second preview (MP3 format) of the track.
            track_number (int): The number of the track on its album.
            type (str): The object type (always "track").
            uri (str): The Spotify URI for the track.

    Note:
        The structure above represents the top tracks of an artist. The full artist object would typically
        include more information about the artist themselves, such as name, genres, popularity, etc.
    """
    tracks: List[dict]


class SpotifyTrackAPI(TypedDict):
    """
    Represents a Spotify track directly from the Spotify API.

    Attributes:
        album (dict): Information about the album the track appears on.
        artists (List[dict]): The artists who performed the track.
        available_markets (List[str]): A list of country codes where the track is available.
        disc_number (int): The disc number (usually 1 unless the album consists of more than one disc).
        duration_ms (int): The track length in milliseconds.
        explicit (bool): Whether or not the track has explicit lyrics.
        external_ids (dict): Known external IDs for the track.
        external_urls (dict): Known external URLs for this track.
        href (str): A link to the Web API endpoint providing full details of the track.
        id (str): The Spotify ID for the track.
        is_local (bool): Whether or not the track is from a local file.
        name (str): The name of the track.
        popularity (int): The popularity of the track. The value will be between 0 and 100, with 100 being the most popular.
        preview_url (str): A link to a 30 second preview (MP3 format) of the track.
        track_number (int): The number of the track on its album.
        type (str): The object type (always "track").
        uri (str): The Spotify URI for the track.
    """
    album: dict
    artists: List[dict]
    available_markets: List[str]
    disc_number: int
    duration_ms: int
    explicit: bool
    external_ids: dict
    external_urls: dict
    href: str
    id: str
    is_local: bool
    name: str
    popularity: int
    preview_url: str
    track_number: int
    type: str
    uri: str


class SpotifyPlaylistAPI(TypedDict):
    """
    Represents a Spotify playlist directly from the Spotify API.

    Attributes:
        href (str): A link to the Web API endpoint providing full details of the playlist.
        items (List[dict]): An array of playlist track objects.
        limit (int): The maximum number of items in the response (as set in the query or by default).
        next (Optional[str]): URL to the next page of items (null if none).
        offset (int): The offset of the items returned (as set in the query or by default).
        previous (Optional[str]): URL to the previous page of items (null if none).
        total (int): The total number of items available to return.

    Each item in the 'items' list contains:
        added_at (str): The date and time the track was added to the playlist.
        added_by (dict): Information about the user who added the track.
        is_local (bool): Whether this track is a local file or not.
        primary_color (Optional[str]): The primary color of the track's album art.
        track (dict): Full track information including:
            preview_url (Optional[str]): A URL to a 30 second preview (MP3 format) of the track.
            available_markets (List[str]): The markets in which this track can be played.
            explicit (bool): Whether or not the track has explicit lyrics.
            type (str): The object type, always "track".
            episode (bool): Whether the track is an episode of a podcast.
            track (bool): Whether this object is a track.
            album (dict): Information about the album the track appears on.
            artists (List[dict]): The artists who performed the track.
            disc_number (int): The disc number (usually 1 unless the album consists of more than one disc).
            duration_ms (int): The track length in milliseconds.
            external_ids (dict): Known external IDs for the track.
            external_urls (dict): Known external URLs for this track.
            href (str): A link to the Web API endpoint providing full details of the track.
            id (str): The Spotify ID for the track.
            name (str): The name of the track.
            popularity (int): The popularity of the track. The value will be between 0 and 100, with 100 being the most popular.
            uri (str): The Spotify URI for the track.
            is_local (bool): Whether this track is a local file or not.
        video_thumbnail (dict): Information about the video thumbnail, if any.
    """
    href: str
    items: List[dict]
    limit: int
    next: Optional[str]
    offset: int
    previous: Optional[str]
    total: int
