import os
from pathlib import Path
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

class Config:
    """Enhanced configuration with validation"""
    
    # Bot Configuration
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    # Application version
    VERSION = "3.2.10"
    
    # Discord Configuration
    ALLOWED_GUILD_IDS = [
        int(x.strip()) for x in os.getenv('SUPPORTED_GUILD_IDS', os.getenv('ALLOWED_GUILD_IDS', '')).split(',')
        if x.strip().isdigit()
    ]
    
    # API Configuration
    SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
    SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
    YOUTUBE_COOKIES = os.getenv('YOUTUBE_COOKIES', '')
    # Optional owner contact to display in unauthorized guild message
    OWNER_CONTACT = os.getenv('OWNER_CONTACT', '').strip()
    
    # Paths
    BASE_DIR = Path(__file__).parent.parent
    DATA_DIR = BASE_DIR / "data"
    DOWNLOADS_DIR = BASE_DIR / "downloads"
    COOKIES_DIR = BASE_DIR / "cookies"

    # Auto-Restart Configuration
    # Enable or disable daily auto-restart (default: true)
    AUTO_RESTART_ENABLED = os.getenv('AUTO_RESTART_ENABLED', 'true').strip().lower() in ('1', 'true', 'yes', 'y')
    # Time of day for restart in 24h format (local to the provided offset) (default: 06:00)
    AUTO_RESTART_TIME = os.getenv('AUTO_RESTART_TIME', '06:00')
    # Timezone offset in minutes relative to UTC (IST = +330). (default: 330)
    try:
        AUTO_RESTART_TZ_OFFSET_MINUTES = int(os.getenv('AUTO_RESTART_TZ_OFFSET_MINUTES', '330'))
    except ValueError:
        AUTO_RESTART_TZ_OFFSET_MINUTES = 330
    
    # Performance Settings
    MAX_PLAYLIST_SIZE = 25
    MAX_QUEUE_SIZE = 100
    CACHE_TTL = 3600
    MAX_CONCURRENT_DOWNLOADS = 3
    
    # ✅ OPTIMIZED YTDL settings for stable audio
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
        # ✅ Add buffer settings
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
        
        # Add environment variable path
        if cls.YOUTUBE_COOKIES:
            if os.path.isabs(cls.YOUTUBE_COOKIES):
                paths_to_check.append(cls.YOUTUBE_COOKIES)
            else:
                paths_to_check.append(str(cls.BASE_DIR / cls.YOUTUBE_COOKIES))
        
        # Add default locations
        paths_to_check.extend([
            str(cls.COOKIES_DIR / "youtube.txt"),
            str(cls.BASE_DIR / "youtube.txt"),
            # Also support top-level project cookies for local runs
            str((cls.BASE_DIR.parent / "cookies" / "youtube.txt")),
            str(Path.home() / ".config" / "aurora" / "youtube.txt")
        ])
        
        # Return first existing path
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
        
        # Required variables
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required")
        
        # Validate token format (basic)
        if not cls.BOT_TOKEN.startswith(('MTC', 'MTM', 'MTQ')):
            logging.warning("⚠️ BOT_TOKEN format may be invalid")
        
        # Spotify validation
        has_spotify = bool(cls.SPOTIFY_CLIENT_ID and cls.SPOTIFY_CLIENT_SECRET)
        if not has_spotify:
            logging.warning("⚠️ Spotify features disabled (missing credentials)")
        
        # Cookies validation
        cookies_path = cls.get_cookies_path()
        if not cookies_path:
            logging.warning("⚠️ No YouTube cookies - private videos may fail")
        
        logging.info(f"✅ Configuration validated (Spotify: {has_spotify})")
        return True
    
    @classmethod
    def is_guild_allowed(cls, guild_id):
        """Check if a guild is allowed"""
        return guild_id in cls.ALLOWED_GUILD_IDS

# Do not auto-validate on import; validation is performed at runtime