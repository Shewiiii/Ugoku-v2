USER_AGENT_HEADER = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) " \
                    "Chrome/79.0.3945.130 Safari/537.36"
# Headers from https://github.com/kmille/deezer-downloader/blob/master/deezer_downloader/deezer.py !
HEADERS = {
    'Pragma': 'no-cache',
    'Origin': 'https://www.deezer.com',
    'Accept-Language': 'fr',
    'User-Agent': USER_AGENT_HEADER,
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'Accept': '*/*',
    'Cache-Control': 'no-cache',
    'X-Requested-With': 'XMLHttpRequest',
    'Connection': 'keep-alive',
    'Referer': 'https://www.deezer.com/login',
    'DNT': '1',
}
BLOWFISH_SECRET = "g4el58wc0zvf9na1"
CHUNK_SIZE = 6144
EXTENSION = {
    'FLAC': 'flac',
    'MP3_320': 'mp3',
    'MP3_128': 'mp3'
}
