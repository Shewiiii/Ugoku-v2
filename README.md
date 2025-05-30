<div align="center">
  <a href="https://www.pixiv.net/en/artworks/130821036">
      <img src="https://i.imgur.com/WvyRtdu.png" alt="Illustration by Arren">
  </a>
  <p>Art by Arren !</p>
  <h1>Ugoku-v2 Discord Bot</h1>
</div>

**A work in progress rework of [Ugoku !](https://github.com/Shewiiii/Ugoku-bot)**, completely refactored and feature complete !  
Learn more about the bot here: https://ugoku.moe/.

<h2>Features/To do</h2>

- [x] Ping.
- [x] Echo messages (make the bot say any message).
- [x] Download stickers from LINE.
- [x] Download songs from Spotify.
- [x] Download lossless songs from Deezer.
- [x] Play songs in a voice channel.
  - [x] Skip, Show queue, Autodetect and add songs/albums, or playlists.
  - [x] Loop song, Loop queue, pause, resume...
  - [x] Amazing audio quality: bypass the channel's audio bitrate.
  - [x] Stream songs from Spotify, Deezer or Soundcloud*.
  - [x] Inject lossless streams to Spotify songs (when available on Deezer).
  - [x] Stream videos from Youtube.
  - [x] Stream audio works (音声作品) in a voice channel.
  - [x] Play songs from a URL (custom source).
  - [x] Apply audio effects (bass boost, reverb, etc), with high quality [Raum](https://www.native-instruments.com/en/products/komplete/effects/raum/) effects built-in !
  - [x] Cache audio from custom sources.
  - [x] Embed info messages with metadata.
  - [x] Show the lyrics of a song using the Musixmatch API
  - [ ] ~~(outdated) Control the bot using [this amazing UI](https://github.com/ChinHongTan/Ugoku-frontend) !~~
- [x] Chat using Gemini 2.0 flash. (WIP)
  - [ ] Optimize token usage.
  - [x] Make its messages more human-like.
  - [x] Have a permanent memory!
- [x] Review jpdb cards in Discord (sentences generated with Gemini).
- [x] Search any word in Japanese.
- [x] Get a random image from Danbooru (SFW only).
- [ ] And maybe more in the future~  

*Song search is not available with Soundcloud, URL only. 

<h2>Public playground bot</h2>

Chatbot features are disabled, but you can still play with the bot !
[Invite link](https://discord.com/oauth2/authorize?client_id=1260656795974897695)

<h2>Known bugs to fix</h2>

- Example sentences not always well chosen when reviewing jpdb cards (cause: Gemini's randomness in its response).
- The song in vc may stop randomly with Spotify (cause: Librespot session's connection closing).
- Audio may lag at the beginning of a song, when changing the audio effect or when seeking forward (causes: Discord client, slow Deezer/Spotify chunked input stream reading).
- /seek may seek to the wrong location (cause: bad seek table provided by Deezer)

<h2>Requirements</h2>

- Python 3.12.x / 3.13.x
- A Discord bot token (get one [here](https://discord.com/developers/applications))
- FFmpeg

Music bot:

- A Spotify app (get one [here](https://developer.spotify.com/)).
- A Deezer Premium or Spotify Premium account (Youtube is supported, but the bot is not optimized for it).
- (Optional) An Imgur API key (get one [here](https://imgur.com/account/settings/apps)), to display the cover art for songs from custom sources.
- (Optional) A Youtube API key (get one [here](https://console.cloud.google.com/)), to enable Youtube playlist URL support.

Chatbot:

- A Gemini API key (get one [here](https://aistudio.google.com))
- (Optional) A Pinecone API key for long-term memory

<h2>Quick setup guide</h2>

- Install FFmpeg. You can follow [this guide](https://www.geeksforgeeks.org/how-to-install-ffmpeg-on-windows/) if you are on a Windows machine.
- Copy the repo.
- Create a virtual environment.

```bash
python -m venv venv
```

OR

```bash
python3 -m venv venv
```

- Enable the venv.

Windows:

```bash
./venv/Scripts/activate.bat
```

Linux:

```bash
source venv/bin/activate
```

- Install the dependencies.

```bash
pip install -r requirements.txt
```

- [Create a bot and add it to a Discord server](https://guide.pycord.dev/getting-started/creating-your-first-bot), or add it to your apps. You can follow the first 3 sections of the guide.
- Create an .env file in the root directory.
- Set the environment variables for the services you want to use, based on the template.
- Restart the IDE (to update the env variables).
- On linux machines, you may want to switch the protobuf implementation to Python if the .env variable has been ignored by doing so:
```bash
echo 'export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python' >> ~/.bashrc
source ~/.bashrc
```
You can now restart your instance.
- Configure and activate the features in the config.py file.
- Run `main.py`.
- If Spotify is enabled, log in to Librespot from your Spotify client (it should appear in the device list)\*.
- Done !

> [!TIP]
> \*This action will create a `credentials.json` file in the root folder. If you are having trouble creating it on a remote machine, try creating it on your local machine and exporting it.

<h2>Special Thanks</h2>

- Chinono 智乃乃, for helping me with this project and inspiring me
- Neutrixia, Hibiki and Hanabi for providing improvement ideas for the bot and extensively testing it!
- Nothes, Sougata and PIKASONIC for allowing me to use your public servers as a platform for Ugoku ❤️
- Everyone actively using my bot!

<h2>Random screenshots</h2>

<div align="center">
  <img src="img/now_playing.png" alt="now playing embed"/>
  <p>Playing a song</p>
  <img src="img/song_queue.jpg" alt="song queue"/>
  <p>Songs in queue</p>
  <img src="img/spotify_download.jpg" alt="spotify song download"/>
  <p>Spotify song download</p>
  <img src="img/lyrics.jpg" alt="lyrics"/>
  <p>Lyrics</p>
  <img src="img/youtube_summary.jpg" alt="lyrics"/>
  <p>Youtube & text summary</p>
  <img src="img/help_command.jpg" alt="help command"/>
  <p>Help command</p>
  <img src="img/danbooru.jpg" alt="danbooru"/>
  <p>Danbooru</p>
  <img src="img/jpdb_review.jpg" alt="review of a jpdb card"/>
  <p>Review of a jpdb card</p>
  <img src="img/jpdb_dict.jpg" alt="japanese word lookup"/>
  <p>Japanese word lookup</p>
</div>
