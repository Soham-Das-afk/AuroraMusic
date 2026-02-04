import discord
import json
import asyncio
import time
import logging
from pathlib import Path
from config.settings import Config

class ControllerManager:
    """Manages music controller embeds"""

    def __init__(self, music_cog):
        self.music_cog = music_cog
        self.controller_data_file = Path(__file__).parent.parent.parent / "data" / "controller_data.json"
        self._update_tasks = {}  # Track pending updates
        self._last_update = {}   # Track last update time
        self._cached_banner_url = None
        self._last_banner_fetch = 0.0

    def is_controller_channel(self, guild_id: int, channel_id: int) -> bool:
        """Check if a channel is a registered controller channel for a guild."""
        controller_data = self.load_controller_data()
        guild_str = str(guild_id)
        if guild_str in controller_data:
            return controller_data[guild_str].get("channel_id") == channel_id
        return False

    async def _get_banner_url(self):
        """Get and cache the application's banner URL."""
        try:
            now = time.time()
            cache_age = now - self._last_banner_fetch
            if self._cached_banner_url and cache_age < 300:  # cache 5 minutes
                return self._cached_banner_url

            url = None

            try:
                app_info = await self.music_cog.bot.application_info()

                banner_url_attr = getattr(app_info, "banner_url", None)
                if banner_url_attr:
                    url = banner_url_attr

                if not url and getattr(app_info, "banner", None):
                    try:
                        asset = app_info.banner.replace(size=4096)
                        url = asset.url
                    except Exception:
                        try:
                            url = app_info.banner.url
                        except Exception:
                            url = None
            except Exception as e:
                logging.error(f"Exception: {e}")

            try:
                from config.settings import Config  # lazy import to avoid cycles
                if not url and getattr(Config, 'BOT_BANNER_URL', ''):
                    env_url = Config.BOT_BANNER_URL
                    if 'drive.google.com' in env_url:
                        try:
                            marker = '/file/d/'
                            if marker in env_url:
                                start = env_url.index(marker) + len(marker)
                                file_id = env_url[start:].split('/')[0]
                                env_url = f'https://drive.google.com/uc?export=view&id={file_id}'
                        except Exception as norm_err:
                            logging.error(f"Exception: {norm_err}")
                    url = env_url
            except Exception as env_err:
                logging.error(f"Exception: {env_err}")

            self._cached_banner_url = url
            self._last_banner_fetch = now
            return url
        except Exception:
            logging.exception("Unexpected error resolving banner URL")
            return None

    def load_controller_data(self):
        """Load controller data from JSON"""
        try:
            if self.controller_data_file.exists():
                with open(self.controller_data_file, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logging.error("Error loading controller data: %s", e)
            return {}

    async def update_controller_embed(self, guild_id, song_data=None, status="waiting"):
        """Update controller with debouncing and banner support"""
        if guild_id in self._update_tasks:
            self._update_tasks[guild_id].cancel()

        bot_banner_url = await self._get_banner_url()

        self._update_tasks[guild_id] = asyncio.create_task(
            self._delayed_update(guild_id, song_data, status, bot_banner_url)
        )

    async def _delayed_update(self, guild_id, song_data, status, bot_banner_url):
        """Delayed update with debouncing and banner support"""
        current_time = time.time()
        last_update = self._last_update.get(guild_id, 0)
        if current_time - last_update < 0.5:
            await asyncio.sleep(0.5 - (current_time - last_update))
        await self._perform_update(guild_id, song_data, status, bot_banner_url)
        self._last_update[guild_id] = time.time()

    async def _perform_update(self, guild_id, song_data=None, status="waiting", bot_banner_url=None):
        """Update controller embed with current info and banner"""
        try:
            controller_data = self.load_controller_data()
            guild_str = str(guild_id)
            if guild_str not in controller_data:
                return
            message_id = controller_data[guild_str].get("message_id")
            channel_id = controller_data[guild_str].get("channel_id")
            if not message_id or not channel_id:
                return
            channel = self.music_cog.bot.get_channel(channel_id)
            if not channel:
                return
            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:  # type: ignore[attr-defined]
                return
            except Exception as fetch_error:
                logging.error(f"Error fetching controller message: {fetch_error}")
                return
            queue = self.music_cog.get_queue(guild_id)
            embed = self.create_controller_embed(song_data, status, queue, bot_banner_url)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await message.edit(embed=embed)
                    break
                except discord.HTTPException as http_error:  # type: ignore[attr-defined]
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                    else:
                        logging.error(f"Failed to update controller after {max_retries} attempts")
                except Exception as edit_error:
                    logging.error(f"Error editing controller message: {edit_error}")
                    break
        except Exception as e:
            logging.exception(f"Error updating controller: {e}")

    def format_duration(self, seconds):
        """Format duration in MM:SS format"""
        try:
            if not seconds or seconds <= 0:
                return "Unknown"
            minutes = int(seconds // 60)
            seconds = int(seconds % 60)
            return f"{minutes}:{seconds:02d}"
        except Exception:
            return "Unknown"

    def create_controller_embed(self, song_data, status, queue, bot_banner_url=None):
        """Create controller embed with cleaned design (banner, thumbnail, organized fields)"""
        try:
            bot_user = self.music_cog.bot.user if hasattr(self.music_cog.bot, "user") else None
            bot_avatar_url = None


            if song_data and status == "playing":
                embed = discord.Embed(  # type: ignore[attr-defined]
                    title="🎵 Now Playing",
                    description=f"""
**{song_data.get('title', 'Unknown Title')}**

Currently streaming high-quality audio
                    """,
                    color=0x00ff00
                )

                uploader = song_data.get('uploader', 'Unknown Artist')
                if uploader in ['YouTube Search', 'Fallback Search', 'YouTube Alternative']:
                    title = song_data.get('title', '')
                    if ' - ' in title:
                        potential_artist = title.split(' - ')[0]
                        if len(potential_artist) < 50:
                            uploader = potential_artist
                    else:
                        uploader = "Unknown Artist"
                embed.add_field(name="👤 Artist", value=uploader, inline=True)

                if song_data.get('duration'):
                    duration_str = self.format_duration(song_data['duration'])
                    embed.add_field(name="⏱️ Duration", value=duration_str, inline=True)

                embed.add_field(name="🔊 Volume", value=f"{queue.volume}%", inline=True)

                total_items = queue.total_items()
                embed.add_field(name="📋 Queue Size", value=f"{total_items} items", inline=True)

                if queue.processed_queue:
                    next_song = list(queue.processed_queue)[0]
                    next_title = next_song.get('title', 'Unknown')
                    if len(next_title) > 50:
                        next_title = next_title[:47] + "..."
                    embed.add_field(name="⏭️ Up Next", value=next_title, inline=True)
                elif queue.queue:
                    embed.add_field(name="⏭️ Processing", value="Loading next songs...", inline=True)
                else:
                    embed.add_field(name="⏭️ Up Next", value="Nothing queued", inline=True)

                status_text = "🟢 Playing"
                if queue.loop_mode:
                    status_text += " • Loop On"
                else:
                    status_text += " • Loop Off"
                if song_data.get('spotify_track'):
                    status_text += " • 🎵 Spotify"
                embed.add_field(name="📊 Status", value=status_text, inline=False)

                try:
                    if getattr(Config, 'SHOW_CONTROLLER_THUMBNAIL', False) and getattr(Config, 'CONTROLLER_THUMBNAIL_URL', ''):
                        embed.set_thumbnail(url=Config.CONTROLLER_THUMBNAIL_URL)
                except Exception:
                    pass

                embed.set_footer(text="Developed by Soham-Das-afk on GitHub")

            elif song_data and status == "paused":
                embed = discord.Embed(  # type: ignore[attr-defined]
                    title="⏸️ Paused",
                    description=f"""
**{song_data.get('title', 'Unknown Title')}**

Playback is currently paused
                    """,
                    color=0xffff00
                )
                embed.add_field(name="🔊 Volume", value=f"{queue.volume}%", inline=True)
                total_items = queue.total_items()
                embed.add_field(name="📋 Queue", value=f"{total_items} items", inline=True)
                loop_status = "Loop On" if queue.loop_mode else "Loop Off"
                embed.add_field(name="📊 Status", value=f"⏸️ Paused • {loop_status}", inline=True)

                try:
                    if getattr(Config, 'SHOW_CONTROLLER_THUMBNAIL', False) and getattr(Config, 'CONTROLLER_THUMBNAIL_URL', ''):
                        embed.set_thumbnail(url=Config.CONTROLLER_THUMBNAIL_URL)
                except Exception:
                    pass

                embed.set_footer(text="Developed by Soham-Das-afk on GitHub")

            elif status == "loading":
                embed = discord.Embed(  # type: ignore[attr-defined]
                    title="⏳ Loading...",
                    description=f"""
**{song_data.get('title', 'Loading...') if song_data else 'Preparing audio...'}**

Please wait while we prepare your music
                    """,
                    color=0xffa500
                )
                embed.add_field(name="📊 Status", value="⏳ Loading", inline=True)
                embed.add_field(name="🔊 Volume", value=f"{queue.volume}%", inline=True)
                embed.add_field(name="📋 Queue", value=f"{queue.total_items()} items", inline=True)

                try:
                    if getattr(Config, 'SHOW_CONTROLLER_THUMBNAIL', False) and getattr(Config, 'CONTROLLER_THUMBNAIL_URL', ''):
                        embed.set_thumbnail(url=Config.CONTROLLER_THUMBNAIL_URL)
                except Exception:
                    pass

                embed.set_footer(text="Developed by Soham-Das-afk on GitHub")

            else:
                embed = discord.Embed(  # type: ignore[attr-defined]
                    title="🎵 AuroraMusic Controller",
                    description="""
**No music playing**

Send a song name, YouTube URL, Spotify link, or playlist to start!
                    """,
                    color=0x7289da
                )
                total_items = queue.total_items()
                if total_items > 0:
                    embed.add_field(name="📋 Queue", value=f"{total_items} items waiting", inline=True)
                    if queue.processed_queue:
                        next_song = list(queue.processed_queue)[0]
                        next_title = next_song.get('title', 'Unknown')
                        if len(next_title) > 50:
                            next_title = next_title[:47] + "..."
                        embed.add_field(name="⏭️ Up Next", value=next_title, inline=True)
                else:
                    embed.add_field(name="📋 Queue", value="No items in queue", inline=True)

                status_text = "🔴 Stopped"
                embed.add_field(name="📊 Status", value=status_text, inline=False)

                embed.set_footer(text="Developed by Soham-Das-afk on GitHub")

            return embed
        except Exception as e:
            logging.exception("Error creating controller embed: %s", e)
            return discord.Embed(title="Error", description="Failed to create embed", color=0xff0000)  # type: ignore[attr-defined]
