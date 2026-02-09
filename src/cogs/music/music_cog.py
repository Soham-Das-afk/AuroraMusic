import discord
import asyncio
import time
import logging
from discord.ext import commands
from discord import app_commands
from collections import defaultdict
from urllib.parse import urlparse
from typing import Optional, Dict, Any
from pathlib import Path

from utils.history_manager import history_manager
from .handlers import ButtonHandlers
from .queue_manager import QueueManager
from .playback import PlaybackManager
from .handlers import ButtonHandlers
from .controller import ControllerManager
from utils.sources.search import search_song, search_playlist, is_playlist_url, validate_query
from config.settings import Config
from utils.sources.youtube import YTDLSource

class PerformanceMonitor:
    """Enhanced performance tracking"""

    def __init__(self):
        self.metrics = defaultdict(list)
        self.start_times = {}
        self.error_counts = defaultdict(int)

    def start_timer(self, operation: str, identifier: str = "default") -> str:
        """Start timer."""
        key = f"{operation}:{identifier}"
        self.start_times[key] = time.time()
        return key

    def end_timer(self, key: str) -> float:
        """End timer."""
        if key in self.start_times:
            duration = time.time() - self.start_times.pop(key)
            operation = key.split(':')[0]
            self.metrics[operation].append(duration)

            if len(self.metrics[operation]) > 50:
                self.metrics[operation].pop(0)

            return duration
        return 0.0

    def record_error(self, operation: str):
        """Record error."""
        self.error_counts[operation] += 1

    def get_avg_time(self, operation: str) -> float:
        """Get average time for operation"""
        times = self.metrics[operation]
        return sum(times) / len(times) if times else 0.0

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance stats"""
        stats = {}
        for operation, times in self.metrics.items():
            if times:
                stats[operation] = {  # ✅ FIXED: Missing implementation
                    'avg_time': self.get_avg_time(operation),
                    'count': len(times),
                    'errors': self.error_counts.get(operation, 0)
                }
        return stats

class MusicCog(commands.Cog, name="MusicCog"):
    """Enhanced main music cog with optimizations"""

    def __init__(self, bot):
        self.bot = bot
        self.queue_manager = QueueManager()
        self.controller_manager = ControllerManager(self)
        self.playback_manager = PlaybackManager(self, self.queue_manager)
        self.button_handlers = ButtonHandlers(self, self.queue_manager)
        self._processing_messages = set()
        self._last_update = {}
        self.perf_monitor = PerformanceMonitor()
        self.cleanup_task = self.bot.loop.create_task(self.cleanup_routines())

    def get_queue(self, guild_id: int):
        return self.queue_manager.get_queue(guild_id)

    async def safe_delete_message(self, message):
        try:
            await message.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            pass

    def is_music_channel(self, channel_id: int, guild_id: int) -> bool:
        return self.controller_manager.is_controller_channel(guild_id, channel_id)

    def _check_rate_limit(self, user_id: int, guild_id: int) -> bool:
        return True

    async def delete_after_delay(self, message, delay):
        await asyncio.sleep(delay)
        await self.safe_delete_message(message)

    async def cleanup_routines(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            self.queue_manager.cleanup_empty_queues()
            await asyncio.sleep(300) # Run every 5 minutes

    async def handle_song_request(self, message, query: str):
        timer_key = None # self.perf_monitor.start_timer("handle_song_request")
        guild_id = message.guild.id
        channel_id = message.channel.id
        message_key = f"{guild_id}:{message.id}"

        try:
            if not self.is_music_channel(channel_id, guild_id):
                await self.safe_delete_message(message)
                return

            if not self._check_rate_limit(message.author.id, guild_id):
                await self.safe_delete_message(message)
                return

            if message_key in self._processing_messages:
                await self.safe_delete_message(message)
                return

            self._processing_messages.add(message_key)

            queue = self.queue_manager.get_queue(guild_id)
            song_data, playlist_info = await self.queue_manager.add_to_queue(
                guild_id, query, requested_by=message.author.id
            )

            await self.safe_delete_message(message)

            if not message.guild.voice_client:
                voice_channel = message.author.voice.channel if message.author.voice else None
                if voice_channel:
                    await voice_channel.connect()
                else:
                    return

            asyncio.create_task(self.process_queue(guild_id, message.guild.voice_client))

            if not message.guild.voice_client.is_playing():
                await self.playback_manager.start_playback_when_ready(message.guild.voice_client, guild_id)

        except Exception as e:
            logging.error(f"Error handling song request: {e}")
            await self.safe_delete_message(message)
        finally:
            self._processing_messages.discard(message_key)

    async def _process_music_request(self, message, query):
        """Process the actual music request with auto-delete"""
        voice_client = await self._ensure_voice_connection(message)
        if not voice_client:
            return

        await self.safe_delete_message(message)

        status_msg = await message.channel.send("🔍 Searching...")

        try:
            if is_playlist_url(query):
                await self._handle_playlist_request(query, message.author, status_msg, message.guild.id, voice_client)
            else:
                await self._handle_single_song_request(query, message.author, status_msg, message.guild.id, voice_client)

        except Exception as e:
            logging.error("Error processing music request: %s", e)
            try:
                await status_msg.edit(content="❌ Request failed!")
                asyncio.create_task(self.delete_after_delay(status_msg, 3))
            except:
                pass

    async def _handle_single_song_request(self, query: str, requester, status_msg, guild_id: int, voice_client):
        """Handle single song request with order tracking"""
        try:
            queue = self.get_queue(guild_id)

            request_order = len(queue.queue) + 1

            request_data = {
                'type': 'song',
                'query': query,
                # use consistent key name 'requested_by' across the codebase
                'requested_by': requester,
                'status_msg': status_msg,
                'order': request_order,
                'timestamp': time.time()
            }

            queue.add_request(request_data)

            await status_msg.edit(content="🎵 Song queued! Processing...")
            asyncio.create_task(self.delete_after_delay(status_msg, 5))

            asyncio.create_task(self.process_queue(guild_id, voice_client))
            asyncio.create_task(self._check_and_start_playback(voice_client, guild_id))

        except Exception as e:
            logging.error("Error handling single song: %s", e)
            try:
                await status_msg.edit(content="❌ Song request failed!")
                asyncio.create_task(self.delete_after_delay(status_msg, 3))
            except:
                pass

    async def _handle_playlist_request(self, playlist_url: str, requester, status_msg, guild_id: int, voice_client):
        """Handle playlist request with better Spotify error handling"""
        try:
            await status_msg.edit(content="🔄 Processing playlist...")

            try:
                playlist_info, songs = await asyncio.wait_for(
                    search_playlist(playlist_url),
                    timeout=60.0  # Increased timeout for Spotify playlists
                )
            except asyncio.TimeoutError:
                await status_msg.edit(content="❌ Playlist processing timeout!")
                asyncio.create_task(self.delete_after_delay(status_msg, 5))
                return
            except Exception as search_error:
                logging.error("Playlist search error: %s", search_error)
                await status_msg.edit(content="❌ Playlist processing failed!")
                asyncio.create_task(self.delete_after_delay(status_msg, 5))
                return

            if not songs:
                await status_msg.edit(content="❌ No songs found in playlist!")
                asyncio.create_task(self.delete_after_delay(status_msg, 5))
                return

            total_songs = len(songs)
            playlist_title = (playlist_info or {}).get('title', 'Unknown Playlist')

            queue = self.get_queue(guild_id)

            for i, song in enumerate(songs):
                request_data = {
                    'type': 'song',
                    'query': song.get('title', 'Unknown'),
                    'song_data': song,
                    # use consistent key name 'requested_by'
                    'requested_by': requester,
                    'order': len(queue.queue) + 1,
                    'timestamp': time.time()
                }
                queue.add_request(request_data)

            if (playlist_info or {}).get('on_demand_conversion'):
                success_msg = f"✅ Added {total_songs} songs from **{playlist_title}** (Spotify)"
                success_msg += f"\n🎵 Songs will be converted during playback"
            else:
                success_msg = f"✅ Added {total_songs} songs from **{playlist_title}**"

            if (playlist_info or {}).get('owner'):
                success_msg += f" by {(playlist_info or {}).get('owner')}"

            await status_msg.edit(content=success_msg)
            asyncio.create_task(self.delete_after_delay(status_msg, 8))

            asyncio.create_task(self.process_queue(guild_id, voice_client))
            asyncio.create_task(self._check_and_start_playback(voice_client, guild_id))

        except Exception as e:
            logging.exception(f"Error handling playlist: {e}")
            try:
                await status_msg.edit(content="❌ Playlist processing failed!")
                asyncio.create_task(self.delete_after_delay(status_msg, 5))
            except:
                pass

    async def process_queue(self, guild_id: int, voice_client):
        """⚡ FIXED queue processing - Processes ONE request at a time."""
        timer_key = self.perf_monitor.start_timer("process_queue")

        queue = None
        try:
            queue = self.get_queue(guild_id)

            if queue.processing or not queue.queue:
                return

            queue.processing = True

            try:
                request = queue.queue.popleft()
                await self._process_song_request(request, guild_id)

            finally:
                queue.processing = False
                if queue.queue:
                    await asyncio.sleep(0.1) # Reduced delay to speed up queue processing
                    asyncio.create_task(self.process_queue(guild_id, voice_client))

        except Exception as e:
            logging.exception(f"[QUEUE] Error processing queue: {e}")
            if queue is not None:
                try:
                    queue.processing = False
                except Exception:
                    pass
            self.perf_monitor.record_error("process_queue")
        finally:
            self.perf_monitor.end_timer(timer_key)

    async def _delayed_process_queue(self, guild_id: int, voice_client, delay: float = 0.2):
        """Process next song after minimal delay"""
        await asyncio.sleep(delay)
        await self.process_queue(guild_id, voice_client)

    async def _process_song_request(self, request: Dict, guild_id: int):
        """Enhanced song processing with on-demand Spotify conversion"""
        try:
            query = request.get('query', 'Unknown')
            song_data = request.get('song_data')

            # normalize requester field name (support both keys if present)
            requester_id = request.get('requested_by') or request.get('requester')

            if song_data:
                if song_data.get('needs_conversion') and song_data.get('conversion_query'):

                    from utils.sources.spotify import spotify_handler

                    conversion_query = song_data['conversion_query']
                    youtube_song = await spotify_handler.search_youtube_for_track(song_data['spotify_info'])

                    if youtube_song:
                        queue = self.get_queue(guild_id)
                        # ensure requester preserved
                        if requester_id and not youtube_song.get('requested_by'):
                            youtube_song['requested_by'] = requester_id
                        queue.add_processed_song(youtube_song)
                    else:
                        queue = self.get_queue(guild_id)
                        if requester_id and not song_data.get('requested_by'):
                            song_data['requested_by'] = requester_id
                        queue.add_processed_song(song_data)
                else:
                    queue = self.get_queue(guild_id)
                    if requester_id and not song_data.get('requested_by'):
                        song_data['requested_by'] = requester_id
                    queue.add_processed_song(song_data)
                return

            song_result = await asyncio.wait_for(
                search_song(query),
                timeout=10.0
            )

            if song_result:
                queue = self.get_queue(guild_id)
                # attach requester to the resolved song so history works reliably
                if requester_id and not song_result.get('requested_by'):
                    song_result['requested_by'] = requester_id
                queue.add_processed_song(song_result)
            else:
                logging.error("No result for: %s", query)

            

        except asyncio.TimeoutError:
            logging.error("Song processing timeout: %s", request.get('query', ''))
        except Exception as e:
            logging.error("Error processing song: %s", e)

    async def _check_and_start_playback(self, voice_client, guild_id: int):
        """Quick playback checker - SINGLE attempt only"""
        await asyncio.sleep(0.5)

        if voice_client.is_playing() or voice_client.is_paused():
            return

        queue = self.queue_manager.get_queue(guild_id)
        if queue.has_songs():
            await self.playback_manager.start_playback(voice_client, guild_id)
            return

        for i in range(10):  # 5 seconds max
            await asyncio.sleep(0.5)
            if queue.has_songs():
                await self.playback_manager.start_playback(voice_client, guild_id)
                return

    async def _ensure_voice_connection(self, message):
        """Ensure voice connection with auto-delete errors and retry logic"""
        if message.guild.voice_client:
            return message.guild.voice_client

        if not message.author.voice or not message.author.voice.channel:
            error_msg = await message.channel.send("❌ You need to be in a voice channel!")
            asyncio.create_task(self.delete_after_delay(error_msg, 3))
            return None

        channel = message.author.voice.channel
        bot_member = message.guild.me

        if not channel.permissions_for(bot_member).connect:
            error_msg = await message.channel.send("❌ I don't have permission to connect to that voice channel!")
            asyncio.create_task(self.delete_after_delay(error_msg, 3))
            return None

        if not channel.permissions_for(bot_member).speak:
            error_msg = await message.channel.send("❌ I don't have permission to speak in that voice channel!")
            asyncio.create_task(self.delete_after_delay(error_msg, 3))
            return None

        for attempt in range(3):
            try:
                voice_client = await asyncio.wait_for(channel.connect(), timeout=15.0)
                return voice_client
            except Exception as e:
                error_str = str(e)
                logging.error("Voice connection error (attempt %d/3): %s", attempt+1, error_str)
                if "4006" in error_str or "Session invalidated" in error_str:
                    wait_time = 2 + attempt * 3
                    await asyncio.sleep(wait_time)
                else:
                    error_msg = await message.channel.send(f"❌ Connection failed: {e}")
                    asyncio.create_task(self.delete_after_delay(error_msg, 3))
                    return None
        error_msg = await message.channel.send("❌ Could not connect to voice channel after several attempts.")
        asyncio.create_task(self.delete_after_delay(error_msg, 3))
        return None

    async def update_controller_embed(self, guild_id: int, song_data=None, status="waiting"):
        """Update controller embed - delegate to controller manager"""
        try:
            await self.controller_manager.update_controller_embed(guild_id, song_data, status)
        except Exception as e:
            logging.error("Error updating controller: %s", e)

    async def handle_play_pause(self, interaction):
        await self.button_handlers.handle_play_pause(interaction)

    async def handle_skip(self, interaction):
        await self.button_handlers.handle_skip(interaction)

    async def handle_stop(self, interaction):
        await self.button_handlers.handle_stop(interaction)

    async def handle_shuffle(self, interaction):
        await self.button_handlers.handle_shuffle(interaction)

    async def handle_previous(self, interaction):
        await self.button_handlers.handle_previous(interaction)

    async def handle_loop(self, interaction):
        await self.button_handlers.handle_loop(interaction)

    async def monitor_voice_connection(self, guild_id: int):
        """Monitor voice connection stability"""
        while True:
            await asyncio.sleep(30)

    async def _delayed_update(self, guild_id, song_data, status):
        """Delayed update with better debouncing"""
        current_time = time.time()
        last_update = self._last_update.get(guild_id, 0)

        if current_time - last_update < 2.0:
            await asyncio.sleep(2.0 - (current_time - last_update))

        try:
            await self.controller_manager.update_controller_embed(guild_id, song_data, status)
            self._last_update[guild_id] = time.time()
        except discord.HTTPException as e:
            if "rate limited" in str(e).lower():
                logging.warning("Rate limited updating controller, retrying in 5s...")
                await asyncio.sleep(5)
                await self.controller_manager.update_controller_embed(guild_id, song_data, status)
            else:
                logging.error("HTTP error updating controller: %s", e)

    async def cog_unload(self):
        """Cleanup when cog is unloaded"""
        if hasattr(self, 'cleanup_task'):
            self.cleanup_task.cancel()

async def setup(bot):
    """Setup function required by discord.py"""
    try:
        cog = MusicCog(bot)
        await bot.add_cog(cog)
        logging.info("MusicCog setup complete: %s", cog)
    except Exception as e:
        logging.exception(f"Error setting up MusicCog: {e}")
        raise
