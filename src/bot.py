import discord  # type: ignore
from discord.ext import commands  # type: ignore
from discord.utils import get  # type: ignore
import asyncio
import sys
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from config.settings import Config
from utils.file_manager import FileManager

class SafeConsoleFilter(logging.Filter):
    """Sanitize log records for consoles that can't render emojis/UTF-8."""
    def __init__(self, encoding: str | None = None):
        super().__init__()
        self.encoding = encoding or getattr(sys.stdout, 'encoding', None) or 'cp1252'

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        try:
            # If the console can't encode it strictly, replace problematic chars
            msg.encode(self.encoding, errors='strict')
        except Exception:
            try:
                safe = msg.encode(self.encoding, errors='replace').decode(self.encoding, errors='replace')
                record.msg = safe
                record.args = ()
            except Exception:
                # As a last resort, strip non-ASCII
                record.msg = ''.join(ch if ord(ch) < 128 else '?' for ch in msg)
                record.args = ()
        return True

# Set up logging with UTF-8 file and safe console output
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

file_handler = logging.FileHandler('bot.log', encoding='utf-8')
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.addFilter(SafeConsoleFilter())

root_logger.handlers.clear()
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

class AuroraMusicBot(commands.Bot):
    """Main bot class for AuroraMusic"""

    def __init__(self, intents):
        # Use a dummy prefix since we rely on slash commands and controller messages only
        super().__init__(command_prefix=commands.when_mentioned_or('!'), intents=intents, help_command=None)

    async def setup_hook(self):
        """Load cogs on startup"""
        cogs_to_load = [
            'cogs.music.music_cog',
            'cogs.admin'
        ]
        for cog in cogs_to_load:
            try:
                await self.load_extension(cog)
                logging.info(f"✅ Loaded cog: {cog}")
            except Exception as e:
                logging.error(f"❌ Failed to load cog {cog}: {e}")

        # Sync slash commands for faster availability
        try:
            if getattr(Config, 'ALLOWED_GUILD_IDS', []):
                # Guild-specific sync for faster updates
                for gid in Config.ALLOWED_GUILD_IDS:
                    try:
                        if not self.get_guild(gid):
                            logging.info(f"Skipping command sync for guild {gid} (bot not in guild)")
                            continue
                        await self.tree.sync(guild=discord.Object(id=gid))  # type: ignore[attr-defined]
                        logging.info(f"✅ Synced app commands for guild {gid}")
                    except Exception as guild_sync_err:
                        logging.error(f"❌ Failed to sync commands for guild {gid}: {guild_sync_err}")
            else:
                # Global sync
                await self.tree.sync()
                logging.info("✅ Synced app commands globally")
        except Exception as sync_err:
            logging.error(f"❌ Failed to sync app commands: {sync_err}")

    async def on_ready(self):
        """Bot ready event"""
        logging.info(f"🎵 {self.user} is now online!")
        logging.info(f"📡 Connected to {len(self.guilds)} servers")
        logging.info(f"👥 Serving {len(set(self.get_all_members()))} users")

        # Helpful: print an invite URL with applications.commands scope (for slash commands)
        try:
            app_info = await self.application_info()
            client_id = app_info.id if hasattr(app_info, 'id') else None
            if client_id:
                # scopes: bot + applications.commands; permissions minimal (send messages, manage messages, connect, speak)
                perms = 0
                # Send Messages (2048) | Manage Messages (8192) | Connect (1048576) | Speak (2097152)
                perms |= 2048 | 8192 | 1048576 | 2097152
                invite = (
                    f"https://discord.com/api/oauth2/authorize?client_id={client_id}"
                    f"&permissions={perms}&scope=bot%20applications.commands"
                )
                logging.info(f"🔗 Invite URL (with slash commands): {invite}")
        except Exception as e:
            logging.debug(f"Invite URL generation failed: {e}")

        # Leave unauthorized guilds
        for guild in self.guilds:
            if not Config.is_guild_allowed(guild.id):
                logging.info(f"❌ Leaving unauthorized guild: {guild.name} ({guild.id})")
                await guild.leave()

        # Set status
        await self.change_presence(
            activity=discord.Activity(  # type: ignore[attr-defined]
                type=discord.ActivityType.listening,  # type: ignore[attr-defined]
                name="🎵 music | /help"
            )
        )

        # Optionally purge cached songs on restart (controlled by env)
        try:
            if getattr(Config, 'CLEAR_CACHE_ON_START', False):
                fm = FileManager()
                downloads_dir = fm.downloads_dir
                deleted = 0
                for f in downloads_dir.glob('*.mp3'):
                    try:
                        f.unlink()
                        deleted += 1
                    except Exception as e:
                        logging.debug(f"Could not delete cached file {f.name}: {e}")
                if deleted:
                    logging.info(f"🧹 Purged {deleted} cached audio file(s) on startup (CLEAR_CACHE_ON_START)")
            else:
                logging.info("💾 Skipping startup cache purge (CLEAR_CACHE_ON_START=false)")
        except Exception as e:
            logging.debug(f"Startup cache purge skipped: {e}")

        # Schedule daily auto-restart based on configuration
        # Ensure we only schedule this once per process
        if getattr(Config, 'AUTO_RESTART_ENABLED', True):
            if not hasattr(self, "_restart_task") or self._restart_task is None:
                try:
                    self._restart_task = asyncio.create_task(self._schedule_daily_restart_configurable())
                    logging.info(
                        f"⏰ Daily auto-restart enabled at {getattr(Config,'AUTO_RESTART_TIME','06:00')} "
                        f"(UTC offset {getattr(Config,'AUTO_RESTART_TZ_OFFSET_MINUTES',330)} min)"
                    )
                except Exception as e:
                    logging.error(f"❌ Failed to start restart scheduler: {e}")
        else:
            logging.info("⏹️ Daily auto-restart disabled by configuration")

        # After connecting, sync commands for guilds we're actually in
        try:
            for g in self.guilds:
                if Config.is_guild_allowed(g.id):
                    try:
                        guild_obj = discord.Object(id=g.id)  # type: ignore[attr-defined]
                        # Phase 1: clear existing guild commands remotely
                        try:
                            # Clear local view for this guild, then sync to wipe remote
                            self.tree.clear_commands(guild=guild_obj)
                            await self.tree.sync(guild=guild_obj)
                            logging.info(f"🗑️ Cleared existing guild commands for {g.id}")
                        except Exception as e:
                            logging.debug(f"Clear existing commands failed for {g.id}: {e}")

                        # Phase 2: copy current global commands into guild scope and sync
                        try:
                            self.tree.copy_global_to(guild=guild_obj)
                            logging.info(f"📥 Copied global commands to guild {g.id} for fast availability")
                        except Exception as e:
                            logging.debug(f"copy_global_to failed for guild {g.id}: {e}")

                        await self.tree.sync(guild=guild_obj)
                        logging.info(f"✅ Republished app commands for guild {g.id}")
                    except Exception as e:
                        logging.error(f"❌ Could not sync commands for guild {g.id}: {e}")
            # Also attempt a global sync as a fallback for visibility issues
            try:
                await self.tree.sync()
                logging.info("🌐 Global command sync attempted (may take up to 1 hour to propagate)")
            except Exception as e:
                logging.debug(f"Global sync skipped/failed: {e}")
        except Exception as e:
            logging.error(f"❌ Post-ready sync error: {e}")

    async def _schedule_daily_restart_configurable(self):
        """Sleep until the next scheduled time (per config) and then restart the process. Repeats daily."""
        while True:
            try:
                # Compute current time in UTC and apply configured offset without external tz database
                now_utc = datetime.now(timezone.utc)
                offset_minutes = int(getattr(Config, 'AUTO_RESTART_TZ_OFFSET_MINUTES', 330))
                offset = timedelta(minutes=offset_minutes)
                now_local = now_utc + offset

                # Parse restart time HH:MM
                time_str = getattr(Config, 'AUTO_RESTART_TIME', '06:00')
                try:
                    hh, mm = [int(x) for x in time_str.split(':', 1)]
                except Exception:
                    hh, mm = 6, 0

                # Next scheduled time from now
                target_local = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if now_local >= target_local:
                    target_local = target_local + timedelta(days=1)

                sleep_seconds = (target_local - now_local).total_seconds()
                hours = int(sleep_seconds // 3600)
                minutes = int((sleep_seconds % 3600) // 60)
                logging.info(
                    f"⏳ Next scheduled restart at {hh:02d}:{mm:02d} (UTC offset {offset_minutes} min) in ~{hours}h {minutes}m"
                )
                await asyncio.sleep(max(1, sleep_seconds))

                logging.info("🔁 Performing scheduled daily restart")
                await self._restart_process()
                # If restart returns (unlikely), schedule next day again
            except asyncio.CancelledError:
                logging.info("⏹️ Restart scheduler cancelled")
                return
            except Exception as e:
                logging.error(f"❌ Restart scheduler error: {e}")
                # In case of error, wait 10 minutes and try to schedule again
                await asyncio.sleep(600)

    async def _restart_process(self):
        """Gracefully close the bot and exec a fresh Python process for this script."""
        try:
            # Flush logs
            for handler in logging.getLogger().handlers:
                try:
                    handler.flush()
                except Exception:
                    pass

            # Close Discord connection cleanly
            await self.close()
        except Exception as e:
            logging.debug(f"Close during restart encountered: {e}")

        # Build exec arguments to relaunch this script
        python = sys.executable
        script_path = Path(__file__).resolve()
        args = [python, str(script_path)]
        logging.info(f"🚀 Re-exec: {' '.join(args)}")
        try:
            os.execv(python, args)
        except Exception as e:
            logging.error(f"❌ Exec failed, exiting instead: {e}")
            # As a fallback, exit and let external supervisor (if any) restart
            sys.exit(0)

    async def on_guild_join(self, guild):
        """Leave unauthorized guilds immediately when added after startup, and send contact message"""
        if not Config.is_guild_allowed(guild.id):
            logging.info(f"❌ Leaving unauthorized guild (joined after startup): {guild.name} ({guild.id})")
            owner_contact = getattr(Config, 'OWNER_CONTACT', '').strip()
            if owner_contact:
                contact_message = (
                    "❌ This bot is restricted to specific servers. "
                    f"If you wish to use it, please contact the owner: {owner_contact}"
                )
            else:
                contact_message = (
                    "❌ This bot is restricted to specific servers. "
                    "If you wish to use it, please contact the owner or server administrator."
                )
            channel = getattr(guild, 'system_channel', None)
            if channel is None or not channel.permissions_for(guild.me).send_messages:
                for ch in guild.text_channels:
                    if ch.permissions_for(guild.me).send_messages:
                        channel = ch
                        break
            if channel:
                try:
                    await channel.send(contact_message)
                except Exception as e:
                    logging.error(f"❌ Could not send contact message in {guild.name}: {e}")
            await guild.leave()
        else:
            # For allowed guilds, ensure slash commands are synced immediately
            try:
                await self.tree.sync(guild=discord.Object(id=guild.id))  # type: ignore[attr-defined]
                logging.info(f"✅ Synced app commands for new guild {guild.id}")
            except Exception as e:
                logging.error(f"❌ Failed to sync commands for new guild {guild.id}: {e}")

    async def on_message(self, message):
        """Process messages only in allowed controller channels"""
        if message.author.bot:
            return

        # Block messages from unauthorized guilds
        if message.guild and not Config.is_guild_allowed(message.guild.id):
            logging.info(f"❌ Ignoring message from unauthorized guild: {message.guild.name} ({message.guild.id})")
            return

        # Controller channel detection
        is_music_channel = False
        controller_info = None

        if message.guild:
            try:
                import json
                controller_data_file = Path(__file__).parent / "data" / "controller_data.json"
                if controller_data_file.exists():
                    with open(controller_data_file, 'r') as f:
                        controller_data = json.load(f)
                    guild_str = str(message.guild.id)
                    if guild_str in controller_data:
                        controller_info = controller_data[guild_str]
                        music_channel_id = controller_info.get("channel_id")
                        if message.channel.id == music_channel_id:
                            is_music_channel = True
                            logging.info(f"🎵 [CONTROLLER] Message in controller channel #{message.channel.name}: '{message.content}'")
            except Exception as e:
                logging.error(f"❌ Error checking controller channel: {e}")

        # Only process music requests in controller channels
        if is_music_channel:
            content = message.content.strip()
            # Ignore potential slash command text; real slash commands don't appear as messages
            if content and not content.startswith('/'):
                logging.info(f"🎵 [CONTROLLER] Processing music request: {content}")
                music_cog = self.get_cog('MusicCog')
                if music_cog and hasattr(music_cog, 'handle_song_request'):
                    await music_cog.handle_song_request(message, content)  # type: ignore[attr-defined]
                else:
                    logging.error("❌ [CONTROLLER] MusicCog not available!")
                    # Best-effort delete to keep controller clean
                    try:
                        await message.delete()
                        logging.info("✅ [CONTROLLER] Deleted message (MusicCog unavailable)")
                    except Exception as del_error:
                        logging.error(f"❌ Error deleting message: {del_error}")
            return
        else:
            # Ignore messages in non-controller channels (slash commands handled separately)
            # Reduce noise: log at debug level only
            logging.debug(f"[NORMAL] Ignoring non-controller message in #{message.channel.name}")
            return

    async def on_voice_state_update(self, member, before, after):
        """Handle voice state updates"""
        if member == self.user:
            return
        if before.channel and self.user in before.channel.members:
            human_members = [m for m in before.channel.members if not m.bot]
            if len(human_members) == 0:
                await asyncio.sleep(300)
                # Re-check after waiting to ensure the bot is still alone
                if before.channel and self.user in before.channel.members:
                    voice_client = get(self.voice_clients, channel=before.channel)
                    if voice_client:
                        await voice_client.disconnect(force=False)
                        logging.info(f"🔌 Disconnected from {before.channel.name} (alone)")

    async def on_command_error(self, ctx, error):
        """Handle command errors"""
        if ctx.guild and not Config.is_guild_allowed(ctx.guild.id):
            logging.info(f"❌ Ignoring command from unauthorized guild: {ctx.guild.name} ({ctx.guild.id})")
            return
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing required argument: `{error.param}`")
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ Invalid argument provided")
            return
        logging.error(f"❌ Command error: {error}")
        await ctx.send("❌ An error occurred while processing the command.")

async def main():
    """Main function to start the bot"""
    try:
        if hasattr(Config, "validate") and not Config.validate():
            logging.error("❌ Configuration validation failed")
            return
        intents = discord.Intents.default()  # type: ignore[attr-defined]
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True
        # Use the correct intents attribute for message events
        intents.messages = True
        bot = AuroraMusicBot(intents=intents)
        token = Config.BOT_TOKEN or ""
        await bot.start(token)
    except KeyboardInterrupt:
        logging.info("🛑 Bot stopped by user")
    except Exception as e:
        logging.error(f"❌ Fatal error: {e}")

if __name__ == "__main__":
    asyncio.run(main())