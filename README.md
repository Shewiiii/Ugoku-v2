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
- [X] Download songs from Spotify.
- [ ] Download lossless songs from Deezer. (WIP)
- [X] Play songs in a voice channel.
  - [X] Skip, Show queue, Autodetect and add songs/albums, or playlists.
  - [X] Loop song, Loop queue, pause, resume...
  - [X] Amazing audio quality: bypass the channel's audio bitrate.
  - [X] Stream songs from Spotify.
  - [X] Inject lossless streams to Spotify songs (when available on Deezer).
  - [X] Stream videos from Youtube.
  - [X] Stream audio works (音声作品) in a voice channel (because why not).
  - [X] Play songs from a URL (custom source).
  - [X] Cache audio from custom sources.
  - [X] Embed info messages with metadata.
  - [X] Show the lyrics of a song using musixmatch API.
  - [ ] ~~(outdated) Control the bot using [this amazing UI](https://github.com/ChinHongTan/Ugoku-frontend) !~~


- [X] Chat using Gemini 2.0 flash. (WIP)
  - [ ] Optimize token usage.
  - [X] Make its messages more human-like.
  - [X] Have a permanent memory!
- [ ] And maybe more in the future~

- [X] Review jpdb cards in Discord (sentences generated with Gemini)
- [X] Search any word in Japanese

<h2>Known bugs to fix</h2>

- Example sentences not always well chosen (Gemini, rare but still)
- The song in vc may stop randomly
- Audio is slowing down at the beginning of a song

<h2>Plublic playground bot</h2>

Chatbot and Spotify streaming features are disabled, but you can still play with the bot !
 [Invite link](https://discord.com/oauth2/authorize?client_id=1260656795974897695)

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
  <img src="img/chat.jpg" alt="chat message"/>
  <p>Random message w</p>
</div>

<h2>Audio benchmarks</h2>

> [!NOTE]
> Deezer has finally been integrated into Ugoku! Lossless audio content will now be injected in Spotify tracks before playing (when available). Ugoku now offers the best audio quality possible for a Discord bot, nearly indistinguishable from true lossless audio...except for occasional lags.

> Benchmark reference:
> - Reference track: Ayiko - Tsundere Love
> - Reference source: Deezer, FLAC  
> - Comparison softwate: Deltawave
> - Time: ~0-30 seconds  
> - Amplitude normalization: -10dBFS
> - Normalized with: Audacity
> - Downsampled with: Audacity
> - Recorded with: VB-Audio Hi-Fi Cable (Bit-perfect virtual cable, Jockie)
> - Converted with: FFmpeg (Ugoku)
> - Recording method:
>   -  Ugoku: Convertion with FFmpeg with the corresponding audio chain
>      -  FLAC -> Ogg 320 -> Opus 510 ("High" quality)
>      -  FLAC -> Opus 510 ("Hifi" quality)
>   -  Jockie: Record Discord's audio output with the virtual cable
> - Audio quality:
>   -  Ugoku: High (Spotify), Hifi (Deezer)
>   -  Jockie: No Patreon subscription to Jockie


<h2>Results:</h2>

<div align="center">
  <h2>Delta of spectra (Lower absolute value is better)</h2>
  <h3>Ugoku, Hifi quality:</h3>
  <img src="benchmarks/measures/delta_spectra_hifi.jpg" alt="delta of spectra ugoku, hifi quality"/>
  <h3>Ugoku, High quality:</h3>
  <img src="benchmarks/measures/delta_spectra_high.jpg" alt="delta of spectra ugoku, high quality"/>
  <h3>Jockie:</h3>
  <img src="benchmarks/measures/delta_spectra_jockie.jpg" alt="delta of spectra jockie"/>
  <h2>Delta waveform (Lower is better)</h2>
  <h3>Ugoku, Hifi quality:</h3>
  <img src="benchmarks/measures/delta_waveform_hifi.jpg" alt="delta waveform ugoku, hifi quality"/>
  <h3>Ugoku, High quality:</h3>
  <img src="benchmarks/measures/delta_waveform_high.jpg" alt="delta waveform ugoku, high quality"/>
  <h3>Jockie:</h3>
  <img src="benchmarks/measures/delta_waveform_jockie.jpg" alt="delta waveform jockie"/>
  <h2>Spectrum of delta (Lower is better)</h2>
  <h3>Ugoku, Hifi quality:</h3>
  <img src="benchmarks/measures/spectrum_delta_hifi.jpg" alt="spectrum of delta ugoku, hifi quality"/>
  <h3>Ugoku, High quality:</h3>
  <img src="benchmarks/measures/spectrum_delta_high.jpg" alt="spectrum of delta ugoku, high quality"/>
  <h3>Jockie:</h3>
  <img src="benchmarks/measures/spectrum_delta_jockie.jpg" alt="spectrum of delta jockie"/>
</div>
