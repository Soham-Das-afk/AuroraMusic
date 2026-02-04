import discord
import asyncio
import time
import logging
from typing import Optional
from utils.sources.youtube import YTDLSource

class VolumeModal(discord.ui.Modal, title='Set Volume'):
    """Modal for volume input with validation"""

    def __init__(self, music_cog):
        super().__init__()
        self.music_cog = music_cog

    volume = discord.ui.TextInput(
        label='Volume (10-200%)',
        placeholder='Enter volume percentage...',
        default='100',
        max_length=3,
        min_length=2
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            volume_value = int(self.volume.value)
            if not 10 <= volume_value <= 200:
                return

            if not interaction.guild:
                return

            queue = self.music_cog.get_queue(interaction.guild.id)
            old_volume = queue.volume
            queue.set_volume(volume_value)

            await self.music_cog.update_controller_embed(
                interaction.guild.id, queue.current,
                "playing" if getattr(interaction.guild, 'voice_client', None) and getattr(interaction.guild.voice_client, 'is_playing', lambda: False)() else "waiting"
            )

            return

        except ValueError:
            return
        except Exception as e:
            logging.error(f"Error in volume modal: {e}")
            return


class ButtonHandlers:
    """Enhanced button handlers with rate limiting and error recovery"""

    def __init__(self, music_cog, queue_manager):
        self.music_cog = music_cog
        self.queue_manager = queue_manager
        self._button_cooldowns = {}
        self._error_counts = {}

    def _check_cooldown(self, user_id: int, button_type: str) -> bool:
        """Check if user is on cooldown for button"""
        key = f"{user_id}:{button_type}"
        current_time = time.time()

        if key in self._button_cooldowns:
            if current_time - self._button_cooldowns[key] < 1.0:  # 1 second cooldown
                return False

        self._button_cooldowns[key] = current_time
        return True

    def _record_error(self, button_type: str):
        """Record button error for monitoring"""
        self._error_counts[button_type] = self._error_counts.get(button_type, 0) + 1
        if self._error_counts[button_type] > 10:
            logging.warning(f"High error count for {button_type}: {self._error_counts[button_type]}")

    async def handle_play_pause(self, interaction):
        """Enhanced play/pause with state validation"""
        if not self._check_cooldown(interaction.user.id, "play_pause"):
            return

        try:
            await interaction.response.defer(ephemeral=True)
            voice_client = interaction.guild.voice_client

            if not voice_client:
                return

            queue = self.queue_manager.get_queue(interaction.guild.id)

            if voice_client.is_playing():
                voice_client.pause()
                await self.music_cog.update_controller_embed(interaction.guild.id, queue.current, "paused")

            elif voice_client.is_paused():
                voice_client.resume()
                await self.music_cog.update_controller_embed(interaction.guild.id, queue.current, "playing")

            else:
                if queue.has_songs():
                    await self.music_cog.playback_manager.start_playback(voice_client, interaction.guild.id)
                else:
                    return

            return

        except Exception as e:
            self._record_error("play_pause")
            logging.error(f"Play/Pause error: {e}")
            return

    async def handle_skip(self, interaction):
        """Enhanced skip with queue validation"""
        if not self._check_cooldown(interaction.user.id, "skip"):
            return

        try:
            await interaction.response.defer(ephemeral=True)
            voice_client = interaction.guild.voice_client

            if not voice_client or not (voice_client.is_playing() or voice_client.is_paused()):
                return

            queue = self.queue_manager.get_queue(interaction.guild.id)
            current_title = queue.current.get('title', 'Unknown') if queue.current else 'Unknown'

            # acquire guild lock to avoid race conditions when skipping
            async with self.queue_manager.get_lock(interaction.guild.id):
                self.music_cog.playback_manager._manual_operations.add(interaction.guild.id)
                # only stop if actually playing/paused to avoid unnecessary callbacks
                if getattr(voice_client, 'is_playing', lambda: False)() or getattr(voice_client, 'is_paused', lambda: False)():
                    try:
                        voice_client.stop()
                    except Exception:
                        pass

            await asyncio.sleep(0.8)  # Allow time for ffmpeg process to terminate

            # Defensive: if FFmpeg/voice source didn't terminate, try to
            # cleanup the lingering source so the next song can start.
            try:
                if getattr(voice_client, 'is_playing', lambda: False)():
                    current_src = getattr(voice_client, 'source', None)
                    if current_src:
                        try:
                            cleanup_fn = getattr(current_src, 'cleanup', None)
                            if callable(cleanup_fn):
                                cleanup_fn()
                        except Exception:
                            logging.exception("Error cleaning up source after skip")
                    # final attempt to stop
                    try:
                        voice_client.stop()
                    except Exception:
                        pass
                    await asyncio.sleep(0.25)
            except Exception:
                pass

            return

        except Exception as e:
            self._record_error("skip")
            logging.error(f"Skip error: {e}")
            self.music_cog.playback_manager._manual_operations.discard(interaction.guild.id)
            return

    async def handle_stop(self, interaction):
        """Enhanced stop with cleanup"""
        if not self._check_cooldown(interaction.user.id, "stop"):
            return

        try:
            await interaction.response.defer(ephemeral=True)
            voice_client = interaction.guild.voice_client

            if not voice_client:
                return

            queue = self.queue_manager.get_queue(interaction.guild.id)

            voice_client.stop()
            queue.clear()

            await asyncio.sleep(0.5)
            await self.music_cog.update_controller_embed(interaction.guild.id, None, "waiting")
            return

        except Exception as e:
            self._record_error("stop")
            logging.error(f"Stop error: {e}")
            try:
                await self.music_cog.update_controller_embed(interaction.guild.id, None, "waiting")
            except:
                pass
            return

    async def handle_previous(self, interaction):
        """✅ FIXED: Previous button implementation with proper state management"""
        if not self._check_cooldown(interaction.user.id, "previous"):
            return

        try:
            await interaction.response.defer(ephemeral=True)
            guild_id = interaction.guild.id
            voice_client = interaction.guild.voice_client

            if not voice_client or not voice_client.is_connected():
                return

            queue = self.queue_manager.get_queue(guild_id)

            if not queue.history:
                return

            self.music_cog.playback_manager._manual_operations.add(guild_id)

            async with self.queue_manager.get_lock(guild_id):
                if queue.current:
                    queue.processed_queue.appendleft(queue.current)

                previous_song = queue.get_previous()

                if not previous_song:
                    if queue.processed_queue and queue.processed_queue[0] == queue.current:
                        queue.current = queue.processed_queue.popleft()
                    self.music_cog.playback_manager._manual_operations.discard(guild_id)
                    return

                voice_client.stop()
                await asyncio.sleep(0.5)

                await self.music_cog.playback_manager.start_playback(voice_client, guild_id)

            return

        except Exception as e:
            self._record_error("previous")
            logging.error(f"Previous error: {e}")
            if interaction.guild:
                self.music_cog.playback_manager._manual_operations.discard(interaction.guild.id)
            return

    async def handle_shuffle(self, interaction):
        """Enhanced shuffle with feedback"""
        try:
            await interaction.response.defer(ephemeral=True)
            queue = self.queue_manager.get_queue(interaction.guild.id)

            if not queue.has_songs():
                return

            songs_count = len(queue.processed_queue)
            queue.shuffle()

            return

        except Exception as e:
            self._record_error("shuffle")
            logging.error(f"Shuffle error: {e}")
            return

    async def handle_volume(self, interaction):
        """Enhanced volume with modal"""
        try:
            await interaction.response.send_modal(VolumeModal(self.music_cog))

        except Exception as e:
            self._record_error("volume")
            logging.error(f"Volume error: {e}")
            return

    async def handle_loop(self, interaction):
        """Enhanced loop with state display"""
        try:
            await interaction.response.defer(ephemeral=True)
            queue = self.queue_manager.get_queue(interaction.guild.id)

            queue.loop_mode = not queue.loop_mode
            status = "🔁 enabled" if queue.loop_mode else "🔁 disabled"

            await self.music_cog.update_controller_embed(
                interaction.guild.id, queue.current,
                "playing" if interaction.guild.voice_client and
                interaction.guild.voice_client.is_playing() else "waiting"
            )

            return

        except Exception as e:
            self._record_error("loop")
            logging.error(f"Loop error: {e}")
            return

    async def handle_rewind(self, interaction):
        """Enhanced rewind with position tracking"""
        try:
            await interaction.response.defer(ephemeral=True)
            voice_client = interaction.guild.voice_client

            if not voice_client or not voice_client.is_connected():
                return

            queue = self.queue_manager.get_queue(interaction.guild.id)
            if not queue.current:
                return

            current_pos = self.music_cog.playback_manager.get_current_position(interaction.guild.id)
            new_position = max(0, current_pos - 10)

            success = await self.music_cog.playback_manager.seek_to_position(
                interaction.guild.id, voice_client, new_position
            )

            await asyncio.sleep(0.1)
            return

        except Exception as e:
            self._record_error("rewind")
            logging.error(f"Rewind error: {e}")
            return

    async def handle_forward(self, interaction):
        """Enhanced forward with duration checking"""
        try:
            await interaction.response.defer(ephemeral=True)
            voice_client = interaction.guild.voice_client

            if not voice_client or not voice_client.is_connected():
                return

            queue = self.queue_manager.get_queue(interaction.guild.id)
            if not queue.current:
                return

            current_pos = self.music_cog.playback_manager.get_current_position(interaction.guild.id)
            new_position = current_pos + 10

            duration = queue.current.get('duration')
            if duration and new_position >= duration - 5:  # 5 second buffer
                voice_client.stop()
                return
            else:
                success = await self.music_cog.playback_manager.seek_to_position(
                    interaction.guild.id, voice_client, new_position
                )
                await asyncio.sleep(0.1)
                return

        except Exception as e:
            self._record_error("forward")
            logging.error(f"Forward error: {e}")
            return

    async def _auto_delete_message(self, message, delay=3):
        """Enhanced auto-delete with better error handling"""
        async def delete_task():
            try:
                await asyncio.sleep(delay)
                if message:
                    await message.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                logging.warning("No permission to delete button response")
            except Exception as e:
                logging.error(f"Error auto-deleting button response: {e}")

        asyncio.create_task(delete_task())
