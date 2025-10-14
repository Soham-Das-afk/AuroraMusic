import discord
import asyncio
import time
import traceback
import logging
from discord.ext import commands
from discord import app_commands
from collections import defaultdict
from urllib.parse import urlparse
from typing import Optional, Dict, Any
from pathlib import Path

from .queue_manager import QueueManager
from .playback import PlaybackManager
from .handlers import ButtonHandlers
from .controller import ControllerManager
from utils.sources.search import search_song, search_playlist, is_playlist_url, validate_query
from config.settings import Config
from utils.sources.youtube import YTDLSource
from utils.file_manager import FileManager

class PerformanceMonitor:
    """Enhanced performance tracking"""
    
    def __init__(self):
        self.metrics = defaultdict(list)
        self.start_times = {}
        self.error_counts = defaultdict(int)
    
    def start_timer(self, operation: str, identifier: str = "default") -> str:
        """Start timing an operation"""
        key = f"{operation}:{identifier}"
        self.start_times[key] = time.time()
        return key
    
    def end_timer(self, key: str) -> float:
        """End timing and record metric"""
        if key in self.start_times:
            duration = time.time() - self.start_times.pop(key)
            operation = key.split(':')[0]
            self.metrics[operation].append(duration)
            
            # Keep only last 50 measurements per operation
            if len(self.metrics[operation]) > 50:
                self.metrics[operation].pop(0)  # ✅ FIXED: Missing line
            
            return duration
        return 0.0
    
    def record_error(self, operation: str):
        """Record an error for an operation"""
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
        self.playback_manager = PlaybackManager(self, self.queue_manager)
        self.button_handlers = ButtonHandlers(self, self.queue_manager)
        self.controller_manager = ControllerManager(self)
        self._processing_messages = set()
        self.perf_monitor = PerformanceMonitor()
        self.file_manager = FileManager()
        
        # ✅ Add rate limiting
        self._user_cooldowns = {}
        self._guild_cooldowns = {}
        
        # ✅ FIXED: Better state tracking
        self._last_update = {}  # Last update time per guild
        self._update_lock = asyncio.Lock()  # Lock for update operations
    
        # Start cleanup task
        self.cleanup_task = asyncio.create_task(self._periodic_cleanup())
    
    async def _periodic_cleanup(self):
        """Periodic cleanup of old files"""
        while True:
            try:
                await asyncio.sleep(3600)  # Every hour
                await self.file_manager.cleanup_old_files()
            except Exception as e:
                logging.debug("Cleanup task error: %s", e)
    
    def get_queue(self, guild_id: int):
        """Get queue for guild"""
        return self.queue_manager.get_queue(guild_id)
    
    def get_playback_lock(self, guild_id: int):
        """Get playback lock for guild"""
        return self.queue_manager.get_lock(guild_id)
    
    def _check_rate_limit(self, user_id: int, guild_id: int) -> bool:
        """LENIENT rate limiting - don't discard songs"""
        current_time = time.time()
        
        # ✅ VERY lenient user rate limit: 1 request per 1 second (was 2s)
        user_key = f"user_{user_id}"
        if user_key in self._user_cooldowns:
            if current_time - self._user_cooldowns[user_key] < 1.0:
                return False  # ✅ FIXED: Missing line
        self._user_cooldowns[user_key] = current_time
        
        # ✅ VERY lenient guild rate limit: 1 request per 0.3 seconds (was 0.5s)
        guild_key = f"guild_{guild_id}"
        if guild_key in self._guild_cooldowns:
            if current_time - self._guild_cooldowns[guild_key] < 0.3:
                return False  # ✅ FIXED: Missing line
        self._guild_cooldowns[guild_key] = current_time
        
        return True
    
    async def delete_after_delay(self, message, delay: int = 5):
        """Enhanced message deletion with error handling"""
        try:
            await asyncio.sleep(delay)
            
            # Check if message still exists before trying to delete
            if message:
                await message.delete()  # ✅ FIXED: Missing line
                logging.debug("Auto-deleted message after %ds", delay)
                
        except discord.NotFound:
            logging.debug("Message already deleted")
        except discord.Forbidden:
            logging.debug("No permission to delete message")
        except discord.HTTPException as e:
            logging.debug("HTTP error deleting message: %s", e)
        except Exception as e:
            logging.debug("Error auto-deleting message: %s", e)

    async def safe_delete_message(self, message):
        """Enhanced message deletion with error handling"""
        try:
            if message and not message.author.bot:
                await message.delete()  # ✅ FIXED: Missing line
                logging.debug("Deleted user message")
        except discord.NotFound:
            pass  # Already deleted
        except discord.Forbidden:
            logging.debug("No permission to delete message")
        except discord.HTTPException as e:
            logging.debug("HTTP error deleting message: %s", e)
        except Exception as e:
            logging.debug("Error deleting message: %s", e)

    def is_music_channel(self, channel_id: int, guild_id: int) -> bool:
        """Check if a channel is a registered music controller channel"""
        try:
            import json  # ✅ FIXED: Missing import
            from pathlib import Path
            
            controller_data_file = Path(__file__).parent.parent.parent / "data" / "controller_data.json"
            
            if controller_data_file.exists():
                with open(controller_data_file, 'r') as f:  # ✅ FIXED: Missing implementation
                    controller_data = json.load(f)
                
                guild_str = str(guild_id)
                if guild_str in controller_data:
                    return controller_data[guild_str].get("channel_id") == channel_id
            
            return False
            
        except Exception as e:
            logging.debug("Error checking music channel: %s", e)
            return False

    async def handle_song_request(self, message: discord.Message, query: str) -> None:
        """Enhanced request handler with channel validation"""
        timer_key = self.perf_monitor.start_timer("handle_song_request")
        
        try:
            guild = getattr(message, 'guild', None)
            if not guild:
                # Ignore DMs
                await self.safe_delete_message(message)
                return
            guild_id = guild.id
            channel = getattr(message, 'channel', None)
            channel_id = getattr(channel, 'id', 0)
            channel_name = getattr(channel, 'name', str(channel_id))
            # Block requests from unauthorized guilds (skip DMs)
            if not Config.is_guild_allowed(guild_id):
                logging.debug("Ignoring music request from unauthorized guild: %s (%s)", guild.name, guild_id)
                await self.safe_delete_message(message)
                return
            
            # ✅ STRICT VALIDATION: Only process requests in registered controller channels
            if not self.is_music_channel(channel_id, guild_id):
                logging.debug("Ignoring request in non-controller channel: #%s", channel_name)
                return
            
            logging.debug("[CONTROLLER] Request: '%s' by %s", query, message.author.display_name)
            
            # ✅ Input validation
            if not validate_query(query):
                await self.safe_delete_message(message)  # ✅ FIXED: Missing line
                return
            
            # ✅ Rate limiting
            if not self._check_rate_limit(message.author.id, guild_id):
                await self.safe_delete_message(message)  # ✅ FIXED: Missing line
                return
            
            # ✅ Prevent duplicate processing
            message_key = f"{guild_id}_{message.id}"
            if message_key in self._processing_messages:
                logging.debug("Already processing message %s", message.id)  # ✅ FIXED: Missing line
                return
            self._processing_messages.add(message_key)
            
            try:
                await asyncio.wait_for(  # ✅ FIXED: Missing implementation
                    self._process_music_request(message, query),
                    timeout=60.0  # Increased timeout for Spotify playlists
                )
            
            except discord.HTTPException as e:
                logging.debug("Discord API error: %s", e)  # ✅ FIXED: Missing line
                await self.safe_delete_message(message)
            except asyncio.TimeoutError:
                logging.debug("Request processing timeout: %s", query)  # ✅ FIXED: Missing line
                await self.safe_delete_message(message)
            except Exception as inner_error:
                logging.debug("Error processing request: %s", inner_error)  # ✅ FIXED: Missing line
                await self.safe_delete_message(message)
            finally:
                self._processing_messages.discard(message_key)  # ✅ FIXED: Missing line
                
        except Exception as e:
            logging.exception("Unexpected error handling request: %s", e)
            traceback.print_exc()
            self.perf_monitor.record_error("handle_song_request")
            await self.safe_delete_message(message)
        finally:
            self.perf_monitor.end_timer(timer_key)
    
    async def _process_music_request(self, message, query):
        """Process the actual music request with auto-delete"""
        # Ensure voice connection
        voice_client = await self._ensure_voice_connection(message)
        if not voice_client:
            return
        
        # Delete user message
        await self.safe_delete_message(message)
        
        # Send status message
        status_msg = await message.channel.send("🔍 Searching...")
        
        try:
            # Check if it's a playlist
            if is_playlist_url(query):
                await self._handle_playlist_request(query, message.author, status_msg, message.guild.id, voice_client)
            else:
                await self._handle_single_song_request(query, message.author, status_msg, message.guild.id, voice_client)
        
        except Exception as e:
            logging.debug("Error processing music request: %s", e)
            try:
                await status_msg.edit(content="❌ Request failed!")
                asyncio.create_task(self.delete_after_delay(status_msg, 3))
            except:
                pass

    async def _handle_single_song_request(self, query: str, requester, status_msg, guild_id: int, voice_client):
        """Handle single song request with order tracking"""
        try:
            queue = self.get_queue(guild_id)
            
            # ✅ Add order tracking
            request_order = len(queue.queue) + 1
            
            request_data = {
                'type': 'song',
                'query': query,
                'requester': requester,
                'status_msg': status_msg,
                'order': request_order,
                'timestamp': time.time()
            }
            
            queue.add_request(request_data)
            logging.debug("Added request #%s: %s", request_order, query[:50])
            
            await status_msg.edit(content="🎵 Song queued! Processing...")
            asyncio.create_task(self.delete_after_delay(status_msg, 5))
            
            # Start processing
            asyncio.create_task(self.process_queue(guild_id, voice_client))
            asyncio.create_task(self._check_and_start_playback(voice_client, guild_id))
            
        except Exception as e:
            logging.debug("Error handling single song: %s", e)
            try:
                await status_msg.edit(content="❌ Song request failed!")
                asyncio.create_task(self.delete_after_delay(status_msg, 3))
            except:
                pass

    async def _handle_playlist_request(self, playlist_url: str, requester, status_msg, guild_id: int, voice_client):
        """Handle playlist request with better Spotify error handling"""
        try:
            await status_msg.edit(content="🔄 Processing playlist...")
            
            # ✅ Add timeout and better error handling
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
                logging.debug("Playlist search error: %s", search_error)
                await status_msg.edit(content="❌ Playlist processing failed!")
                asyncio.create_task(self.delete_after_delay(status_msg, 5))
                return
            
            if not songs:
                await status_msg.edit(content="❌ No songs found in playlist!")
                asyncio.create_task(self.delete_after_delay(status_msg, 5))
                return
            
            # ✅ Process all songs
            total_songs = len(songs)
            playlist_title = (playlist_info or {}).get('title', 'Unknown Playlist')
            
            logging.debug("Adding %d songs from '%s' to queue", total_songs, playlist_title)
            
            queue = self.get_queue(guild_id)
            
            # Add all songs to queue
            for i, song in enumerate(songs):
                request_data = {
                    'type': 'song',
                    'query': song.get('title', 'Unknown'),
                    'song_data': song,
                    'requester': requester,
                    'order': len(queue.queue) + 1,
                    'timestamp': time.time()
                }
                queue.add_request(request_data)
            
            # ✅ Better success message with playlist info
            if (playlist_info or {}).get('on_demand_conversion'):
                success_msg = f"✅ Added {total_songs} songs from **{playlist_title}** (Spotify)"
                success_msg += f"\n🎵 Songs will be converted during playback"
            else:
                success_msg = f"✅ Added {total_songs} songs from **{playlist_title}**"
            
            if (playlist_info or {}).get('owner'):
                success_msg += f" by {(playlist_info or {}).get('owner')}"
            
            await status_msg.edit(content=success_msg)
            asyncio.create_task(self.delete_after_delay(status_msg, 8))
            
            # Start processing
            asyncio.create_task(self.process_queue(guild_id, voice_client))
            asyncio.create_task(self._check_and_start_playback(voice_client, guild_id))
            
        except Exception as e:
            logging.exception("Error handling playlist: %s", e)
            traceback.print_exc()
            try:
                await status_msg.edit(content="❌ Playlist processing failed!")
                asyncio.create_task(self.delete_after_delay(status_msg, 5))
            except:
                pass

    async def process_queue(self, guild_id: int, voice_client):
        """⚡ FIXED queue processing - STRICT FIFO ORDER"""
        timer_key = self.perf_monitor.start_timer("process_queue")
        
        queue = None
        try:
            queue = self.get_queue(guild_id)
            
            logging.debug("[QUEUE] Processing queue for guild %s", guild_id)
            logging.debug("[QUEUE] Queue size: %d requests", len(queue.queue))
            logging.debug("[QUEUE] Processed size: %d songs", len(queue.processed_queue))
            logging.debug("[QUEUE] Currently processing: %s", queue.processing)
            
            if queue.processing:
                logging.debug("[QUEUE] Already processing, skipping")
                return
            
            queue.processing = True
            logging.debug("[QUEUE] Started processing")
            
            try:
                while queue.queue:
                    request = queue.queue.popleft()
                    await self._process_song_request(request, guild_id)
                    await asyncio.sleep(0.1)  # Small delay between processing
                    
            finally:
                queue.processing = False
                logging.debug("[QUEUE] Finished processing")
        
        except Exception as e:
            logging.exception("[QUEUE] Error processing queue: %s", e)
            traceback.print_exc()
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
            request_order = request.get('order', 'unknown')
            
            logging.debug("Processing song request: %s (order: %s)", query[:50], request_order)
            
            # ✅ Handle pre-loaded song data (from playlists)
            if song_data:
                # ✅ Check if this is a Spotify song that needs conversion
                if song_data.get('needs_conversion') and song_data.get('conversion_query'):
                    logging.debug("Converting Spotify song on-demand: %s", song_data['title'][:50])
                    
                    # Import here to avoid circular imports
                    from utils.sources.spotify import spotify_handler
                    
                    # Convert using the pre-built query
                    conversion_query = song_data['conversion_query']
                    youtube_song = await spotify_handler.search_youtube_for_track(song_data['spotify_info'])
                    
                    if youtube_song:
                        logging.debug("Converted: %s", youtube_song.get('title', 'Unknown')[:50])
                        queue = self.get_queue(guild_id)
                        queue.add_processed_song(youtube_song)
                        # Update controller to reflect new Up Next
                        guild = self.bot.get_guild(guild_id)
                        vc = guild.voice_client if guild else None
                        status = "playing" if vc and (vc.is_playing() or vc.is_paused()) else "waiting"
                        await self.update_controller_embed(guild_id, queue.current, status)
                    else:
                        logging.debug("Conversion failed for: %s", song_data['title'][:50])
                        # Still add the original data as fallback
                        queue = self.get_queue(guild_id)
                        queue.add_processed_song(song_data)
                        guild = self.bot.get_guild(guild_id)
                        vc = guild.voice_client if guild else None
                        status = "playing" if vc and (vc.is_playing() or vc.is_paused()) else "waiting"
                        await self.update_controller_embed(guild_id, queue.current, status)
                else:
                    # Regular pre-loaded song
                    queue = self.get_queue(guild_id)
                    queue.add_processed_song(song_data)
                    logging.debug("Added pre-loaded song: %s", song_data.get('title', 'Unknown')[:50])
                    guild = self.bot.get_guild(guild_id)
                    vc = guild.voice_client if guild else None
                    status = "playing" if vc and (vc.is_playing() or vc.is_paused()) else "waiting"
                    await self.update_controller_embed(guild_id, queue.current, status)
                return
            
            # ✅ Regular search processing
            song_result = await asyncio.wait_for(
                search_song(query), 
                timeout=10.0
            )
            
            if song_result:
                queue = self.get_queue(guild_id)
                queue.add_processed_song(song_result)
                logging.debug("Added searched song: %s", song_result.get('title', 'Unknown')[:50])
                guild = self.bot.get_guild(guild_id)
                vc = guild.voice_client if guild else None
                status = "playing" if vc and (vc.is_playing() or vc.is_paused()) else "waiting"
                await self.update_controller_embed(guild_id, queue.current, status)
            else:
                logging.debug("No result for: %s", query)

        except asyncio.TimeoutError:
            logging.debug("Song processing timeout: %s", request.get('query', ''))
        except Exception as e:
            logging.debug("Error processing song: %s", e)

    async def _check_and_start_playback(self, voice_client, guild_id: int):
        """Quick playback checker - SINGLE attempt only"""
        await asyncio.sleep(0.5)
        
        # Only check ONCE
        if voice_client.is_playing() or voice_client.is_paused():
            logging.debug("Already playing/paused, skipping playback check")
            return
        
        # Check if songs are ready
        queue = self.queue_manager.get_queue(guild_id)
        if queue.has_songs():
            logging.debug("Songs ready immediately, starting playback")
            await self.playback_manager.start_playback(voice_client, guild_id)
            return
        
        # Wait briefly for processing to complete
        for i in range(10):  # 5 seconds max
            await asyncio.sleep(0.5)
            if queue.has_songs():
                logging.debug("Songs ready after %.1fs, starting playback", i*0.5)
                await self.playback_manager.start_playback(voice_client, guild_id)
                return
        
        logging.debug("No songs ready after 5s")

    async def _ensure_voice_connection(self, message):
        """Ensure voice connection with auto-delete errors and retry logic"""
        # Check existing connection
        if message.guild.voice_client:
            return message.guild.voice_client
        
        # Validate user voice state
        if not message.author.voice or not message.author.voice.channel:
            error_msg = await message.channel.send("❌ You need to be in a voice channel!")
            asyncio.create_task(self.delete_after_delay(error_msg, 3))
            return None
        
        # Check permissions
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
        
        # Robust connection with retries
        for attempt in range(3):
            try:
                voice_client = await asyncio.wait_for(channel.connect(), timeout=15.0)
                logging.debug("Connected to %s", channel.name)
                return voice_client
            except Exception as e:
                error_str = str(e)
                logging.debug("Voice connection error (attempt %d/3): %s", attempt+1, error_str)
                if "4006" in error_str or "Session invalidated" in error_str:
                    wait_time = 2 + attempt * 3
                    logging.debug("Discord voice session invalidated (4006). Retrying in %ds…", wait_time)
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
            logging.debug("Error updating controller: %s", e)

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

    async def handle_rewind(self, interaction):
        await self.button_handlers.handle_rewind(interaction)

    async def handle_forward(self, interaction):
        await self.button_handlers.handle_forward(interaction)

    async def handle_volume(self, interaction):
        await self.button_handlers.handle_volume(interaction)

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
        
        # ✅ FIXED: Minimum 2 seconds between updates to prevent rate limiting
        if current_time - last_update < 2.0:
            await asyncio.sleep(2.0 - (current_time - last_update))
        
        # Check if we're being rate limited
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

# ✅ ADD THE REQUIRED SETUP FUNCTION
async def setup(bot):
    """Setup function required by discord.py"""
    try:
        cog = MusicCog(bot)
        await bot.add_cog(cog)
        logging.info("MusicCog setup complete: %s", cog)
    except Exception as e:
        logging.error("Error setting up MusicCog: %s", e)
        traceback.print_exc()
        raise