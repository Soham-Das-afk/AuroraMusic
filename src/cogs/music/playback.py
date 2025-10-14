import asyncio
import discord
import time  # ✅ Make sure this is imported
import traceback
from typing import Optional, Dict, Any
from utils.sources.youtube import YTDLSource

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
        
        # ✅ ADD: Missing performance metrics
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
                print("❌ No voice connection")
                return False
            
            # Check if already playing
            if voice_client.is_playing():
                print("🔍 Already playing/paused, skipping start_playback")
                return True
            
            queue = self.queue_manager.get_queue(guild_id)
            
            # Get next song
            next_song = queue.get_next()
            if not next_song:
                print("📭 No songs to play")
                await self.music_cog.controller_manager.update_controller_embed(guild_id, None, "waiting")
                return False
            
            print(f"🎵 Playing: {next_song.get('title', 'Unknown')}")
            
            # ✅ Reuse cached player when available
            song_url = next_song.get('webpage_url')
            player = None
            if song_url and song_url in queue.cache:
                cached = queue.cache.get(song_url)
                if cached:
                    player = cached
                    print("✅ Using cached player for next song")
            
            for attempt in range(3):
                try:
                    if player:
                        break
                    print(f"🔄 Creating player (attempt {attempt + 1}/3)")
                    player = await YTDLSource.from_url(song_url, volume_percent=queue.volume)
                    
                    if player:
                        print(f"✅ Player created successfully on attempt {attempt + 1}")
                        break
                    else:
                        print(f"❌ Player creation failed on attempt {attempt + 1}")
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    print(f"❌ Player creation error (attempt {attempt + 1}): {e}")
                    if attempt < 2:
                        await asyncio.sleep(2)
            
            # ✅ FIXED: Add proper handling after the loop
            if not player:
                print(f"❌ Failed to create player after 3 attempts")
                # Mark song as failed and try next
                next_song['failed'] = True
                queue.add_to_history(next_song)
                await asyncio.sleep(1)
                return await self.start_playback(voice_client, guild_id)  # Try next song
            
            # ✅ Start playback with better error handling
            try:
                def _after(error):
                    try:
                        fut = asyncio.run_coroutine_threadsafe(
                            self.song_finished(error, guild_id),
                            self.music_cog.bot.loop
                        )
                        # Do not block the audio thread; add a done callback to surface errors in logs
                        fut.add_done_callback(lambda f: f.exception())
                    except Exception:
                        pass

                voice_client.play(
                    player,
                    after=_after
                )
                
                # ✅ Wait a moment to verify playback started
                await asyncio.sleep(0.5)
                
                if voice_client.is_playing():
                    print(f"✅ Playback started successfully")
                    self._song_start_times[guild_id] = time.time()
                    await self.music_cog.controller_manager.update_controller_embed(guild_id, next_song, "playing")
                    return True
                else:
                    print(f"❌ Playback failed to start")
                    # Try next song
                    return await self.start_playback(voice_client, guild_id)
                    
            except Exception as play_error:
                print(f"❌ Playback start error: {play_error}")
                return False
        
        except Exception as e:
            print(f"❌ Error in start_playback: {e}")
            traceback.print_exc()
            return False
    
    async def song_finished(self, error, guild_id: int):
        """Enhanced song finished handler with better queue management"""
        try:
            # ✅ ADD: Validate guild_id
            if guild_id is None:
                print(f"❌ song_finished called with None guild_id, error: {error}")
                return
                
            print(f"✅ Song finished in guild {guild_id}")
            
            if error:
                print(f"❌ Playback error: {error}")
                self.performance_metrics['playback_errors'] += 1
            else:
                self.performance_metrics['successful_plays'] += 1
            
            # ✅ ADD: Validate guild exists
            guild = self.music_cog.bot.get_guild(guild_id)
            if not guild:
                print(f"❌ Guild {guild_id} not found")
                return
                
            queue = self.queue_manager.get_queue(guild_id)
            voice_client = guild.voice_client
            
            if not voice_client:
                print(f"❌ No voice client for guild {guild_id}")
                return
            
            # ✅ CRITICAL FIX: Check if this was a manual operation (skip/stop)
            if guild_id in self._manual_operations:
                print(f"🔍 Manual operation in progress, handling appropriately")
                
                # Add current song to history before removing
                if queue.current:
                    print(f"📝 Manually added to history: {queue.current.get('title', 'Unknown')}")
                    queue.history.append(queue.current)
                    queue.current = None
                
                # ✅ FIXED: Clear manual operation flag FIRST
                self._manual_operations.discard(guild_id)
                
                # ✅ CRITICAL: Check for next song and auto-advance
                if queue.has_songs():
                    print(f"🔄 Manual skip completed, advancing to next song")
                    await asyncio.sleep(0.5)  # Brief pause
                    await self.start_playback(voice_client, guild_id)
                    return
                else:
                    print(f"🔄 Manual operation completed, no more songs")
                    await self.music_cog.update_controller_embed(guild_id, None, "waiting")
                    return
            
            # ✅ Natural song end (not manual skip)
            print(f"🎵 Natural song completion")
            
            # Add to history if current song exists
            if queue.current:
                if queue.current not in queue.history:  # Avoid duplicates
                    queue.history.append(queue.current)
                    print(f"📝 Added to history: {queue.current.get('title', 'Unknown')}")
                else:
                    print(f"📝 Song already in history, skipping: {queue.current.get('title', 'Unknown')}")
            
            # Check loop mode
            current_song = queue.current
            queue.current = None
            
            if queue.loop_mode and current_song:
                print(f"🔁 Loop mode: Replaying {current_song.get('title', 'Unknown')}")
                queue.processed_queue.appendleft(current_song)
            
            # ✅ ALWAYS try to advance to next song
            if queue.has_songs():
                print(f"🎵 Advancing to next song in queue")
                await asyncio.sleep(0.5)  # Brief pause
                await self.start_playback(voice_client, guild_id)
            else:
                print(f"✅ Queue empty - showing waiting state")
                await self.music_cog.update_controller_embed(guild_id, None, "waiting")
        
        except Exception as e:
            print(f"❌ Error in song_finished: {e}")
            import traceback
            traceback.print_exc()
            
            # Cleanup on error
            self._manual_operations.discard(guild_id)
            try:
                await self.music_cog.update_controller_embed(guild_id, None, "waiting")
            except:
                pass
    
    async def start_playback_when_ready(self, voice_client, guild_id: int):
        """Wait for songs to be ready, then start playback"""
        queue = self.queue_manager.get_queue(guild_id)
        
        # Wait up to 10 seconds for songs to be ready
        for i in range(20):  # 10 seconds
            if queue.has_songs():
                print(f"🚀 Songs ready after {i*0.5:.1f}s, starting playback")
                await self.start_playback(voice_client, guild_id)
                return
            await asyncio.sleep(0.5)
        
        print("⏰ No songs ready after 10s")
        await self.music_cog.controller_manager.update_controller_embed(guild_id, None, "waiting")
    
    async def _background_cache_task(self, guild_id: int):
        """Enhanced background task to cache next songs - handles dynamic additions"""
        if guild_id in self._caching_guilds:
            print("🔄 Cache task already running for this guild")
            return
        
        self._caching_guilds.add(guild_id)
        
        try:
            queue = self.queue_manager.get_queue(guild_id)
            
            # ✅ ENHANCED: Cache more songs when there are many in queue
            total_songs = len(queue.processed_queue)
            if total_songs > 10:
                cache_count = 5  # Cache next 5 songs for large queues
            elif total_songs > 5:
                cache_count = 3  # Cache next 3 songs for medium queues
            else:
                cache_count = 2  # Cache next 2 songs for small queues
            
            songs_to_cache = list(queue.processed_queue)[:cache_count]
            
            if not songs_to_cache:
                print("📭 No additional songs to pre-cache")
                return
            
            print(f"📭 Next songs available: {total_songs}")
            print(f"🔄 Starting background cache ({cache_count} songs, song playing successfully)")
            
            # Get the lock to prevent conflicts
            async with self.queue_manager.get_lock(guild_id):
                print(f"🔒 Cache lock acquired for guild {guild_id}")
                
                cached_count = 0
                for i, song in enumerate(songs_to_cache, 1):
                    song_url = song.get('webpage_url')
                    if song_url and song_url not in queue.cache:
                        try:
                            print(f"🔄 Caching song {i}/{cache_count}: {song.get('title', 'Unknown')[:50]}")
                            
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
                                print(f"✅ Cached ({cached_count}/{cache_count}): {song.get('title', 'Unknown')[:50]}")
                                
                                # ✅ Small delay between caching to prevent overwhelming
                                if i < len(songs_to_cache):
                                    await asyncio.sleep(0.5)
                            else:
                                print(f"❌ Failed to cache: {song.get('title', 'Unknown')[:50]}")
                        
                        except asyncio.TimeoutError:
                            print(f"⏰ Cache timeout: {song.get('title', 'Unknown')[:50]}")
                        except Exception as e:
                            print(f"❌ Cache error: {e}")
                    else:
                        if song_url in queue.cache:
                            print(f"✅ Song {i} already cached: {song.get('title', 'Unknown')[:50]}")
                        else:
                            print(f"⚠️ No URL for song {i}: {song.get('title', 'Unknown')[:50]}")
                
                print(f"✅ Cache batch completed: {cached_count}/{cache_count} songs cached")
                
                # ✅ ENHANCED: Continue caching if there are more songs and we successfully cached current batch
                remaining_songs = len(queue.processed_queue) - cache_count
                if remaining_songs > 0 and cached_count > 0:
                    print(f"🔄 {remaining_songs} more songs available for future caching")
                    
                    # Schedule next caching batch after current song finishes
                    asyncio.create_task(self._schedule_next_cache_batch(guild_id, 30.0))  # Cache more in 30 seconds
            
            print(f"🔓 Cache lock released for guild {guild_id}")
        
        except Exception as e:
            print(f"❌ Background cache error: {e}")
            traceback.print_exc()
        finally:
            self._caching_guilds.discard(guild_id)

    async def _schedule_next_cache_batch(self, guild_id: int, delay: float):
        """Schedule next caching batch after delay"""
        await asyncio.sleep(delay)
        
        # Check if still playing and more songs need caching
        guild = self.music_cog.bot.get_guild(guild_id)
        if not guild or not guild.voice_client or not guild.voice_client.is_playing():
            print(f"🔄 Not playing anymore, skipping scheduled cache for guild {guild_id}")
            return
        
        queue = self.queue_manager.get_queue(guild_id)
        uncached_songs = []
        
        for song in list(queue.processed_queue)[5:10]:  # Check songs 6-10
            if song.get('webpage_url') not in queue.cache:
                uncached_songs.append(song)
        
        if uncached_songs and guild_id not in self._caching_guilds:
            print(f"🔄 Scheduled cache batch starting for {len(uncached_songs)} songs")
            asyncio.create_task(self._background_cache_task(guild_id))
        else:
            print(f"🔄 No additional caching needed for guild {guild_id}")
    
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
            
            # Stop current playback
            voice_client.stop()
            await asyncio.sleep(0.3)
            
            # Create new player with start time
            song_url = queue.current.get('webpage_url')
            player = await YTDLSource.from_url(
                song_url,
                loop=self.music_cog.bot.loop,
                volume_percent=queue.volume,
                start_time=position
            )
            
            if player:
                # Start playback from new position
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
                
                # Update position tracking
                self._song_start_times[guild_id] = time.time() - position
                self._playback_positions[guild_id] = position
                
                return True
            
            return False
        
        except Exception as e:
            print(f"❌ Seek error: {e}")
            return False
        finally:
            # Remove from seeking set after a delay
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