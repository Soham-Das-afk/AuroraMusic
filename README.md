# AuroraMusic Discord Music Bot (v3.2.35)

<!-- If this repo is public, you can use dynamic GitHub badges below:
![GitHub release (latest by date)](https://img.shields.io/github/v/release/Soham-Das-afk/AuroraMusic)
![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/Soham-Das-afk/AuroraMusic/release.yml?branch=master)
-->
[![release](https://img.shields.io/badge/release-v3.2.35-blue)](https://github.com/Soham-Das-afk/AuroraMusic/releases/latest)
[![build](https://img.shields.io/badge/build-GitHub%20Actions-blue)](https://github.com/Soham-Das-afk/AuroraMusic/actions)

<!-- Note: Repo is currently private (dynamic GitHub badges require public visibility). Once public, you can uncomment the dynamic badges above -->
![Docker Image Version (latest by date)](https://img.shields.io/docker/v/sohamdas103/auroramusic?label=docker)
![Docker Pulls](https://img.shields.io/docker/pulls/sohamdas103/auroramusic)

Quick links:
- Latest Release: https://github.com/Soham-Das-afk/AuroraMusic/releases/latest
- Docker Hub: https://hub.docker.com/r/sohamdas103/auroramusic

AuroraMusic is a feature-rich music bot designed for Discord servers, allowing users to play music from various sources, manage queues, and interact with an intuitive user interface. This bot supports both YouTube and Spotify, providing a seamless music experience for users.

## Quick start (copy-paste)

Windows (local):
```powershell
git clone https://github.com/Soham-Das-afk/AuroraMusic.git
cd AuroraMusic
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# edit .env to set BOT_TOKEN and ALLOWED_GUILD_IDS; set YOUTUBE_COOKIES=cookies/youtube.txt (recommended)
python src/bot.py
```

Linux (local):
```bash
git clone https://github.com/Soham-Das-afk/AuroraMusic.git
cd AuroraMusic
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env to set BOT_TOKEN and ALLOWED_GUILD_IDS; set YOUTUBE_COOKIES=cookies/youtube.txt (recommended)
python3 src/bot.py
```

Docker (both OS):
```bash
# ensure .env exists and is filled; cookies recommended at cookies/youtube.txt
docker compose up -d --build
docker compose logs -f
```

Run directly with Docker (without Compose):

Windows PowerShell
```powershell
# assumes you created and filled .env in the project folder
docker pull sohamdas103/auroramusic:latest
docker run --name auroramusic ^
   --env-file .env ^
   -v "$PWD/cookies:/app/src/cookies:ro" ^
   -v "$PWD/data:/app/src/data" ^
   -v "$PWD/downloads:/app/src/downloads" ^
   -p 8080:8080 ^
   -d sohamdas103/auroramusic:latest
```

Linux/macOS
```bash
# assumes you created and filled .env in the project folder
docker pull sohamdas103/auroramusic:latest
docker run --name auroramusic \
   --env-file .env \
   -v "$(pwd)/cookies:/app/src/cookies:ro" \
   -v "$(pwd)/data:/app/src/data" \
   -v "$(pwd)/downloads:/app/src/downloads" \
   -p 8080:8080 \
   -d sohamdas103/auroramusic:latest
```

## Features

- **Modern Controller UI**: A welcome banner card (uses your Discord App banner or `BOT_BANNER_URL`), plus a clean controller embed (no image) with clear fields for queue, next song, volume, and status.
- **Multi-Source Playback**: Play music from YouTube and Spotify, including single tracks and playlists.
- **Queue Management**: Add, view, shuffle, and manage a queue of tracks.
- **Autoplay**: Automatically find and play related tracks when the queue ends.
- **Interactive Controls**: Use buttons for play, pause, skip, and other controls directly in Discord.
- **Slash Commands**: Modern slash commands for setup and status, plus a message-based controller for music requests.
   - On startup, the bot now clears any old guild slash commands and republishes the latest set for the guilds it's in (clear-and-resync). This ensures you always see the current commands.
- **Rich Embeds**: Displays detailed information about the currently playing track and the queue.
- **Voice Integration**: Joins voice channels and streams high-quality audio.
- **Error Handling**: Provides user-friendly error messages and robust exception handling.
- **Persistent State**: Remembers playback history and controller channel information per guild.
- **Pre-caching**: Downloads the next track in the queue for smooth playback.

## Installation (local)

1. Clone the repository:
   ```
   git clone https://github.com/Soham-Das-afk/AuroraMusic.git
   cd AuroraMusic
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file based on the `.env.example` template and fill in your credentials:
   - On Windows PowerShell:
     ```
     Copy-Item .env.example .env
     ```
   - Or copy manually in Explorer.

4. Configure `ALLOWED_GUILD_IDS` in the `.env` file to restrict the bot from joining unwanted servers.

## Usage (local)

- Start the bot by running:
   ```
   python src/bot.py
   ```

- Use `/setup` to create a dedicated music controller channel in your server.

- In the controller channel:
   - Send a song name, YouTube URL, or Spotify link (no prefix needed)
   - Use the controller buttons (Play/Pause, Skip, Previous, Stop, Rewind/Forward 10s, Volume, Loop, Shuffle)

- Helpful slash commands:
   - `/help` — quick usage guide and links to your controller channel
   - `/ping` — bot latency/status (shows AuroraMusic v3.2.35)
   - `/health` — configuration and queue summary
   - `/cleanup` — remove the controller (admin only)

Permissions note:
- The bot should have “Manage Messages” in the controller channel for auto-cleanup of helper messages.

### Downloads and Cleanup

- Downloads folder: `src/downloads` (configurable via `Config.DOWNLOADS_DIR`)
- Files older than 1 day are automatically deleted; we also keep the total under 100 files by removing the oldest if needed.
- Cache persistence across restarts: by default the cache is preserved. Set `CLEAR_CACHE_ON_START=true` if you want to start fresh each run.
- Cleanup runs hourly in the background. You can adjust these settings in `utils/file_manager.py` if desired.

## Step-by-step setup

### Windows (local, without Docker)

1) Install prerequisites
   - Install Python 3.11 (enable “Add to PATH”).
   - Install FFmpeg:
     - Using winget:
       ```powershell
       winget install Gyan.FFmpeg
       ```
     - Or using Chocolatey:
       ```powershell
       choco install ffmpeg
       ```
   - Verify:
     ```powershell
     python --version
     ffmpeg -version
     ```

2) Get the code and set up a virtual environment
   ```powershell
   git clone https://github.com/Soham-Das-afk/AuroraMusic.git
   cd AuroraMusic
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3) Configure environment
   ```powershell
   Copy-Item .env.example .env
   ```
   - Open `.env` and set:
     - BOT_TOKEN=your discord bot token
     - ALLOWED_GUILD_IDS=comma,separated,guild,ids
     - Optional: SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET
   - Optional (recommended): YOUTUBE_COOKIES=cookies/youtube.txt  # helps bypass age/region restrictions
     - Optional: OWNER_CONTACT=your handle or ID for contact

4) Run the bot
   ```powershell
   python src/bot.py
   ```

5) In Discord, run `/setup` in a server you own to create the music controller channel.

Tip: If venv activation is blocked, run PowerShell as admin once and execute:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Linux (local, without Docker)

1) Install prerequisites (Debian/Ubuntu example)
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-venv python3-pip ffmpeg libopus0 libsodium23
   ```
   - Verify:
   ```bash
   python3 --version
   ffmpeg -version
   ```

2) Get the code and set up a virtual environment
   ```bash
   git clone https://github.com/Soham-Das-afk/AuroraMusic.git
   cd AuroraMusic
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3) Configure environment
   ```bash
   cp .env.example .env
   ```
   - Edit `.env` and set BOT_TOKEN, ALLOWED_GUILD_IDS, and any optional values.

4) Run the bot
   ```bash
   python3 src/bot.py
   ```

5) Use `/setup` in your server to create the music controller.

### Environment variables

Required:
- `BOT_TOKEN` — your Discord bot token
- `ALLOWED_GUILD_IDS` — comma-separated list of server IDs where the bot is allowed

Optional:
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` — enable Spotify features
- `YOUTUBE_COOKIES` — (recommended) path to cookies file (e.g., `cookies/youtube.txt`) to help bypass age or regional restrictions and improve reliability
 - `BOT_BANNER_URL` — optional fallback image/GIF URL for the welcome banner if your Discord App doesn’t have a banner (example: `https://cdn.example.com/banner.gif`)
 - `CONTROLLER_THUMBNAIL_URL` — optional controller thumbnail image URL (not shown by default; can be enabled later)
 - `SHOW_BANNER` — show the welcome banner image card (true/false; accepts 1/0, true/false, yes/no, y/n)
 - `SHOW_CONTROLLER_THUMBNAIL` — show a small thumbnail on controller embeds (true/false; accepts 1/0, true/false, yes/no, y/n)
 - `OWNER_CONTACT` — contact string shown for unauthorized guilds (e.g., Discord handle/ID)
 - `AUTO_RESTART_ENABLED` — enable daily auto-restart (true/false, default true)
 - `AUTO_RESTART_TIME` — time for restart in HH:MM (default 06:00)
 - `AUTO_RESTART_TZ_OFFSET_MINUTES` — timezone offset in minutes (IST=330)
 - `CLEAR_CACHE_ON_START` — when true, delete all cached audio files on startup; when false (default), keep the cache across restarts
 
### Hosting your banner image (recommended options)

If your Discord App banner isn’t set or you prefer a custom GIF, set `BOT_BANNER_URL` to a direct image URL. Reliable, no-login choices:

- ImgBB (simple, free):
   1. Go to https://imgbb.com/
   2. Upload your image/GIF (leave “expiration” as Don’t autodelete)
   3. After upload, open the image, choose “Embed codes” or “Links” and copy the Direct link
       - It must look like `https://i.ibb.co/xxxx/banner.gif` (note the `i.ibb.co` host and file extension)
   4. Set `BOT_BANNER_URL` in `.env` to that direct link

- GitHub via jsDelivr (immutable + fast CDN):
   - Commit `assets/banner.gif` to your repo
   - Use: `https://cdn.jsdelivr.net/gh/<user>/<repo>@<tag-or-commit>/assets/banner.gif`

Tip: Avoid page/album links (they return HTML). You want links ending in `.gif`, `.png`, or `.jpg` with `Content-Type: image/*`.

## Docker

Build the image and run with Docker Compose (recommended):

1. Ensure `.env` includes the required variables listed above.
2. Place cookies (recommended) on the host at `AuroraMusic/cookies/youtube.txt` and set `YOUTUBE_COOKIES=cookies/youtube.txt` in `.env` (helps bypass age/region restrictions).
3. From the project folder:
    ```
    docker compose up -d --build
    docker compose logs -f
    ```

Notes:
- Personal cookies and runtime data are not baked into the image. The compose file mounts:
   - `./cookies -> /app/src/cookies:ro`
   - `./data -> /app/src/data`
   - `./downloads -> /app/src/downloads`
- To stop the container:
   ```
   docker compose down
   ```
- Multi-arch images: Starting with v3.2.35+, images are published for `linux/amd64` and `linux/arm64` (Apple Silicon, Graviton, etc.). Docker will automatically pull the correct architecture manifest.
 
### Windows (Docker Desktop)

1) Install Docker Desktop and ensure WSL 2 backend is enabled.
2) Configure `.env` (copy from `.env.example`).
3) Recommended: Place YouTube cookies at `AuroraMusic/cookies/youtube.txt` and set `YOUTUBE_COOKIES=cookies/youtube.txt` in `.env` (bypasses age or regional access limits).
4) From the project folder:
   ```powershell
   docker compose up -d --build
   docker compose logs -f
   ```
5) Stop when needed:
   ```powershell
   docker compose down
   ```

### Linux (Docker Engine + Compose)

1) Install Docker Engine and Compose plugin (Debian/Ubuntu example):
   ```bash
   sudo apt update
   sudo apt install -y docker.io docker-compose-plugin
   sudo usermod -aG docker $USER
   newgrp docker
   docker compose version
   ```
2) Configure `.env` and cookies as above.
3) Build and run:
   ```bash
   docker compose up -d --build
   docker compose logs -f
   ```
4) Stop:
   ```bash
   docker compose down
   ```

### Upgrade

- Docker (Compose):
   ```bash
   docker compose pull
   docker compose up -d --pull always
   ```
- Docker (direct run):
   ```bash
   docker pull sohamdas103/auroramusic:latest
   docker stop auroramusic && docker rm auroramusic
   # re-run the docker run command from above
   ```
- From source (venv):
   ```powershell
   git pull
   pip install -r requirements.txt
   python src/bot.py
   ```

## CI/CD

- Pushing a tag like `v3.2.35` triggers GitHub Actions to:
   - Build and push Docker images (if secrets are configured)
   - Create a GitHub Release with notes

- Required repo secrets (Settings → Secrets and variables → Actions):
   - `DOCKERHUB_USERNAME`: your Docker Hub username (e.g., `sohamdas103`)
   - `DOCKERHUB_TOKEN`: a Docker Hub Personal Access Token with write permissions

- If secrets are not configured, the workflow will still create the GitHub Release and skip Docker push.

## Troubleshooting

- Token/authorization errors: Double-check `BOT_TOKEN` in `.env` and that the bot was invited with the right scopes (bot + applications.commands).
- Slash commands not showing: The bot clears and re-syncs per-guild on startup, but global propagation can still take time. Try re-inviting or restarting; check logs.
- FFmpeg not found: Ensure `ffmpeg -version` works in your shell/terminal. Install FFmpeg and add to PATH.
- Voice playback issues on Linux: Ensure `libopus0` and `libsodium` are installed (see Linux prerequisites).
- Permissions: In the controller channel, grant “Manage Messages” to the bot for best cleanup behavior.

## Maintenance

I maintain this project when it’s needed or when I get time. If you run into issues or have suggestions, feel free to reach out directly:

- Discord: @sick._.duck.103 (Discord ID: 616499661951467530)

  

## License

This project uses a source-available license tailored for AuroraMusic. You may use and host the bot, and propose improvements, but you may not publish, distribute, sublicense, or sell the software or derivatives. See the `LICENSE` file for the full terms.

## Ownership and attribution

The source code in this repository is solely owned by the author (Discord: @sick._.duck.103, ID: 616499661951467530).

- You are allowed to use and host this code to run Discord music bots.
- You are not allowed to claim ownership or authorship of this code.
- If you redistribute or fork, retain the existing credits and the notice from this repository (see `NOTICE`).
- If you are hosting the bot publicly, keep the in-bot footer credit and/or provide visible attribution in your deployment.