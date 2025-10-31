import os
from pathlib import Path
from dotenv import load_dotenv  # type: ignore
import logging

load_dotenv()

class Config:
    """Enhanced configuration with validation"""
    
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    VERSION = "3.2.37"
    
    ALLOWED_GUILD_IDS = [
        int(x.strip()) for x in os.getenv('SUPPORTED_GUILD_IDS', os.getenv('ALLOWED_GUILD_IDS', '')).split(',')
        if x.strip().isdigit()
    ]
    
    SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
    SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
    YOUTUBE_COOKIES = os.getenv('YOUTUBE_COOKIES', '')
    OWNER_CONTACT = os.getenv('OWNER_CONTACT', '').strip()
    BOT_BANNER_URL = os.getenv('BOT_BANNER_URL', '').strip()
    CONTROLLER_THUMBNAIL_URL = os.getenv('CONTROLLER_THUMBNAIL_URL', '').strip()
    SHOW_BANNER = os.getenv('SHOW_BANNER', 'true').strip().lower() in ('1', 'true', 'yes', 'y')
    SHOW_CONTROLLER_THUMBNAIL = os.getenv('SHOW_CONTROLLER_THUMBNAIL', 'false').strip().lower() in ('1', 'true', 'yes', 'y')
    CLEAR_CACHE_ON_START = os.getenv('CLEAR_CACHE_ON_START', 'false').strip().lower() in ('1', 'true', 'yes', 'y')
    
    BASE_DIR = Path(__file__).parent.parent
    DATA_DIR = BASE_DIR / "data"
    DOWNLOADS_DIR = Path.home() / "AuroraMusic_downloads"
    COOKIES_DIR = BASE_DIR / "cookies"

    AUTO_RESTART_ENABLED = os.getenv('AUTO_RESTART_ENABLED', 'true').strip().lower() in ('1', 'true', 'yes', 'y')
    AUTO_RESTART_TIME = os.getenv('AUTO_RESTART_TIME', '06:00')
    try:
        AUTO_RESTART_TZ_OFFSET_MINUTES = int(os.getenv('AUTO_RESTART_TZ_OFFSET_MINUTES', '330'))
    except ValueError:
        AUTO_RESTART_TZ_OFFSET_MINUTES = 330
    
    MAX_PLAYLIST_SIZE = 25
    MAX_QUEUE_SIZE = 100
    CACHE_TTL = 3600
    MAX_CONCURRENT_DOWNLOADS = 3

    ENABLE_GLOBAL_COMMAND_SYNC = os.getenv('ENABLE_GLOBAL_COMMAND_SYNC', 'false').strip().lower() in ('1', 'true', 'yes', 'y')
    try:
        COMMAND_SYNC_RETRIES = int(os.getenv('COMMAND_SYNC_RETRIES', '3'))
    except ValueError:
        COMMAND_SYNC_RETRIES = 3
    try:
        COMMAND_SYNC_BACKOFF_BASE = float(os.getenv('COMMAND_SYNC_BACKOFF_BASE', '1.5'))
    except ValueError:
        COMMAND_SYNC_BACKOFF_BASE = 1.5

    GLOBAL_COMMAND_SYNC_OFFPEAK_ENABLED = os.getenv('GLOBAL_COMMAND_SYNC_OFFPEAK_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes', 'y')
    try:
        GLOBAL_COMMAND_SYNC_OFFPEAK_START_HOUR_UTC = int(os.getenv('GLOBAL_COMMAND_SYNC_OFFPEAK_START_HOUR_UTC', '2'))
    except ValueError:
        GLOBAL_COMMAND_SYNC_OFFPEAK_START_HOUR_UTC = 2
    try:
        GLOBAL_COMMAND_SYNC_OFFPEAK_END_HOUR_UTC = int(os.getenv('GLOBAL_COMMAND_SYNC_OFFPEAK_END_HOUR_UTC', '5'))
    except ValueError:
        GLOBAL_COMMAND_SYNC_OFFPEAK_END_HOUR_UTC = 5
    try:
        GLOBAL_COMMAND_SYNC_RETRY_INTERVAL_SECONDS = int(os.getenv('GLOBAL_COMMAND_SYNC_RETRY_INTERVAL_SECONDS', '300'))
    except ValueError:
        GLOBAL_COMMAND_SYNC_RETRY_INTERVAL_SECONDS = 300
    try:
        GLOBAL_COMMAND_SYNC_MAX_ATTEMPTS_IN_WINDOW = int(os.getenv('GLOBAL_COMMAND_SYNC_MAX_ATTEMPTS_IN_WINDOW', '6'))
    except ValueError:
        GLOBAL_COMMAND_SYNC_MAX_ATTEMPTS_IN_WINDOW = 6
    
    YTDL_FORMAT_OPTS = {
        'format': 'bestaudio[ext=m4a][filesize<25M]/bestaudio[filesize<25M]/best[filesize<25M]',  # Smaller files
        'outtmpl': '%(title)s_%(id)s.%(ext)s',
        'concurrent_fragment_downloads': 1,  # ✅ Reduced from 2
        'http_chunk_size': 1048576,  # ✅ Smaller chunks (1MB instead of 10MB)
        'retries': 3,  # ✅ More retries
        'fragment_retries': 3,
        'socket_timeout': 30,  # ✅ Longer timeout
        'keepvideo': False,
        'restrictfilenames': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'logtostderr': False,
        'quiet': True,
        'no_playlist': True,
        'extractaudio': True,
        'audioformat': 'mp3',
        'audioquality': '96K',  # ✅ Lower quality for stability (was 128K)
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '96',  # ✅ Match audioquality
        }],
        'prefer_ffmpeg': True,
        'buffersize': 1024,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    }
    
    SEARCH_OPTS = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': False,
        'ignoreerrors': True,
        'playlist_items': f'1:{MAX_PLAYLIST_SIZE}',
        'socket_timeout': 15,  # Faster timeout for searches
    }
    
    @classmethod
    def get_cookies_path(cls) -> str | None:
        """Get absolute path to cookies file with proper validation"""
        paths_to_check = []
        
        if cls.YOUTUBE_COOKIES:
            if os.path.isabs(cls.YOUTUBE_COOKIES):
                paths_to_check.append(cls.YOUTUBE_COOKIES)
            else:
                paths_to_check.append(str(cls.BASE_DIR / cls.YOUTUBE_COOKIES))
        
        paths_to_check.extend([
            str(cls.COOKIES_DIR / "youtube.txt"),
            str(cls.BASE_DIR / "youtube.txt"),
            str((cls.BASE_DIR.parent / "cookies" / "youtube.txt")),
            str(Path.home() / ".config" / "aurora" / "youtube.txt")
        ])
        
        for path in paths_to_check:
            if os.path.exists(path) and os.path.getsize(path) > 0:
                logging.info(f"✅ Using cookies: {path}")
                return path
        
        logging.warning("⚠️ No valid cookies file found")
        return None
    
    @classmethod
    def get_ytdl_opts_with_cookies(cls):
        """Get YTDL options with cookies and optimizations"""
        opts = cls.YTDL_FORMAT_OPTS.copy()
        
        cookies_file = cls.get_cookies_path()
        if cookies_file:
            opts.update({
                'cookiefile': cookies_file,
                'extractor_retries': 2,
                'retry_sleep_functions': {'http': lambda n: min(0.5 * n, 3)},
            })
        
        return opts
    
    @classmethod
    def get_search_opts_with_cookies(cls):
        """Get search options with cookies"""
        opts = cls.SEARCH_OPTS.copy()
        
        cookies_file = cls.get_cookies_path()
        if cookies_file:
            opts.update({
                'cookiefile': cookies_file,
                'extractor_retries': 2,
                'retry_sleep_functions': {'http': lambda n: min(0.5 * n, 2)},
            })
        
        return opts
    
    @classmethod
    def ensure_directories(cls):
        """Ensure all required directories exist"""
        for directory in [cls.DATA_DIR, cls.DOWNLOADS_DIR, cls.COOKIES_DIR]:
            directory.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def validate(cls):
        """Comprehensive validation"""
        cls.ensure_directories()
        
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required")
        
        if not cls.BOT_TOKEN.startswith(('MTC', 'MTM', 'MTQ')):
            logging.warning("⚠️ BOT_TOKEN format may be invalid")
        
        has_spotify = bool(cls.SPOTIFY_CLIENT_ID and cls.SPOTIFY_CLIENT_SECRET)
        if not has_spotify:
            logging.warning("⚠️ Spotify features disabled (missing credentials)")
        
        cookies_path = cls.get_cookies_path()
        if not cookies_path:
            logging.warning("⚠️ No YouTube cookies - private videos may fail")
        
        if cls.BOT_BANNER_URL:
            logging.info("🖼️ Using BOT_BANNER_URL from environment for banner fallback")
        if cls.CONTROLLER_THUMBNAIL_URL:
            logging.info("🖼️ CONTROLLER_THUMBNAIL_URL set in environment")
        logging.info(f"🧩 SHOW_BANNER={cls.SHOW_BANNER} | SHOW_CONTROLLER_THUMBNAIL={cls.SHOW_CONTROLLER_THUMBNAIL}")
        logging.info(f"💾 CLEAR_CACHE_ON_START={cls.CLEAR_CACHE_ON_START}")

        logging.info(f"✅ Configuration validated (Spotify: {has_spotify})")
        return True
    
    @classmethod
    def is_guild_allowed(cls, guild_id):
        """Check if a guild is allowed"""
        return guild_id in cls.ALLOWED_GUILD_IDS

