import discord
from discord.ext import commands
from discord.utils import get
import asyncio
import sys
import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from config.settings import Config

project_root = Path(__file__).parent.parent
log_dir = project_root / 'logs'
log_dir.mkdir(exist_ok=True)
log_file = log_dir / 'bot.log'

class SafeConsoleFilter(logging.Filter):
    """Sanitize log records."""
    def __init__(self, encoding: str | None = None):
        super().__init__()
        self.encoding = encoding or getattr(sys.stdout, 'encoding', None) or 'cp1252'

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        try:
            msg.encode(self.encoding, errors='strict')
        except Exception:
            try:
                safe = msg.encode(self.encoding, errors='replace').decode(self.encoding, errors='replace')
                record.msg = safe
                record.args = ()
            except Exception:
                record.msg = ''.join(ch if ord(ch) < 128 else '?' for ch in msg)
                record.args = ()
        return True

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.addFilter(SafeConsoleFilter())

root_logger.handlers.clear()
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

class AuroraMusicBot(commands.Bot):
    """Main bot class."""

    def __init__(self, intents):
        super().__init__(command_prefix=commands.when_mentioned_or('!'), intents=intents, help_command=None)
        self._commands_synced_global = False
        self._command_sync_lock = None

    async def setup_hook(self):
        """Load cogs on startup"""
        if self._command_sync_lock is None:
            self._command_sync_lock = asyncio.Lock()
        cogs_to_load = [
            'cogs.music.music_cog',
            'cogs.admin',
            'cogs.general'
        ]
        for cog in cogs_to_load:
            try:
                await self.load_extension(cog)
                logging.info(f"✅ Loaded cog: {cog}")
            except Exception as e:
                logging.error(f"❌ Failed to load cog {cog}: {e}")

        try:
            if getattr(Config, 'ALLOWED_GUILD_IDS', []):
                for gid in Config.ALLOWED_GUILD_IDS:
                    try:
                        if not self.get_guild(gid):
                            logging.info(f"Skipping command sync for guild {gid} (bot not in guild)")
                            continue
                        await self._attempt_command_sync(guild=discord.Object(id=gid))
                        logging.info(f"✅ Synced app commands for guild {gid}")
                    except Exception as guild_sync_err:
                        logging.error(f"❌ Failed to sync commands for guild {gid}: {guild_sync_err}")
            else:
                if getattr(Config, 'ENABLE_GLOBAL_COMMAND_SYNC', False):
                    if getattr(Config, 'GLOBAL_COMMAND_SYNC_OFFPEAK_ENABLED', False):
                        if self._is_now_in_offpeak_window():
                            await self._attempt_command_sync(guild=None, global_sync=True)
                            logging.info("✅ Synced app commands globally (off-peak window)")
                        else:
                            try:
                                if not hasattr(self, '_global_sync_task') or self._global_sync_task is None:
                                    self._global_sync_task = asyncio.create_task(self._schedule_global_sync_at_offpeak())
                                    logging.info("⏳ Global command sync scheduled for next off-peak window")
                            except Exception as e:
                                logging.error(f"Exception: {e}")
                    else:
                        await self._attempt_command_sync(guild=None, global_sync=True)
                        logging.info("✅ Synced app commands globally (opt-in)")
                else:
                    logging.info("🔕 Global command sync skipped (ENABLE_GLOBAL_COMMAND_SYNC=false)")
        except Exception as sync_err:
            logging.error(f"❌ Failed to sync app commands: {sync_err}")

    async def _attempt_command_sync(self, guild: discord.Object | None = None, global_sync: bool = False) -> None:
        """Sync app commands with retries/backoff."""
        max_retries = int(getattr(Config, 'COMMAND_SYNC_RETRIES', 3))
        backoff_base = float(getattr(Config, 'COMMAND_SYNC_BACKOFF_BASE', 1.5))

        lock = getattr(self, '_command_sync_lock', None)
        if lock is None:
            lock = asyncio.Lock()
            self._command_sync_lock = lock

        attempt = 0
        async with lock:
            while True:
                try:
                    if guild is None and global_sync:
                        await self.tree.sync()
                        self._commands_synced_global = True
                    elif guild is None:
                        await self.tree.sync()
                        self._commands_synced_global = True
                    else:
                        await self.tree.sync(guild=guild)
                    return
                except Exception as e:
                    attempt += 1
                    if attempt > max_retries:
                        logging.error(f"❌ Command sync failed after {attempt} attempts: {e}")
                        raise
                    delay = backoff_base ** attempt
                    logging.warning(f"⚠️ Command sync attempt {attempt} failed: {e}. Retrying in {delay:.1f}s")
                    try:
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        raise

    def _is_now_in_offpeak_window(self) -> bool:
        """Check if current UTC hour is in off-peak window."""
        try:
            start = int(getattr(Config, 'GLOBAL_COMMAND_SYNC_OFFPEAK_START_HOUR_UTC', 2))
            end = int(getattr(Config, 'GLOBAL_COMMAND_SYNC_OFFPEAK_END_HOUR_UTC', 5))
        except Exception:
            start, end = 2, 5
        now_hour = datetime.now(timezone.utc).hour
        if start <= end:
            return start <= now_hour < end
        else:
            return now_hour >= start or now_hour < end

    async def _schedule_global_sync_at_offpeak(self):
        """Wait for off-peak window to run global sync."""
        try:
            start = int(getattr(Config, 'GLOBAL_COMMAND_SYNC_OFFPEAK_START_HOUR_UTC', 2))
            end = int(getattr(Config, 'GLOBAL_COMMAND_SYNC_OFFPEAK_END_HOUR_UTC', 5))
        except Exception:
            start, end = 2, 5

        now = datetime.now(timezone.utc)

        candidate = now.replace(hour=start, minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate = candidate + timedelta(days=1)

        wait_seconds = (candidate - now).total_seconds()
        logging.info(f"⏳ Waiting {int(wait_seconds)}s until next global command sync window at {candidate.isoformat()} UTC")
        try:
            await asyncio.sleep(max(1, wait_seconds))

            window_end = candidate.replace(hour=end, minute=0, second=0, microsecond=0)
            if start > end:
                window_end = window_end + timedelta(days=1)

            attempts = 0
            max_attempts = int(getattr(Config, 'GLOBAL_COMMAND_SYNC_MAX_ATTEMPTS_IN_WINDOW', 6))
            retry_interval = int(getattr(Config, 'GLOBAL_COMMAND_SYNC_RETRY_INTERVAL_SECONDS', 300))

            while True:
                now = datetime.now(timezone.utc)
                if now >= window_end:
                    logging.warning("⚠️ Off-peak window ended before successful global sync")
                    break

                if attempts >= max_attempts:
                    logging.warning("⚠️ Reached max global sync attempts for this off-peak window")
                    break

                attempts += 1
                try:
                    await self._attempt_command_sync(guild=None, global_sync=True)
                    self._commands_synced_global = True
                    logging.info(f"✅ Global command sync completed at off-peak window (attempt {attempts})")
                    break
                except Exception as e:
                    logging.warning(f"⚠️ Off-peak global sync attempt {attempts} failed: {e}")
                    now = datetime.now(timezone.utc)
                    time_left = (window_end - now).total_seconds()
                    if time_left <= 0:
                        logging.warning("⚠️ No time left in off-peak window for retries")
                        break
                    wait = min(retry_interval, max(1, int(time_left)))
                    logging.info(f"⏳ Waiting {wait}s before next global sync attempt (attempt {attempts + 1})")
                    try:
                        await asyncio.sleep(wait)
                    except asyncio.CancelledError:
                        logging.info("⏹️ Global sync scheduler cancelled during sleep")
                        return
        except asyncio.CancelledError:
            logging.info("⏹️ Global sync scheduler cancelled")
            return
        except Exception as e:
            logging.error(f"❌ Off-peak global sync failed: {e}")
        finally:
            try:
                self._global_sync_task = None
            except Exception:
                pass

    async def on_ready(self):
        """Bot ready event"""
        logging.info(f"🎵 {self.user} is now online!")
        logging.info(f"📡 Connected to {len(self.guilds)} servers")
        logging.info(f"👥 Serving {len(set(self.get_all_members()))} users")

        try:
            app_info = await self.application_info()
            client_id = app_info.id if hasattr(app_info, 'id') else None
            if client_id:
                perms = 8
                invite = (
                    f"https://discord.com/api/oauth2/authorize?client_id={client_id}"
                    f"&permissions={perms}&scope=bot%20applications.commands"
                )
                logging.info(f"🔗 Invite URL (with slash commands): {invite}")
        except Exception as e:
            logging.error(f"Exception: {e}")

        for guild in self.guilds:
            if not Config.is_guild_allowed(guild.id):
                logging.info(f"❌ Leaving unauthorized guild: {guild.name} ({guild.id})")
                await guild.leave()

        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="🎵 music | /help"
            )
        )

        logging.info("💾 Downloads/background caching disabled — skipping startup cache purge")

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

        try:
            for g in self.guilds:
                if Config.is_guild_allowed(g.id):
                    try:
                        guild_obj = discord.Object(id=g.id)
                        try:
                            self.tree.clear_commands(guild=guild_obj)
                            await self._attempt_command_sync(guild=guild_obj)
                            logging.info(f"🗑️ Cleared and republished guild commands for {g.id}")
                        except Exception as e:
                            logging.error(f"Exception: {e}")
                    except Exception as e:
                        logging.error(f"❌ Could not sync commands for guild {g.id}: {e}")
            try:
                if getattr(Config, 'ENABLE_GLOBAL_COMMAND_SYNC', False) and not getattr(self, '_commands_synced_global', False):
                    if getattr(Config, 'GLOBAL_COMMAND_SYNC_OFFPEAK_ENABLED', False):
                        if self._is_now_in_offpeak_window():
                            await self._attempt_command_sync(guild=None, global_sync=True)
                            logging.info("🌐 Global command sync attempted (off-peak)")
                            self._commands_synced_global = True
                        else:
                            if not hasattr(self, '_global_sync_task') or self._global_sync_task is None:
                                self._global_sync_task = asyncio.create_task(self._schedule_global_sync_at_offpeak())
                                logging.info("⏳ Global command sync scheduled post-ready for next off-peak window")
                    else:
                        await self._attempt_command_sync(guild=None, global_sync=True)
                        logging.info("🌐 Global command sync attempted (opt-in)")
                        self._commands_synced_global = True
                else:
                    pass
            except Exception as e:
                logging.error(f"Exception: {e}")
        except Exception as e:
            logging.error(f"❌ Post-ready sync error: {e}")

    async def _schedule_daily_restart_configurable(self):
        """Sleep until the next scheduled time (per config) and then restart the process. Repeats daily."""
        while True:
            try:
                now_utc = datetime.now(timezone.utc)
                offset_minutes = int(getattr(Config, 'AUTO_RESTART_TZ_OFFSET_MINUTES', 330))
                offset = timedelta(minutes=offset_minutes)
                now_local = now_utc + offset

                time_str = getattr(Config, 'AUTO_RESTART_TIME', '06:00')
                try:
                    hh, mm = [int(x) for x in time_str.split(':', 1)]
                except Exception:
                    hh, mm = 6, 0

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
            except asyncio.CancelledError:
                logging.info("⏹️ Restart scheduler cancelled")
                return
            except Exception as e:
                logging.error(f"❌ Restart scheduler error: {e}")
                await asyncio.sleep(600)

    async def _restart_process(self):
        """Restart bot process."""
        try:
            for handler in logging.getLogger().handlers:
                try:
                    handler.flush()
                except Exception:
                    pass

            try:
                await self.close()
            except Exception as e:
                logging.error(f"Exception: {e}")

            try:
                http = getattr(self, 'http', None)
                if http and hasattr(http, 'close'):
                    await http.close()  # type: ignore[func-returns-value]
            except Exception as e:
                logging.error(f"Exception: {e}")

            try:
                loop = asyncio.get_running_loop()
                current = asyncio.current_task()
                tasks = [t for t in asyncio.all_tasks(loop) if t is not current and not t.done()]
                for t in tasks:
                    t.cancel()
                if tasks:
                    await asyncio.wait(tasks, timeout=0.5)
            except Exception as e:
                logging.error(f"Exception: {e}")

            try:
                await asyncio.sleep(0.1)
            except Exception:
                pass

            python = sys.executable
            args = [python] + sys.argv
            logging.info(f"🚀 Re-exec: {' '.join(args)}")
            try:
                # Preferred: replace current process with new Python process
                os.execv(python, args)
            except Exception as e:
                logging.warning(f"⚠️ os.execv failed: {e}. Falling back to spawn + exit")
                try:

                    subprocess.Popen(args, close_fds=True)
                except Exception as e2:
                    logging.error(f"❌ Fallback spawn also failed: {e2}")
                finally:
                    os._exit(0)
        except Exception as e:
            logging.error(f"❌ Restart routine error: {e}")
            os._exit(0)

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
            try:
                await self.tree.sync(guild=discord.Object(id=guild.id))
                logging.info(f"✅ Synced app commands for new guild {guild.id}")
            except Exception as e:
                logging.error(f"❌ Failed to sync commands for new guild {guild.id}: {e}")

    async def on_message(self, message):
        """Process messages only in allowed controller channels"""
        if message.author.bot:
            return

        if message.guild and not Config.is_guild_allowed(message.guild.id):
            logging.info(f"❌ Ignoring message from unauthorized guild: {message.guild.name} ({message.guild.id})")
            return

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

        if is_music_channel:
            content = message.content.strip()
            if content and not content.startswith('/'):
                logging.info(f"🎵 [CONTROLLER] Processing music request: {content}")
                music_cog = self.get_cog('MusicCog')
                if music_cog and hasattr(music_cog, 'handle_song_request'):
                    await music_cog.handle_song_request(message, content)  # type: ignore[attr-defined]
                else:
                    logging.error("❌ [CONTROLLER] MusicCog not available!")
                    try:
                        await message.delete()
                        logging.info("✅ [CONTROLLER] Deleted message (MusicCog unavailable)")
                    except Exception as del_error:
                        logging.error(f"❌ Error deleting message: {del_error}")
            return
        else:
            return

    async def on_voice_state_update(self, member, before, after):
        """Handle voice state updates"""
        if member == self.user:
            return
        if before.channel and self.user in before.channel.members:
            human_members = [m for m in before.channel.members if not m.bot]
            if len(human_members) == 0:
                await asyncio.sleep(300)
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
