<div align="center">
  <a href="https://www.pixiv.net/en/artworks/130821036">
      <img src="https://i.imgur.com/WvyRtdu.png" alt="Illustration by Arren">
  </a>
  <p>Art by Arren !</p>
  <h1>Ugoku-v2 Discord Bot</h1>
</div>

**A work in progress rework of [Ugoku !](https://github.com/Shewiiii/Ugoku-bot)**, completely refactored and feature complete !  
Learn more about the bot here: https://ugoku.app/.


<h2>Requirements</h2>

- Python 3.12.x / 3.13.x
- A Discord bot token (get one [here](https://discord.com/developers/applications))
- FFmpeg

Music bot:

- A Spotify app (get one [here](https://developer.spotify.com/)).
- A Deezer Premium or Spotify Premium account.
- (Optional) An Imgur API key (get one [here](https://imgur.com/account/settings/apps)), to display the cover art for songs from custom sources.

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