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

    async def _get_banner_url(self):
        """Get and cache the application's banner URL (back-compat with banner_url).
        Adds verbose debug logging to diagnose missing banner issues."""
        try:
            now = time.time()
            cache_age = now - self._last_banner_fetch
            if self._cached_banner_url and cache_age < 300:  # cache 5 minutes
                logging.debug("[BANNER] Using cached banner URL (age=%.1fs): %s", cache_age, self._cached_banner_url)
                return self._cached_banner_url

            url = None

            # Try application banner using old and new attributes
            try:
                logging.debug("[BANNER] Fetching bot application info…")
                app_info = await self.music_cog.bot.application_info()
                logging.debug(
                    "[BANNER] app_info fetched. Has banner_url? %s; Has banner asset? %s",
                    'banner_url' in dir(app_info), bool(getattr(app_info, 'banner', None))
                )

                # Old discord.py provided banner_url directly
                banner_url_attr = getattr(app_info, "banner_url", None)
                logging.debug("[BANNER] app_info.banner_url = %s", banner_url_attr)
                if banner_url_attr:
                    url = banner_url_attr

                # Newer discord.py exposes an Asset at app_info.banner
                if not url and getattr(app_info, "banner", None):
                    try:
                        asset = app_info.banner.replace(size=4096)
                        url = asset.url
                        logging.debug("[BANNER] app_info.banner asset url = %s", url)
                    except Exception:
                        try:
                            url = app_info.banner.url
                            logging.debug("[BANNER] app_info.banner url (no replace) = %s", url)
                        except Exception:
                            url = None
            except Exception as e:
                logging.debug("[BANNER] Error fetching app_info/banner: %s", e)

            # Fallback to env-provided banner URL if available
            try:
                from config.settings import Config  # lazy import to avoid cycles
                if not url and getattr(Config, 'BOT_BANNER_URL', ''):
                    env_url = Config.BOT_BANNER_URL
                    # Normalize common share links (e.g., Google Drive viewer) to direct-view if possible
                    if 'drive.google.com' in env_url:
                        try:
                            # Patterns like: https://drive.google.com/file/d/<id>/view?usp=sharing
                            marker = '/file/d/'
                            if marker in env_url:
                                start = env_url.index(marker) + len(marker)
                                file_id = env_url[start:].split('/')[0]
                                env_url = f'https://drive.google.com/uc?export=view&id={file_id}'
                                logging.debug("[BANNER] Normalized Google Drive URL to direct-view: %s", env_url)
                        except Exception as norm_err:
                            logging.debug("[BANNER] Could not normalize Drive URL: %s", norm_err)
                    url = env_url
                    logging.debug("[BANNER] Using BOT_BANNER_URL fallback: %s", url)
            except Exception as env_err:
                logging.debug("[BANNER] Env fallback error: %s", env_err)

            self._cached_banner_url = url
            self._last_banner_fetch = now
            logging.debug("[BANNER] Final resolved banner URL: %s", self._cached_banner_url)
            return url
        except Exception:
            logging.exception("[BANNER] Unexpected error resolving banner URL")
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
        # Cancel previous update task
        if guild_id in self._update_tasks:
            self._update_tasks[guild_id].cancel()
        
        # Fetch banner in async context (cached)
        bot_banner_url = await self._get_banner_url()

        # Create new update task with small delay, pass banner
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
                logging.debug("No controller data for guild %s", guild_id)
                return
            message_id = controller_data[guild_str].get("message_id")
            channel_id = controller_data[guild_str].get("channel_id")
            if not message_id or not channel_id:
                logging.debug("Missing message/channel ID for guild %s", guild_id)
                return
            channel = self.music_cog.bot.get_channel(channel_id)
            if not channel:
                logging.debug("Controller channel not found: %s", channel_id)
                return
            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:  # type: ignore[attr-defined]
                logging.debug("Controller message not found: %s", message_id)
                return
            except Exception as fetch_error:
                logging.error("Error fetching controller message: %s", fetch_error)
                return
            queue = self.music_cog.get_queue(guild_id)
            embed = self.create_controller_embed(song_data, status, queue, bot_banner_url)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await message.edit(embed=embed)
                    logging.debug("Controller updated - Status: %s (attempt %d)", status, attempt + 1)
                    break
                except discord.HTTPException as http_error:  # type: ignore[attr-defined]
                    logging.debug("HTTP error updating controller (attempt %d): %s", attempt + 1, http_error)
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                    else:
                        logging.error("Failed to update controller after %d attempts", max_retries)
                except Exception as edit_error:
                    logging.error("Error editing controller message: %s", edit_error)
                    break
        except Exception as e:
            logging.exception("Error updating controller: %s", e)

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
            # Prefer large banner image; do not use bot avatar thumbnail
            bot_user = self.music_cog.bot.user if hasattr(self.music_cog.bot, "user") else None
            bot_avatar_url = None

            # Banner fetch: only fetch if in async context, otherwise skip
            # This function is sync, so skip banner fetch to avoid RuntimeWarning
            # If you want banner, pass it in from async context

            if song_data and status == "playing":
                embed = discord.Embed(  # type: ignore[attr-defined]
                    title="🎵 Now Playing",
                    description=f"""
**{song_data.get('title', 'Unknown Title')}**

Currently streaming high-quality audio
                    """,
                    color=0x00ff00
                )
                
                # Artist field
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
                
                # Duration
                if song_data.get('duration'):
                    duration_str = self.format_duration(song_data['duration'])
                    embed.add_field(name="⏱️ Duration", value=duration_str, inline=True)
                
                # Volume
                embed.add_field(name="🔊 Volume", value=f"{queue.volume}%", inline=True)
                
                # Queue info
                total_items = queue.total_items()
                embed.add_field(name="📋 Queue Size", value=f"{total_items} items", inline=True)
                
                # Next song
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
                
                # Status indicators
                status_text = "🟢 Playing"
                if queue.loop_mode:
                    status_text += " • Loop On"
                else:
                    status_text += " • Loop Off"
                if song_data.get('spotify_track'):
                    status_text += " • 🎵 Spotify"
                embed.add_field(name="📊 Status", value=status_text, inline=False)
                
                # Optional thumbnail if enabled via env
                try:
                    if getattr(Config, 'SHOW_CONTROLLER_THUMBNAIL', False) and getattr(Config, 'CONTROLLER_THUMBNAIL_URL', ''):
                        embed.set_thumbnail(url=Config.CONTROLLER_THUMBNAIL_URL)
                except Exception:
                    pass

                # Footer credit
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
                
                # Optional thumbnail if enabled via env
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
                
                # Optional thumbnail if enabled via env
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
                
                # Status indicators
                status_text = "🔴 Stopped"
                embed.add_field(name="📊 Status", value=status_text, inline=False)
                
                embed.set_footer(text="Developed by Soham-Das-afk on GitHub")
            
            return embed
        except Exception as e:
            logging.exception("Error creating controller embed: %s", e)
            return discord.Embed(title="Error", description="Failed to create embed", color=0xff0000)  # type: ignore[attr-defined]