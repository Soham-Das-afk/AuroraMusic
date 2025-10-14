import discord
import asyncio
import traceback
import time
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
                await interaction.response.send_message(
                    "❌ Volume must be between 10-200%", ephemeral=True
                )
                return
            
            queue = self.music_cog.get_queue(interaction.guild.id)
            old_volume = queue.volume
            queue.set_volume(volume_value)
            
            # Update controller
            await self.music_cog.update_controller_embed(
                interaction.guild.id, queue.current, 
                "playing" if interaction.guild.voice_client and 
                interaction.guild.voice_client.is_playing() else "waiting"
            )
            
            await interaction.response.send_message(
                f"🔊 Volume changed: {old_volume}% → {volume_value}%", 
                ephemeral=True
            )
            
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid number (10-200)", ephemeral=True
            )
        except Exception as e:
            print(f"❌ Error in volume modal: {e}")
            await interaction.response.send_message(
                "❌ Volume change failed", ephemeral=True
            )

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
            print(f"⚠️ High error count for {button_type}: {self._error_counts[button_type]}")
    
    async def handle_play_pause(self, interaction):
        """Enhanced play/pause with state validation"""
        if not self._check_cooldown(interaction.user.id, "play_pause"):
            await interaction.response.send_message("⏳ Please wait before using this button again", ephemeral=True)
            return
        
        try:
            await interaction.response.defer(ephemeral=True)
            voice_client = interaction.guild.voice_client
            
            if not voice_client:
                msg = await interaction.followup.send("❌ Not connected to voice!", ephemeral=True)
                await self._auto_delete_message(msg, 3)
                return
            
            queue = self.queue_manager.get_queue(interaction.guild.id)
            
            if voice_client.is_playing():
                voice_client.pause()
                await self.music_cog.update_controller_embed(interaction.guild.id, queue.current, "paused")
                msg = await interaction.followup.send("⏸️ Paused!", ephemeral=True)
                
            elif voice_client.is_paused():
                voice_client.resume()
                await self.music_cog.update_controller_embed(interaction.guild.id, queue.current, "playing")
                msg = await interaction.followup.send("▶️ Resumed!", ephemeral=True)
                
            else:
                if queue.has_songs():
                    await self.music_cog.playback_manager.start_playback(voice_client, interaction.guild.id)
                    msg = await interaction.followup.send("▶️ Playback started!", ephemeral=True)
                else:
                    msg = await interaction.followup.send("❌ No songs in queue!", ephemeral=True)
            
            await self._auto_delete_message(msg, 3)
                
        except Exception as e:
            self._record_error("play_pause")
            print(f"❌ Play/Pause error: {e}")
            try:
                msg = await interaction.followup.send("❌ Play/Pause failed!", ephemeral=True)
                await self._auto_delete_message(msg, 3)
            except:
                pass
    
    async def handle_skip(self, interaction):
        """Enhanced skip with queue validation"""
        if not self._check_cooldown(interaction.user.id, "skip"):
            await interaction.response.send_message("⏳ Please wait before skipping again", ephemeral=True)
            return
        
        try:
            await interaction.response.defer(ephemeral=True)
            voice_client = interaction.guild.voice_client
            
            if not voice_client or not (voice_client.is_playing() or voice_client.is_paused()):
                await interaction.followup.send("❌ Nothing is playing!", ephemeral=True)
                return
            
            queue = self.queue_manager.get_queue(interaction.guild.id)
            current_title = queue.current.get('title', 'Unknown') if queue.current else 'Unknown'
            
            # ✅ CRITICAL: Mark as manual operation BEFORE stopping
            print(f"🔍 [SKIP DEBUG] Marking guild {interaction.guild.id} as manual operation")
            self.music_cog.playback_manager._manual_operations.add(interaction.guild.id)
            
            # ✅ Stop playback (this triggers song_finished)
            voice_client.stop()
            
            await interaction.followup.send(f"⏭️ Skipped: {current_title}", ephemeral=True)
            
        except Exception as e:
            self._record_error("skip")
            print(f"❌ Skip error: {e}")
            # ✅ Clear manual flag on error
            self.music_cog.playback_manager._manual_operations.discard(interaction.guild.id)
            try:
                await interaction.followup.send("❌ Skip failed!", ephemeral=True)
            except:
                pass
    
    async def handle_stop(self, interaction):
        """Enhanced stop with cleanup"""
        if not self._check_cooldown(interaction.user.id, "stop"):
            await interaction.response.send_message("⏳ Please wait before using stop again", ephemeral=True)
            return
        
        try:
            await interaction.response.defer(ephemeral=True)
            voice_client = interaction.guild.voice_client
            
            if not voice_client:
                await interaction.followup.send("❌ Not connected to voice!", ephemeral=True)
                return
            
            queue = self.queue_manager.get_queue(interaction.guild.id)
            
            # Stop and clear
            voice_client.stop()
            queue.clear()
            
            # Cleanup cache
            queue.cache.clear()
            
            # Update controller
            await asyncio.sleep(0.5)
            await self.music_cog.update_controller_embed(interaction.guild.id, None, "waiting")
            
            msg = await interaction.followup.send("⏹️ Stopped and cleared everything!", ephemeral=True)
            await self._auto_delete_message(msg, 3)
                
        except Exception as e:
            self._record_error("stop")
            print(f"❌ Stop error: {e}")
            try:
                await self.music_cog.update_controller_embed(interaction.guild.id, None, "waiting")
                msg = await interaction.followup.send("❌ Stop failed!", ephemeral=True)
                await self._auto_delete_message(msg, 3)
            except:
                pass
    
    async def handle_previous(self, interaction):
        """✅ FIXED: Previous button implementation with proper state management"""
        if not self._check_cooldown(interaction.user.id, "previous"):
            await interaction.response.send_message("⏳ Please wait before using previous", ephemeral=True)
            return
        
        try:
            await interaction.response.defer(ephemeral=True)
            voice_client = interaction.guild.voice_client
            
            if not voice_client or not voice_client.is_connected():
                await interaction.followup.send("❌ Not connected to voice!", ephemeral=True)
                return
            
            queue = self.queue_manager.get_queue(interaction.guild.id)
            
            if not queue.history:
                await interaction.followup.send("❌ No previous song available!", ephemeral=True)
                return
            
            print(f"🔍 [PREVIOUS DEBUG] History size: {len(queue.history)}")
            print(f"🔍 [PREVIOUS DEBUG] Current song: {queue.current.get('title', 'None') if queue.current else 'None'}")
            
            # ✅ CRITICAL FIX: Mark as manual operation to prevent auto-advance conflicts
            self.music_cog.playback_manager._manual_operations.add(interaction.guild.id)
            
            async with self.queue_manager.get_lock(interaction.guild.id):
                # Get the previous song
                previous_song = queue.get_previous()  # This handles the queue manipulation correctly
                
                if not previous_song:
                    await interaction.followup.send("❌ No previous song available!", ephemeral=True)
                    return
                
                print(f"⏮️ Previous song retrieved: {previous_song.get('title', 'Unknown')}")
                
                # ✅ FIXED: Stop current playback and wait
                voice_client.stop()
                await asyncio.sleep(1.0)  # Longer wait for complete stop
                
                # ✅ FIXED: Clear the manual operation flag after stop completes
                await asyncio.sleep(0.5)
                self.music_cog.playback_manager._manual_operations.discard(interaction.guild.id)
                
                # ✅ Use playback manager to start the previous song
                success = await self.music_cog.playback_manager.start_playback(voice_client, interaction.guild.id)
                
                if success:
                    msg = await interaction.followup.send(
                        f"⏮️ Playing previous: {previous_song.get('title', 'Unknown')[:50]}", 
                        ephemeral=True
                    )
                else:
                    msg = await interaction.followup.send("❌ Failed to start previous song!", ephemeral=True)
                
                await self._auto_delete_message(msg, 3)
    
        except Exception as e:
            self._record_error("previous")
            print(f"❌ Previous error: {e}")
            import traceback
            traceback.print_exc()
            # Clear manual operation flag on error
            self.music_cog.playback_manager._manual_operations.discard(interaction.guild.id)
            try:
                await interaction.followup.send("❌ Previous failed!", ephemeral=True)
            except:
                pass
    
    async def handle_shuffle(self, interaction):
        """Enhanced shuffle with feedback"""
        try:
            await interaction.response.defer(ephemeral=True)
            queue = self.queue_manager.get_queue(interaction.guild.id)
            
            if not queue.has_songs():
                await interaction.followup.send("❌ No songs to shuffle!", ephemeral=True)
                return
            
            songs_count = len(queue.processed_queue)
            queue.shuffle()
            
            msg = await interaction.followup.send(f"🔀 Shuffled {songs_count} songs!", ephemeral=True)
            await self._auto_delete_message(msg, 3)
                
        except Exception as e:
            self._record_error("shuffle")
            print(f"❌ Shuffle error: {e}")
            try:
                await interaction.followup.send("❌ Shuffle failed!", ephemeral=True)
            except:
                pass
    
    async def handle_volume(self, interaction):
        """Enhanced volume with modal"""
        try:
            await interaction.response.send_modal(VolumeModal(self.music_cog))
            
        except Exception as e:
            self._record_error("volume")
            print(f"❌ Volume error: {e}")
            try:
                await interaction.response.send_message("❌ Volume control failed!", ephemeral=True)
            except:
                pass
    
    async def handle_loop(self, interaction):
        """Enhanced loop with state display"""
        try:
            await interaction.response.defer(ephemeral=True)
            queue = self.queue_manager.get_queue(interaction.guild.id)
            
            queue.loop_mode = not queue.loop_mode
            # ✅ FIXED: Keep the 🔁 symbol in the button response
            status = "🔁 enabled" if queue.loop_mode else "🔁 disabled"
            
            # Update controller to reflect loop status
            await self.music_cog.update_controller_embed(
                interaction.guild.id, queue.current,
                "playing" if interaction.guild.voice_client and 
                interaction.guild.voice_client.is_playing() else "waiting"
            )
            
            msg = await interaction.followup.send(f"Loop mode {status}!", ephemeral=True)
            await self._auto_delete_message(msg, 3)
            
        except Exception as e:
            self._record_error("loop")
            print(f"❌ Loop error: {e}")
            try:
                await interaction.followup.send("❌ Loop toggle failed!", ephemeral=True)
            except:
                pass
    
    async def handle_rewind(self, interaction):
        """Enhanced rewind with position tracking"""
        try:
            await interaction.response.defer(ephemeral=True)
            voice_client = interaction.guild.voice_client
            
            if not voice_client or not voice_client.is_connected():
                await interaction.followup.send("❌ Not connected to voice!", ephemeral=True)
                return
            
            queue = self.queue_manager.get_queue(interaction.guild.id)
            if not queue.current:
                await interaction.followup.send("❌ No song is playing!", ephemeral=True)
                return
            
            current_pos = self.music_cog.playback_manager.get_current_position(interaction.guild.id)
            new_position = max(0, current_pos - 10)
            
            success = await self.music_cog.playback_manager.seek_to_position(
                interaction.guild.id, voice_client, new_position
            )
            
            if success:
                msg = await interaction.followup.send("⏪ Rewound 10 seconds!", ephemeral=True)
            else:
                msg = await interaction.followup.send("❌ Rewind failed!", ephemeral=True)
            
            await self._auto_delete_message(msg, 3)
                
        except Exception as e:
            self._record_error("rewind")
            print(f"❌ Rewind error: {e}")
            try:
                await interaction.followup.send("❌ Rewind failed!", ephemeral=True)
            except:
                pass
    
    async def handle_forward(self, interaction):
        """Enhanced forward with duration checking"""
        try:
            await interaction.response.defer(ephemeral=True)
            voice_client = interaction.guild.voice_client
            
            if not voice_client or not voice_client.is_connected():
                await interaction.followup.send("❌ Not connected to voice!", ephemeral=True)
                return
            
            queue = self.queue_manager.get_queue(interaction.guild.id)
            if not queue.current:
                await interaction.followup.send("❌ No song is playing!", ephemeral=True)
                return
            
            current_pos = self.music_cog.playback_manager.get_current_position(interaction.guild.id)
            new_position = current_pos + 10
            
            # Check duration
            duration = queue.current.get('duration')
            if duration and new_position >= duration - 5:  # 5 second buffer
                voice_client.stop()
                msg = await interaction.followup.send("⏭️ Near end, skipping to next!", ephemeral=True)
            else:
                success = await self.music_cog.playback_manager.seek_to_position(
                    interaction.guild.id, voice_client, new_position
                )
                if success:
                    msg = await interaction.followup.send("⏩ Forwarded 10 seconds!", ephemeral=True)
                else:
                    msg = await interaction.followup.send("❌ Forward failed!", ephemeral=True)
            
            await self._auto_delete_message(msg, 3)
                
        except Exception as e:
            self._record_error("forward")
            print(f"❌ Forward error: {e}")
            try:
                await interaction.followup.send("❌ Forward failed!", ephemeral=True)
            except:
                pass
    
    async def _auto_delete_message(self, message, delay=3):
        """Enhanced auto-delete with better error handling"""
        async def delete_task():
            try:
                await asyncio.sleep(delay)
                if message:
                    await message.delete()
                    print(f"✅ Auto-deleted button response after {delay}s")
            except discord.NotFound:
                print("⚠️ Button response already deleted")
            except discord.Forbidden:
                print("⚠️ No permission to delete button response")
            except Exception as e:
                print(f"⚠️ Error auto-deleting button response: {e}")
        
        asyncio.create_task(delete_task())