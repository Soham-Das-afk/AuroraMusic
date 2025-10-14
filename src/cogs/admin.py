import discord  # type: ignore
from discord.ext import commands  # type: ignore
from discord import app_commands  # type: ignore
import json
import os
import traceback
from pathlib import Path
import time
import logging
from .music.controller import ControllerManager
from typing import Any, cast
from config.settings import Config

# Help type checker: treat discord as Any to avoid attr-not-found noise while keeping runtime intact
discord = cast(Any, discord)

# Controller data storage
CONTROLLER_DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'controller_data.json')

def load_controller_data():
    """Load controller data from JSON file"""
    try:
        if os.path.exists(CONTROLLER_DATA_FILE):
            with open(CONTROLLER_DATA_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logging.error("Error loading controller data: %s", e)
    return {}

def save_controller_data(data):
    """Save controller data to JSON file"""
    try:
        os.makedirs(os.path.dirname(CONTROLLER_DATA_FILE), exist_ok=True)
        with open(CONTROLLER_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error("Error saving controller data: %s", e)

class MusicControlView(discord.ui.View):  # type: ignore[attr-defined]
    def __init__(self):
        super().__init__(timeout=None)
        logging.debug("MusicControlView initialized")

    @discord.ui.button(emoji='⏮️', label='Previous', style=discord.ButtonStyle.secondary, custom_id='music_previous', row=0)  # type: ignore[attr-defined]
    async def previous(self, interaction: Any, button: Any):
        logging.debug("Previous button clicked by %s", interaction.user)
        try:
            music_cog = interaction.client.get_cog('MusicCog')
            if music_cog and hasattr(music_cog, 'handle_previous'):
                await music_cog.handle_previous(interaction)
            else:
                await interaction.response.send_message("❌ Music system not available!", ephemeral=True)
        except Exception as e:
            logging.debug("Exception in previous button: %s", e)
            traceback.print_exc()
            try:
                await interaction.response.send_message("❌ Previous failed!", ephemeral=True)
            except Exception as e2:
                logging.debug("Failed to send error message: %s", e2)

    @discord.ui.button(emoji='⏯️', label='Play/Pause', style=discord.ButtonStyle.primary, custom_id='music_play_pause', row=0)  # type: ignore[attr-defined]
    async def play_pause(self, interaction: Any, button: Any):
        logging.debug("Play/Pause button clicked by %s", interaction.user)
        try:
            music_cog = interaction.client.get_cog('MusicCog')
            if music_cog and hasattr(music_cog, 'handle_play_pause'):
                # Update label based on current state
                vc = interaction.guild.voice_client if interaction.guild else None
                if vc and vc.is_playing():
                    button.label = 'Pause'
                    button.emoji = '⏸️'
                elif vc and vc.is_paused():
                    button.label = 'Resume'
                    button.emoji = '▶️'
                else:
                    button.label = 'Play'
                    button.emoji = '▶️'
                await music_cog.handle_play_pause(interaction)
            else:
                await interaction.response.send_message("❌ Music system not available!", ephemeral=True)
        except Exception as e:
            logging.debug("Exception in play_pause button: %s", e)
            traceback.print_exc()
            try:
                await interaction.response.send_message("❌ Play/Pause failed!", ephemeral=True)
            except Exception as e2:
                logging.debug("Failed to send error message: %s", e2)

    @discord.ui.button(emoji='⏭️', label='Skip', style=discord.ButtonStyle.secondary, custom_id='music_skip', row=0)  # type: ignore[attr-defined]
    async def skip(self, interaction: Any, button: Any):
        logging.debug("Skip button triggered")
        try:
            music_cog = interaction.client.get_cog('MusicCog')
            if music_cog and hasattr(music_cog, 'handle_skip'):
                await music_cog.handle_skip(interaction)
            else:
                await interaction.response.send_message("❌ Music system not available!", ephemeral=True)
        except Exception as e:
            logging.debug("Exception in skip button: %s", e)
            traceback.print_exc()

    @discord.ui.button(emoji='⏹️', label='Stop', style=discord.ButtonStyle.danger, custom_id='music_stop', row=0)  # type: ignore[attr-defined]
    async def stop(self, interaction: Any, button: Any):
        logging.debug("Stop button clicked by %s", interaction.user)
        try:
            music_cog = interaction.client.get_cog('MusicCog')
            if music_cog and hasattr(music_cog, 'handle_stop'):
                await music_cog.handle_stop(interaction)
            else:
                await interaction.response.send_message("❌ Music system not available!", ephemeral=True)
        except Exception as e:
            logging.debug("Exception in stop button: %s", e)
            traceback.print_exc()
            try:
                await interaction.response.send_message("❌ Stop failed!", ephemeral=True)
            except Exception as e2:
                logging.debug("Failed to send error message: %s", e2)

    @discord.ui.button(emoji='⏪', label='Rewind 10s', style=discord.ButtonStyle.primary, custom_id='music_rewind', row=1)  # type: ignore[attr-defined]
    async def rewind(self, interaction: Any, button: Any):
        try:
            music_cog = interaction.client.get_cog('MusicCog')
            if music_cog and hasattr(music_cog, 'handle_rewind'):
                await music_cog.handle_rewind(interaction)
            else:
                await interaction.response.send_message("❌ Music system not available!", ephemeral=True)
        except Exception as e:
            logging.debug("Exception in rewind button: %s", e)
            traceback.print_exc()

    @discord.ui.button(emoji='⏩', label='Forward 10s', style=discord.ButtonStyle.primary, custom_id='music_forward', row=1)  # type: ignore[attr-defined]
    async def forward(self, interaction: Any, button: Any):
        try:
            music_cog = interaction.client.get_cog('MusicCog')
            if music_cog and hasattr(music_cog, 'handle_forward'):
                await music_cog.handle_forward(interaction)
            else:
                await interaction.response.send_message("❌ Music system not available!", ephemeral=True)
        except Exception as e:
            logging.debug("Exception in forward button: %s", e)
            traceback.print_exc()

    @discord.ui.button(emoji='🔊', label='Volume', style=discord.ButtonStyle.secondary, custom_id='music_volume', row=1)  # type: ignore[attr-defined]
    async def volume(self, interaction: Any, button: Any):
        try:
            music_cog = interaction.client.get_cog('MusicCog')
            if music_cog and hasattr(music_cog, 'handle_volume'):
                await music_cog.handle_volume(interaction)
            else:
                await interaction.response.send_message("❌ Music system not available!", ephemeral=True)
        except Exception as e:
            logging.debug("Exception in volume button: %s", e)
            traceback.print_exc()

    @discord.ui.button(emoji='🔁', label='Loop', style=discord.ButtonStyle.secondary, custom_id='music_loop', row=2)  # type: ignore[attr-defined]
    async def loop_mode(self, interaction: Any, button: Any):
        try:
            music_cog = interaction.client.get_cog('MusicCog')
            if music_cog and hasattr(music_cog, 'handle_loop'):
                await music_cog.handle_loop(interaction)
            else:
                await interaction.response.send_message("❌ Music system not available!", ephemeral=True)
        except Exception as e:
            logging.debug("Exception in loop button: %s", e)
            traceback.print_exc()

    @discord.ui.button(emoji='🔀', label='Shuffle', style=discord.ButtonStyle.secondary, custom_id='music_shuffle', row=2)  # type: ignore[attr-defined]
    async def shuffle(self, interaction: Any, button: Any):
        try:
            music_cog = interaction.client.get_cog('MusicCog')
            if music_cog and hasattr(music_cog, 'handle_shuffle'):
                await music_cog.handle_shuffle(interaction)
            else:
                await interaction.response.send_message("❌ Music system not available!", ephemeral=True)
        except Exception as e:
            logging.debug("Exception in shuffle button: %s", e)
            traceback.print_exc()

    @discord.ui.button(emoji='🔄', label='AutoPlay', style=discord.ButtonStyle.secondary, custom_id='music_autoplay', row=2)  # type: ignore[attr-defined]
    async def autoplay(self, interaction: Any, button: Any):
        logging.debug("AutoPlay button clicked by %s", interaction.user)
        await interaction.response.send_message("🔄 AutoPlay feature coming soon!", ephemeral=True)

    def create_controller_embed(self, song_data, status, queue):
        """Create controller embed with cleaned design (banner, thumbnail, organized fields)"""
        try:
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
                        embed.add_field(name="⏭️ Next Song", value=next_title, inline=True)
                    elif queue.queue:
                        embed.add_field(name="⏭️ Processing", value="Loading songs...", inline=True)
                    else:
                        embed.add_field(name="⏭️ Next Song", value="Nothing queued", inline=True)
                else:
                    embed.add_field(name="📋 Queue", value="Empty", inline=True)
                    embed.add_field(name="⏭️ Next Song", value="Nothing queued", inline=True)
                embed.add_field(name="🔊 Volume", value=f"{queue.volume}%", inline=True)
                loop_status = "Loop On" if queue.loop_mode else "Loop Off"
                embed.add_field(name="Loop Mode", value=loop_status, inline=True)
            return embed
        except Exception as e:
            logging.error("Error creating embed: %s", e)
            return discord.Embed(  # type: ignore[attr-defined]
                title="🎵 AuroraMusic Controller",
                description="""
**Controller Active**

Something went wrong creating the detailed view,
but the controller is still working!

Try sending a song name or link to continue.
                """,
                color=0x7289da
            )
    
    def format_duration(self, seconds):
        """Format duration in MM:SS format"""
        try:
            if not seconds or seconds <= 0:
                return "Unknown"
            minutes = int(seconds // 60)
            seconds = int(seconds % 60)
            return f"{minutes}:{seconds:02d}"
        except:
            return "Unknown"

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.controller_data = load_controller_data()
        logging.debug("AdminCog initialized")

    async def cog_load(self):
        logging.debug("AdminCog loaded - Adding persistent view")
        view = MusicControlView()
        self.bot.add_view(view)
        logging.debug("Added %s to bot.persistent_views", type(view).__name__)

    

    @app_commands.command(name="setup", description="Set up the music bot with a dedicated channel")
    @app_commands.describe(
        channel_name="Name for the music channel (default: 'aurora-music')",
        category="Category to create the channel in"
    )
    async def setup_slash(self, interaction: discord.Interaction, channel_name: str = "aurora-music", category: discord.CategoryChannel = None): # type: ignore
        await interaction.response.defer()
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ You need administrator permissions!", ephemeral=True)
            return
        guild_id_str = str(interaction.guild.id)
        if guild_id_str in self.controller_data:
            await interaction.followup.send("❌ Music controller already exists! Use `/cleanup` first.", ephemeral=True)
            return
        try:
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(send_messages=True, read_messages=True),  # type: ignore[attr-defined]
                interaction.guild.me: discord.PermissionOverwrite(send_messages=True, read_messages=True, manage_messages=True)  # type: ignore[attr-defined]
            }
            channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic="🎵 AuroraMusic Controller • Send songs here to play them!"
            )
            # Use ControllerManager for banner and controller embeds for consistency
            manager = ControllerManager(interaction.client.get_cog('MusicCog'))
            bot_banner_url = await manager._get_banner_url()

            banner_embed = discord.Embed(title="🎵 Welcome to AuroraMusic!")  # type: ignore[attr-defined]
            banner_embed.set_footer(text="Developed by @sick._.duck.103 on Discord")
            # Show banner image only if enabled and URL present
            if getattr(Config, 'SHOW_BANNER', True) and bot_banner_url:
                banner_embed.set_image(url=bot_banner_url)
            banner_msg = await channel.send(embed=banner_embed)
            # Build the same controller embed used during live updates
            # Fake a minimal queue-like object for initial state
            class _InitialQueue:
                volume = 100
                loop_mode = False
                def total_items(self):
                    return 0
                processed_queue = []
                queue = []
            controller_embed = manager.create_controller_embed(
                song_data=None,
                status="waiting",
                queue=_InitialQueue(),
                bot_banner_url=bot_banner_url
            )
            # Do not set any image on the controller embed (controller-only content)
            view = MusicControlView()
            controller_msg = await channel.send(embed=controller_embed, view=view)
            self.controller_data[guild_id_str] = {
                "channel_id": channel.id,
                "banner_message_id": banner_msg.id,
                "message_id": controller_msg.id,
                "channel_name": channel_name
            }
            save_controller_data(self.controller_data)
            success_embed = discord.Embed(  # type: ignore[attr-defined]
                title="✅ Setup Complete!",
                description=f"Music controller created in {channel.mention}",
                color=0x00ff00
            )
            success_embed.add_field(
                name="🎵 How to use",
                value="Go to the music channel and send songs!",
                inline=False
            )
            await interaction.followup.send(embed=success_embed)
        except Exception as e:
            logging.error("Setup error: %s", e)
            traceback.print_exc()
            await interaction.followup.send(f"❌ Setup failed: {str(e)}", ephemeral=True)

    @app_commands.command(name="ping", description="Check if the bot is responsive")
    async def ping_slash(self, interaction: discord.Interaction): # type: ignore
        """Test slash command"""
        latency = round(interaction.client.latency * 1000)
        embed = discord.Embed(  # type: ignore[attr-defined]
            title="🏓 Pong!",
            description=f"Bot latency: {latency}ms",
            color=0x00ff00
        )
        embed.add_field(name="🤖 Status", value="Online & Ready", inline=True)
        embed.add_field(name="🎵 Music System", value="Available", inline=True)
        try:
            from config.settings import Config as _Cfg
            ver = getattr(_Cfg, 'VERSION', '3.2.37')
        except Exception:
            ver = '3.2.37'
        embed.add_field(name="🔧 Version", value=f"AuroraMusic v{ver}", inline=True)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="cleanup", description="Remove the music controller and clear saved data")
    @app_commands.describe(delete_channel="Also delete the controller channel (default: true)")
    async def cleanup_slash(self, interaction: discord.Interaction, delete_channel: bool = True):  # type: ignore
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ You need administrator permissions!", ephemeral=True)
            return

        guild_id_str = str(interaction.guild.id)
        data = self.controller_data
        if guild_id_str not in data:
            await interaction.followup.send("ℹ️ No controller found for this server.", ephemeral=True)
            return

        entry = data[guild_id_str]
        channel_id = entry.get("channel_id")
        controller_msg_id = entry.get("message_id")
        banner_msg_id = entry.get("banner_message_id")
        channel = interaction.guild.get_channel(channel_id) if channel_id else None

        deleted_any = False
        errors = []

        try:
            if channel:
                # Try delete controller message
                if controller_msg_id:
                    try:
                        msg = await channel.fetch_message(controller_msg_id)
                        await msg.delete()
                        deleted_any = True
                    except Exception as e:
                        errors.append(f"controller message: {e}")
                # Try delete banner message
                if banner_msg_id:
                    try:
                        msg = await channel.fetch_message(banner_msg_id)
                        await msg.delete()
                        deleted_any = True
                    except Exception as e:
                        errors.append(f"banner message: {e}")

                # Optionally delete channel
                if delete_channel:
                    try:
                        await channel.delete(reason="AuroraMusic cleanup requested")
                        deleted_any = True
                    except Exception as e:
                        errors.append(f"channel delete: {e}")
        finally:
            # Remove saved entry regardless of deletion success
            self.controller_data.pop(guild_id_str, None)
            save_controller_data(self.controller_data)

        if errors:
            await interaction.followup.send(
                f"✅ Cleanup done with some issues: {', '.join(errors)}",
                ephemeral=True
            )
        else:
            if deleted_any:
                await interaction.followup.send("🧹 Cleanup complete!", ephemeral=True)
            else:
                await interaction.followup.send("ℹ️ Nothing to delete, but data was cleared.", ephemeral=True)

    @app_commands.command(name="health", description="Show bot configuration and server status")
    async def health_slash(self, interaction: discord.Interaction):  # type: ignore
        from config.settings import Config
        await interaction.response.defer(ephemeral=True)

        # Config checks
        allowed = Config.is_guild_allowed(interaction.guild.id)
        cookies_path = Config.get_cookies_path()
        has_spotify = bool(Config.SPOTIFY_CLIENT_ID and Config.SPOTIFY_CLIENT_SECRET)

        # Queue info
        queue_summary = "N/A"
        music_cog = interaction.client.get_cog('MusicCog')
        if music_cog and hasattr(music_cog, 'get_queue'):
            try:
                queue = music_cog.get_queue(interaction.guild.id)
                info = queue.get_queue_info()
                queue_summary = (
                    f"current={'yes' if info['current'] else 'no'}, "
                    f"processed={info['queue_size']}, pending={info['processing_size']}, "
                    f"history={info['history_size']}, loop={'on' if info['loop_mode'] else 'off'}, "
                    f"volume={info['volume']}%"
                )
            except Exception as e:
                queue_summary = f"error: {e}"

        embed = discord.Embed(title="🩺 AuroraMusic Health", color=0x00aaee)  # type: ignore[attr-defined]
        embed.add_field(name="Allowed Guild", value="✅ Yes" if allowed else "❌ No", inline=True)
        embed.add_field(name="Cookies", value=f"✅ {cookies_path}" if cookies_path else "⚠️ None", inline=True)
        embed.add_field(name="Spotify", value="✅ Enabled" if has_spotify else "⚠️ Disabled", inline=True)
        embed.add_field(name="Queue", value=queue_summary, inline=False)

        # Controller presence
        data = self.controller_data
        entry = data.get(str(interaction.guild.id))
        if entry:
            embed.add_field(
                name="Controller",
                value=f"channel_id={entry.get('channel_id')}, message_id={entry.get('message_id')}",
                inline=False
            )
        else:
            embed.add_field(name="Controller", value="Not set up", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="help", description="Show AuroraMusic usage and commands")
    async def help_slash(self, interaction: discord.Interaction):  # type: ignore
        await interaction.response.defer(ephemeral=True)
        # Determine controller channel for this guild
        controller_hint = "Use `/setup` to create a music controller channel."
        try:
            entry = self.controller_data.get(str(interaction.guild.id))
            if entry and entry.get("channel_id"):
                channel = interaction.guild.get_channel(entry["channel_id"])  # type: ignore[index]
                if channel:
                    controller_hint = f"Your controller channel: {channel.mention}"
                else:
                    controller_hint = f"Controller channel: <#{entry['channel_id']}>"
        except Exception:
            pass

        description = (
            f"{controller_hint}\n\n"
            "In the controller channel:\n"
            "• Send a song name or link (YouTube/Spotify)\n"
            "• Use the buttons to play/pause, skip, loop, volume, etc.\n\n"
            "Useful commands:\n"
            "• `/ping` — bot latency and status\n"
            "• `/health` — configuration and queue summary\n"
            "• `/cleanup` — remove controller (admin only)\n"
        )

        # Add permission warning if bot can't manage messages in the controller channel
        try:
            entry = self.controller_data.get(str(interaction.guild.id))
            warn_text = None
            if entry and entry.get("channel_id"):
                ch = interaction.guild.get_channel(entry["channel_id"])  # type: ignore[index]
                me = interaction.guild.me  # type: ignore[assignment]
                if ch and me and not ch.permissions_for(me).manage_messages:
                    warn_text = "⚠️ Missing 'Manage Messages' in controller channel — auto-cleanup may fail."
            if warn_text:
                description += f"\n{warn_text}"
        except Exception:
            pass

        embed = discord.Embed(title="🎵 AuroraMusic Help", description=description, color=0x7289da)  # type: ignore[attr-defined]
        await interaction.followup.send(embed=embed, ephemeral=True)

# ✅ REQUIRED: Add setup function
async def setup(bot):
    """Setup function for the admin cog"""
    try:
        cog = AdminCog(bot)
        await bot.add_cog(cog)
        logging.info("AdminCog setup complete: %s", cog)
    except Exception as e:
        logging.error("Error setting up AdminCog: %s", e)
        traceback.print_exc()
        raise
