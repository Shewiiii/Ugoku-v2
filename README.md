<div align="center">
  <a href="https://twitter.com/shironappa_">
      <img src="https://i.imgur.com/gj3SRcY.png&" alt="Illustration by Shironappa">
  </a>
  <p>Art by Shironappa</p>
  <h1>Ugoku-v2 Discord Bot</h1>
</div>
<b>A work in progress rework of <a href='https://github.com/Shewiiii/Ugoku-bot'>Ugoku !</a>, completely refactored and lightweight~</b>   
<p>Thank you again <a href='https://github.com/ChinHongTan'>Chinono</a> to help me on that project, much love <3</p>

<h2>Features/To do</h2>

- [X] Ping.
- [X] Echo messages (make the bot say any message).
- [X] Download stickers from LINE.
- [X] Download songs, albums or playlists from Spotify. (WIP)
- [X] Play songs in a voice channel.
  - [X] Skip, Show queue, Autodetect and add songs/albums, or playlists.
  - [X] Loop song, Loop queue, pause, resume...
  - [X] Bypass the channel's audio bitrate.
  - [X] Stream songs from Spotify.
  - [X] Stream videos from Youtube.
  - [X] Stream audio works (音声作品) in a voice channel (because why not).
  - [X] Play songs from a URL (custom source).
  - [X] Cache audio from custom sources.
  - [X] Embed info messages with metadata.
  - [x] Show the lyrics of a song using.
  - [X] Control the bot using [this amazing UI](https://github.com/ChinHongTan/Ugoku-frontend) !

> [!NOTE]
> Ugoku-v2 is only using Spotify as a streaming service source, so the best audio chain (besides custom sources) is OGG 320kbps -> Opus 510kpbs. However the audio quality is extremely similar to FLAC -> Opus 510kpbs.

- [X] Chat using Gemini 1.5 Pro. (WIP)
  - [ ] Optimize token usage.
  - [X] Make its messages more human-like.
  - [X] Have a permanent memory!
- [ ] And maybe more in the future~

<h2>Known bugs to fix</h2>

- Queue not showing when too many characters in the queue/loop section. (mostly the case with onsei)
  ("In data.embeds.0.fields.1.value: Must be 1024 or fewer in length.").
