<div align="center">
  <a href="https://twitter.com/shironappa_">
      <img src="https://i.imgur.com/gj3SRcY.png&" alt="Illustration by Shironappa">
  </a>
  <p>Art by Shironappa</p>
  <h1>Ugoku-v2 Discord Bot</h1>
</div>
<b>Chinono's branch of Ugoku, forked from Shewi's <a href='https://github.com/Shewiiii/Ugoku-v2'>Ugoku-v2 !</a>. I forked this mainly to try and develop a webpage dashboard <a href='https://github.com/ChinHongTan/Ugoku-frontend'>here</a>, which is still work in progress.</b>
<h2>Features/To do</h2>
<b>Unticked boxes are work in progress.</b>

- [X] Ping.
- [X] Echo messages (make the bot say any message).
- [X] Download stickers from LINE.
- [ ] Download songs, albums or playlists from Spotify.
- [X] Play songs in a voice channel.
  - [X] Skip, Show queue, Autodetect and add songs/albums, or playlists.
  - [X] Loop song, Loop queue, pause, resume...
  - [X] Bypass the channel's audio bitrate.
  - [X] Stream songs from Spotify.
  - [X] Play songs from a URL (custom source).
  - [X] Cache audio from custom sources.
  - [ ] Embed info messages with metadata (partially done).

> [!NOTE]
> Ugoku-v2 is only using Spotify or Youtube as streaming service sources, so the best audio chain (besides custom sources) is OGG 320kbps -> Opus 510kpbs. However the audio quality is extremely similar to FLAC -> Opus 510kpbs

- [X] Stream audio works (音声作品) in a voice channel (because why not).
- [ ] Chat using GPT-4o Mini.
- [ ] Log users out no matter the token? To avoid user stuck and cannot log out.
- [ ] Implement a refresh token logic
- [ ] Clean up spotipy.py
- [ ] And maybe more in the future~

<h2>Known bugs to fix</h2>

- Queue not showing when too many characters in the queue/loop section.
  ("In data.embeds.0.fields.1.value: Must be 1024 or fewer in length.").
- Can't play audio works without MP3 Files in it.
