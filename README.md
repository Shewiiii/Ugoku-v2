<div align="center">
  <a href="https://twitter.com/shironappa_">
      <img src="https://i.imgur.com/gj3SRcY.png" alt="Illustration by Shironappa">
  </a>
  <p>Art by Shironappa</p>
  <h1>Ugoku-v2 Discord Bot</h1>
</div>

**A work in progress rework of [Ugoku !](https://github.com/Shewiiii/Ugoku-bot)**, completely refactored and lightweight~  
Thank you again [Chinono](https://github.com/ChinHongTan) to help me on that project, much love <3

<h2>Features/To do</h2>

- [X] Ping.
- [X] Echo messages (make the bot say any message).
- [X] Download stickers from LINE.
- [X] Download songs, albums or playlists from Spotify. (WIP)
- [X] Play songs in a voice channel.
  - [X] Skip, Show queue, Autodetect and add songs/albums, or playlists.
  - [X] Loop song, Loop queue, pause, resume...
  - [X] Amazing audio quality: bypass the channel's audio bitrate.
  - [X] Stream songs from Spotify.
  - [X] Stream videos from Youtube.
  - [X] Stream audio works (音声作品) in a voice channel (because why not).
  - [X] Play songs from a URL (custom source).
  - [X] Cache audio from custom sources.
  - [X] Embed info messages with metadata.
  - [X] Show the lyrics of a song using musixmatch API.
  - [ ] (outdated) Control the bot using [this amazing UI](https://github.com/ChinHongTan/Ugoku-frontend) !


- [X] Chat using Gemini 1.5 Pro. (WIP)
  - [ ] Optimize token usage.
  - [X] Make its messages more human-like.
  - [X] Have a permanent memory!
- [ ] And maybe more in the future~

<h2>Known bugs to fix</h2>

- Queue not showing when too many characters in the queue/loop section. (mostly the case with onsei)
  ("In data.embeds.0.fields.1.value: Must be 1024 or fewer in length.").

<h2>Audio benchmarks</h2>

> [!NOTE]
> Ugoku-v2 is only using Spotify as a music streaming service source, so the best audio chain (besides custom sources) is OGG 320kbps -> Opus 510kpbs. I'm planning to implement Deezer as a streaming source to the bot, in order to get the best possible audio quality out of any discord Bot.

> Benchmark reference:
> - Reference track: Ayiko - Tsundere Love
> - Reference source: Deezer, FLAC  
> - Time: ~0-30 seconds  
> - Amplitude normalization: -10dBFS
> - Recorded with: VB-Audio Hi-Fi Cable (Virtual cable)
> - Normalized with: Audacity
> - Downsampled with: Audacity
> - Commands:
>   -  Ugoku: ```/play https://open.spotify.com/intl-fr/track/0d6cQvE2RqPS9Mgl3Lcfbo```
>   -  Jockie: ```m!play https://open.spotify.com/intl-fr/track/0d6cQvE2RqPS9Mgl3Lcfbo```
> - Audio quality:
>   -  Ugoku: Very High
>   -  Jockie: No Patreon subscription to Jockie


<h2>Results:</h2>

<div align="center">
  <h3>Delta of spectra, Ugoku: (Lower absolute value is better)</h3>
  <img src="benchmarks/measures/delta_spectra_ugoku.jpg" alt="delta spectra ugoku"/>
  <h3>Delta of spectra, Jockie:</h3>
  <img src="benchmarks/measures/delta_spectra_jockie.jpg" alt="delta spectra jockie"/>
  <h3>Delta waveform, Ugoku: (Lower is better)</h3>
  <img src="benchmarks/measures/delta_waveform_ugoku.jpg" alt="delta waveform ugoku"/>
  <h3>Delta waveform, Jockie:</h3>
  <img src="benchmarks/measures/delta_waveform_jockie.jpg" alt="delta waveform jockie"/>
  <h3>Spectrogram, Reference:</h3>
  <img src="benchmarks/measures/spectrogram_reference.jpg" alt="spectrogram reference"/>
  <h3>Spectrogram, Ugoku:</h3>
  <img src="benchmarks/measures/spectrogram_ugoku.jpg" alt="spectrogram ugoku"/>
  <h3>Spectrogram, Jockie:</h3>
  <img src="benchmarks/measures/spectrogram_jockie.jpg" alt="spectrogram jockie"/>
</div>
