import asyncio
import discord
import time  # ✅ Make sure this is imported
import logging
import traceback
from typing import Optional, Dict, Any
from utils.sources.youtube import YTDLSource
from utils.history_manager import history_manager

class PlaybackManager:
    """Handles all playback logic"""
    
    def __init__(self, music_cog, queue_manager):
        self.music_cog = music_cog
        self.queue_manager = queue_manager
        self._seeking_guilds = set()
        self._caching_guilds = set()
        self._manual_operations = set()  # Track manual skip/previous operations
        self._playback_positions = {}  # Track song positions
        self._song_start_times = {}   # Track when songs started
        
        self.performance_metrics = {
            'playback_errors': 0,
            'successful_plays': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
    
    async def start_playback(self, voice_client, guild_id: int):
        """Start playing with better error handling"""
        try:
            if not voice_client or not voice_client.is_connected():
                return False
            
            if voice_client.is_playing():
                return True
            
            queue = self.queue_manager.get_queue(guild_id)

            next_song = queue.current if queue.current else queue.get_next()
            if not next_song:
                await self.music_cog.controller_manager.update_controller_embed(guild_id, None, "waiting")
                return False
            
            logging.info("Playing: %s", next_song.get('title', 'Unknown'))
            
            song_url = next_song.get('webpage_url')
            player = None
            if song_url and song_url in queue.cache:
                cached = queue.cache.get(song_url)
                if cached:
                    player = cached
            
            for attempt in range(3):
                try:
                    if player:
                        break
                    prefer_file = bool(getattr(queue, 'prefer_file_once', False))
                    player = await YTDLSource.from_url(
                        song_url,
                        volume_percent=queue.volume,
                        prefer_file=prefer_file,
                        download_if_missing=not prefer_file
                    )
                    if getattr(queue, 'prefer_file_once', False):
                        queue.prefer_file_once = False
                    
                    if player:
                        break
                    else:
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    if attempt < 2:
                        await asyncio.sleep(2)
            
            if not player:
                logging.error("Failed to create player after 3 attempts")
                next_song['failed'] = True
                queue.add_to_history(next_song)
                await asyncio.sleep(1)
                return await self.start_playback(voice_client, guild_id)  # Try next song
            
            try:
                def _after(error):
                    try:
                        fut = asyncio.run_coroutine_threadsafe(
                            self.song_finished(error, guild_id),
                            self.music_cog.bot.loop
                        )
                        fut.add_done_callback(lambda f: f.exception())
                    except Exception:
                        pass

                voice_client.play(
                    player,
                    after=_after
                )
                
                await asyncio.sleep(0.5)
                
                if voice_client.is_playing():
                    self._song_start_times[guild_id] = time.time()
                    await self.music_cog.controller_manager.update_controller_embed(guild_id, next_song, "playing")
                    return True
                else:
                    return await self.start_playback(voice_client, guild_id)
                    
            except Exception as play_error:
                return False
        
        except Exception as e:
            logging.exception("Error in start_playback: %s", e)
            logging.exception('Exception traceback')
            return False
    
    async def song_finished(self, error, guild_id: int):
        """Enhanced song finished handler with better queue management"""
        try:
            if guild_id is None:
                return
                
            
            if error:
                self.performance_metrics['playback_errors'] += 1
            else:
                self.performance_metrics['successful_plays'] += 1
            
            guild = self.music_cog.bot.get_guild(guild_id)
            if not guild:
                return
                
            queue = self.queue_manager.get_queue(guild_id)
            voice_client = guild.voice_client
            
            if not voice_client:
                return
            
            if guild_id in self._manual_operations:
                
                if queue.current:
                    queue.history.append(queue.current)
                    queue.current = None
                
                self._manual_operations.discard(guild_id)
                
                if queue.has_songs():
                    await asyncio.sleep(0.5)  # Brief pause
                    await self.start_playback(voice_client, guild_id)
                    return
                else:
                    await self.music_cog.update_controller_embed(guild_id, None, "waiting")
                    return
            
            
            if queue.current:
                if queue.current not in queue.history:  # Avoid duplicates
                    user_id = queue.current.get("requested_by")
                    if user_id:
                        await history_manager.add_to_history(guild_id, user_id, queue.current)
                    
                    queue.history.append(queue.current)
                else:
                    pass
            
            current_song = queue.current
            queue.current = None
            
            if queue.loop_mode and current_song:
                queue.processed_queue.appendleft(current_song)
            
            if queue.has_songs():
                await asyncio.sleep(0.5)  # Brief pause
                await self.start_playback(voice_client, guild_id)
            else:
                await self.music_cog.update_controller_embed(guild_id, None, "waiting")
        
        except Exception as e:
            logging.exception("Error in song_finished: %s", e)
            import traceback
            logging.exception('Exception traceback')
            
            self._manual_operations.discard(guild_id)
            try:
                await self.music_cog.update_controller_embed(guild_id, None, "waiting")
            except:
                pass
    
    async def start_playback_when_ready(self, voice_client, guild_id: int):
        """Wait for songs to be ready, then start playback"""
        queue = self.queue_manager.get_queue(guild_id)
        
        for i in range(20):  # 10 seconds
            if queue.has_songs():
                await self.start_playback(voice_client, guild_id)
                return
            await asyncio.sleep(0.5)
        
        await self.music_cog.controller_manager.update_controller_embed(guild_id, None, "waiting")
    
    async def _background_cache_task(self, guild_id: int):
        """Enhanced background task to cache next songs - handles dynamic additions"""
        if guild_id in self._caching_guilds:
            return
        
        self._caching_guilds.add(guild_id)
        
        try:
            queue = self.queue_manager.get_queue(guild_id)
            
            cache_count = 5
            
            songs_to_cache = list(queue.processed_queue)[:cache_count]
            
            if not songs_to_cache:
                return
            
            total_songs = len(queue.processed_queue)
            
            async with self.queue_manager.get_lock(guild_id):
                
                cached_count = 0
                for i, song in enumerate(songs_to_cache, 1):
                    song_url = song.get('webpage_url')
                    if song_url and song_url not in queue.cache:
                        try:
                            
                            player = await asyncio.wait_for(
                                YTDLSource.from_url(
                                    song_url,
                                    loop=self.music_cog.bot.loop,
                                    volume_percent=queue.volume
                                ),
                                timeout=25.0  # Slightly longer timeout
                            )
                            
                            if player:
                                queue.cache[song_url] = player
                                cached_count += 1
                                
                                if i < len(songs_to_cache):
                                    await asyncio.sleep(0.5)
                            else:
                                pass
                        
                        except asyncio.TimeoutError:
                            pass
                        except Exception as e:
                            logging.error(f"Exception: {e}")
                    else:
                        if song_url in queue.cache:
                            pass
                        else:
                            pass
                
                
                remaining_songs = len(queue.processed_queue) - cache_count
                if remaining_songs > 0 and cached_count > 0:
                    
                    asyncio.create_task(self._schedule_next_cache_batch(guild_id, 30.0))  # Cache more in 30 seconds
            
        
        except Exception as e:
            logging.exception("Background cache error: %s", e)
            logging.exception('Exception traceback')
        finally:
            self._caching_guilds.discard(guild_id)

    async def _schedule_next_cache_batch(self, guild_id: int, delay: float):
        """Schedule next caching batch after delay"""
        await asyncio.sleep(delay)
        
        guild = self.music_cog.bot.get_guild(guild_id)
        if not guild or not guild.voice_client or not guild.voice_client.is_playing():
            return
        
        queue = self.queue_manager.get_queue(guild_id)
        uncached_songs = []
        
        for song in list(queue.processed_queue)[5:10]:  # Check songs 6-10
            if song.get('webpage_url') not in queue.cache:
                uncached_songs.append(song)
        
        if uncached_songs and guild_id not in self._caching_guilds:
            asyncio.create_task(self._background_cache_task(guild_id))
        else:
            pass
    
    def get_current_position(self, guild_id: int) -> int:
        """Get current playback position in seconds"""
        if guild_id in self._song_start_times:
            return int(time.time() - self._song_start_times[guild_id])
        return 0
    
    async def seek_to_position(self, guild_id: int, voice_client, position: int) -> bool:
        """Seek to a specific position in the current song"""
        try:
            self._seeking_guilds.add(guild_id)
            
            queue = self.queue_manager.get_queue(guild_id)
            if not queue.current:
                return False
            
            voice_client.stop()
            await asyncio.sleep(0.3)
            
            song_url = queue.current.get('webpage_url')
            player = await YTDLSource.from_url(
                song_url,
                loop=self.music_cog.bot.loop,
                volume_percent=queue.volume,
                start_time=position
            )
            
            if player:
                def _after_seek(error):
                    try:
                        fut = asyncio.run_coroutine_threadsafe(
                            self.song_finished(error, guild_id),
                            self.music_cog.bot.loop
                        )
                        fut.add_done_callback(lambda f: f.exception())
                    except Exception:
                        pass

                voice_client.play(
                    player,
                    after=_after_seek
                )
                
                self._song_start_times[guild_id] = time.time() - position
                self._playback_positions[guild_id] = position
                
                return True
            
            return False
        
        except Exception as e:
            return False
        finally:
            await asyncio.sleep(1)
            self._seeking_guilds.discard(guild_id)
    
    def cleanup_guild(self, guild_id: int):
        """Cleanup guild-specific data"""
        self._seeking_guilds.discard(guild_id)
        self._caching_guilds.discard(guild_id)
        self._manual_operations.discard(guild_id)
        self._playback_positions.pop(guild_id, None)
        self._song_start_times.pop(guild_id, None)
    
    def get_cache_status(self, guild_id: int) -> dict:
        """Get detailed cache status for monitoring"""
        queue = self.queue_manager.get_queue(guild_id)
        
        total_songs = len(queue.processed_queue)
        cached_songs = 0
        next_10_songs = list(queue.processed_queue)[:10]
        
        cache_details = []
        for i, song in enumerate(next_10_songs, 1):
            is_cached = song.get('webpage_url') in queue.cache
            if is_cached:
                cached_songs += 1
            
            cache_details.append({
                'position': i,
                'title': song.get('title', 'Unknown')[:30],
                'cached': is_cached
            })
        
        cache_coverage = (cached_songs / min(10, total_songs)) * 100 if total_songs > 0 else 0
        
        return {
            'total_songs_in_queue': total_songs,
            'cached_in_next_10': cached_songs,
            'cache_coverage_percent': round(cache_coverage, 1),
            'currently_caching': guild_id in self._caching_guilds,
            'cache_details': cache_details
        }
