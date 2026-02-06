import asyncio
import discord
import time  # ✅ Make sure this is imported
import logging
import traceback
from typing import Optional, Dict, Any
from utils.sources.youtube import YTDLSource, youtube_handler
from utils.history_manager import history_manager

class PlaybackManager:
    """Handles all playback logic"""

    def __init__(self, music_cog, queue_manager):
        self.music_cog = music_cog
        self.queue_manager = queue_manager
        self._seeking_guilds = set()
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

            # Defer checking for mismatched/stuck players until we've determined
            # what the next song to play will be. This avoids referencing
            # variables before they are set.

            queue = self.queue_manager.get_queue(guild_id)

            next_song = queue.current if queue.current else queue.get_next()
            if not next_song:
                await self.music_cog.controller_manager.update_controller_embed(guild_id, None, "waiting")
                return False

            # On-demand conversion for Spotify tracks
            if next_song.get('needs_conversion'):
                logging.info(f"🎵 Converting Spotify track: {next_song.get('title')}")
                query = next_song.get('conversion_query')
                if query and youtube_handler:
                    yt_song_data = await youtube_handler.search(query)
                    if yt_song_data:
                        # Preserve original requester and add Spotify info
                        yt_song_data['requested_by'] = next_song.get('requested_by')
                        yt_song_data['spotify_info'] = next_song.get('spotify_info')
                        next_song = yt_song_data
                        queue.update_current_song(next_song) # Update the song in the queue
                    else:
                        logging.error(f"Failed to convert Spotify track: {next_song.get('title')}")
                        # Skip to the next song if conversion fails
                        return await self.start_playback(voice_client, guild_id)

            logging.info("Playing: %s", next_song.get('title', 'Unknown'))

            # If voice client is currently playing something different from
            # the next song we want to play, force-stop and try to cleanup
            # the lingering source/process so the new player can start
            try:
                if voice_client.is_playing():
                    current_src = getattr(voice_client, 'source', None)
                    queued_title = next_song.get('title') if next_song else None
                    current_title = getattr(current_src, 'title', None)
                    if current_src and queued_title and current_title and current_title != queued_title:
                        logging.warning(f"Detected playing source mismatch (playing: {current_title!r}, queued: {queued_title!r}) — forcing stop and cleanup")
                        try:
                            voice_client.stop()
                        except Exception:
                            pass
                        try:
                            cleanup_fn = getattr(current_src, 'cleanup', None)
                            if callable(cleanup_fn):
                                cleanup_fn()
                        except Exception:
                            logging.exception("Error cleaning up lingering source")
                        await asyncio.sleep(0.35)

            except Exception:
                logging.exception("Error while checking/cleaning current voice source")

            song_url = next_song.get('webpage_url')
            player = None

            for attempt in range(3):
                try:
                    if player:
                        break
                    
                    player = await YTDLSource.from_url(
                        song_url,
                        volume_percent=queue.volume
                    )

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
                await asyncio.sleep(1)  # Add a small delay
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

        for i in range(20):
            if queue.has_songs():
                await self.start_playback(voice_client, guild_id)
                return
            await asyncio.sleep(0.5)

        await self.music_cog.controller_manager.update_controller_embed(guild_id, None, "waiting")

    

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
        self._manual_operations.discard(guild_id)
        self._playback_positions.pop(guild_id, None)
        self._song_start_times.pop(guild_id, None)


