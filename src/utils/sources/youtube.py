import asyncio
import time
import hashlib
import aiohttp
import re
import json
import yt_dlp
import discord
import traceback
import logging
import random
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from config.settings import Config

class YouTubeHandlerSingleton:
    """YouTube handler singleton."""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._search_pool = {}
            self._initialized = True

    def _cleanup_old_instances(self):
        self._search_pool.clear()

    def _get_search_instance(self, use_cookies: bool = True, use_proxy: bool = True):
        """Get new search instance."""
        opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'skip_download': True,
            'extract_flat': False,
            'playlist_items': f'1:{getattr(Config, "MAX_PLAYLIST_SIZE", 100)}',
            'socket_timeout': 15,
            'retries': 3,
            'extractor_args': {
                'youtube': {
                    'player_client': ['web', 'ios', 'android'],
                    'player_skip': ['hls', 'dash'],
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
            },
            'sleep_interval': 2,
            'max_sleep_interval': 5,
            'geo_bypass': True,
            'geo_bypass_country': None,
            'age_limit': 99,
        }

        if use_proxy:
            if Config.PROXIES:
                opts['proxy'] = random.choice(Config.PROXIES)
            elif Config.PROXY_URL:
                opts['proxy'] = Config.PROXY_URL

        if use_cookies:
            cookies_file = getattr(Config, "get_cookies_path", lambda: None)()
            if cookies_file and Path(cookies_file).exists():
                opts['cookiefile'] = str(cookies_file)
        
        return yt_dlp.YoutubeDL(opts)

    def _get_stream_instance(self, use_cookies: bool = True):
        """Get new stream instance (stateless for low memory usage)"""
        opts = Config.YTDL_FORMAT_OPTS.copy()
        
        if Config.PROXIES:
            opts['proxy'] = random.choice(Config.PROXIES)
        elif Config.PROXY_URL:
            opts['proxy'] = Config.PROXY_URL

        if use_cookies:
            cookies_file = getattr(Config, "get_cookies_path", lambda: None)()
            if cookies_file and Path(cookies_file).exists():
                opts['cookiefile'] = str(cookies_file)
        
        return yt_dlp.YoutubeDL(opts)

    

    def is_url_supported(self, url: str) -> bool:
        return bool(re.search(r'(youtube\.com|youtu\.be)', url, re.IGNORECASE))

    def is_playlist_url(self, url: str) -> bool:
        if not self.is_url_supported(url):
            return False
        playlist_patterns = [
            r'[&?]list=', r'playlist\?list=', r'/playlist/',
            r'music\.youtube\.com/playlist'
        ]
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in playlist_patterns)

    def clean_url(self, url: str) -> str:
        if not self.is_url_supported(url):
            return url
        try:
            shorts_match = re.search(r'youtube\.com/shorts/([a-zA-Z0-9_-]+)', url)
            if shorts_match:
                video_id = shorts_match.group(1)
                return f"https://www.youtube.com/watch?v={video_id}"
            if 'v=' in url:
                video_id = url.split('v=')[1].split('&')[0]
                return f"https://www.youtube.com/watch?v={video_id}"
            elif 'youtu.be/' in url:
                video_id = url.split('youtu.be/')[1].split('?')[0]
                return f"https://www.youtube.com/watch?v={video_id}"
            else:
                return url
        except Exception:
            return url

    def clean_filename(self, filename: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*]', '', filename)
        cleaned = re.sub(r'[^\w\s\-\.]', '', cleaned)
        cleaned = re.sub(r'\s+', '_', cleaned.strip())
        return cleaned[:100] if len(cleaned) > 100 else cleaned

    async def search(self, query: str) -> Optional[Dict[str, Any]]:
        for attempt in range(3):  # Retry up to 3 times
            try:
                loop = asyncio.get_event_loop()
                if query.startswith(('http://', 'https://')):
                    search_query = self.clean_url(query)
                else:
                    search_query = f"ytsearch:{query}"
                logging.info(f"🔍 YouTube search: {query}")
                try:
                    result = await self._web_based_search(query)
                    if result:
                        logging.info("✅ Web-based search successful")
                        return result
                except Exception as e:
                    logging.warning(f"⚠️ Web-based search failed: {e}")
                extraction_strategies = [
                    ('web_client', {'extractor_args': {'youtube': {'player_client': ['web']}}}),
                    ('ios_client', {'extractor_args': {'youtube': {'player_client': ['ios']}}}),
                    ('android_client', {'extractor_args': {'youtube': {'player_client': ['android']}}}),
                    ('minimal', {'format': 'worst', 'quiet': True})
                ]

                # Add direct connection fallback if proxies are in use
                if Config.PROXIES or Config.PROXY_URL:
                    extraction_strategies.append(
                        ('direct_fallback', {'extractor_args': {'youtube': {'player_client': ['web']}}, '_no_proxy': True})
                    )

                for strategy_name, extra_opts in extraction_strategies:
                    try:
                        logging.info(f"🔍 Trying extraction strategy: {strategy_name}")
                        use_proxy = not extra_opts.pop('_no_proxy', False)
                        
                        base_instance = self._get_search_instance(use_cookies=True, use_proxy=use_proxy)
                        base_opts = dict(getattr(base_instance, 'params', {}) or {})
                        base_opts.update(extra_opts)
                        
                        ytdl_tmp = yt_dlp.YoutubeDL(base_opts)  # type: ignore[arg-type]
                        data = await asyncio.wait_for(
                            loop.run_in_executor(None, lambda: ytdl_tmp.extract_info(search_query, download=False)),
                            timeout=15.0
                        )
                        if data and 'entries' in data and data['entries']:
                            entries = data.get('entries') or []
                            if not isinstance(entries, list):
                                entries = []
                            for entry in entries:
                                if entry and entry.get('id'):
                                    result = self._format_song_data(entry)
                                    logging.info(f"✅ Found with strategy: {strategy_name}")
                                    return result
                    except asyncio.TimeoutError:
                        logging.warning(f"⏰ Timeout with strategy: {strategy_name}")
                        continue
                    except Exception as e:
                        if 'bot' in str(e).lower():
                            logging.warning(f"🤖 Bot detection with strategy: {strategy_name}")
                            continue
                        else:
                            logging.warning(f"⚠️ Error with strategy: {strategy_name}: {e}")
                            continue
                return await self._create_searchable_fallback(query)
            except Exception as e:
                logging.error(f"❌ Search error on attempt {attempt + 1}: {e}")
                if attempt < 2:
                    logging.info(f"Retrying in {2 * (attempt + 1)} seconds...")
                    await asyncio.sleep(2 * (attempt + 1))
                else:
                    logging.error("❌ All search attempts failed.")
                    return None
        return None

    async def _web_based_search(self, query: str) -> Optional[Dict[str, Any]]:
        """Web scraping fallback for bot detection"""
        # Try up to 3 different proxies if available
        use_proxies = bool(Config.PROXIES or Config.PROXY_URL)
        retries = 3 if use_proxies and len(Config.PROXIES) > 1 else 1
        
        # Add a final attempt without proxy if proxies are in use
        total_attempts = retries + 1 if use_proxies else retries

        for attempt in range(total_attempts):
            try:
                request_kwargs = {}
                is_proxy_attempt = attempt < retries and use_proxies
                
                if is_proxy_attempt:
                    if Config.PROXIES:
                        proxy = random.choice(Config.PROXIES)
                        request_kwargs['proxy'] = proxy
                        if attempt > 0:
                            logging.info(f"🔄 Retry {attempt} with different proxy: {proxy}")
                    elif Config.PROXY_URL:
                        request_kwargs['proxy'] = Config.PROXY_URL
                elif use_proxies:
                    logging.info("🔄 Retrying web search without proxy...")

                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                    }
                ) as session:

                    search_url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
                    
                    async with session.get(search_url, **request_kwargs) as response:
                        if response.status == 200:
                            html = await response.text()

                            match = re.search(r'var ytInitialData = ({.*?});', html)
                            if match:
                                try:
                                    data = json.loads(match.group(1))

                                    contents = data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [])

                                    for section in contents:
                                        items = section.get('itemSectionRenderer', {}).get('contents', [])
                                        for item in items:
                                            if 'videoRenderer' in item:
                                                video = item['videoRenderer']
                                                video_id = video.get('videoId', None)
                                                title = video.get('title', {}).get('runs', [{}])[0].get('text', 'Unknown')
                                                uploader = "Unknown Artist"
                                                try:
                                                    channel_info = video.get('ownerText', {}).get('runs', [{}])
                                                    if channel_info and len(channel_info) > 0:
                                                        uploader = channel_info[0].get('text', 'Unknown Artist')
                                                    if uploader == "Unknown Artist":
                                                        long_byline = video.get('longBylineText', {}).get('runs', [{}])
                                                        if long_byline and len(long_byline) > 0:
                                                            uploader = long_byline[0].get('text', 'Unknown Artist')
                                                    if uploader == "Unknown Artist":
                                                        uploader = self._extract_artist_from_query(title)
                                                except Exception as e:
                                                    logging.warning(f"⚠️ Error extracting uploader: {e}")
                                                    uploader = self._extract_artist_from_query(query)
                                                if video_id and title and uploader:
                                                    return {
                                                        'id': video_id,
                                                        'title': title,
                                                        'webpage_url': f"https://www.youtube.com/watch?v={video_id}",
                                                        'duration': 180,  # Default duration
                                                        'uploader': uploader,
                                                        'source': 'web_scraping',
                                                        'availability': 'public'
                                                    }
                                except json.JSONDecodeError:
                                    pass

            except Exception as e:
                logging.warning(f"⚠️ Web-based search error (attempt {attempt+1}): {e}")
                if attempt < total_attempts - 1:
                    continue
                return None
        return None

    async def _create_searchable_fallback(self, query: str) -> Optional[Dict[str, Any]]:
        """Create a searchable fallback result"""
        try:
            query_hash = hashlib.md5(f"{query}{int(time.time() // 3600)}".encode()).hexdigest()[:11]

            artist_name = self._extract_artist_from_query(query)

            return {
                'id': query_hash,
                'title': f"Search: {query}",
                'webpage_url': f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}",
                'duration': 180,
                'uploader': artist_name,
                'source': 'fallback',
                'availability': 'public',
                'is_fallback': True
            }

        except Exception as e:
            logging.error(f"❌ Fallback creation failed: {e}")
            return None

    def _extract_artist_from_query(self, query: str) -> str:
        """Extract potential artist name from search query"""
        try:
            if ' - ' in query:
                parts = query.split(' - ')
                if len(parts) >= 2:
                    return parts[0].strip()

            if ' by ' in query.lower():
                parts = query.lower().split(' by ')
                if len(parts) >= 2:
                    return parts[1].strip().title()

            words = query.split()
            if len(words) >= 2:
                return ' '.join(words[:2])  # First two words
            elif len(words) == 1:
                return words[0]

            return "Unknown Artist"

        except Exception:
            return "Unknown Artist"

    def _format_song_data(self, video_info: Dict) -> Dict[str, Any]:
        """Format video info with enhanced debugging and validation"""
        try:
            logging.info(f"🔍 [FORMAT DEBUG] Processing video: {video_info.get('id', 'no-id')}")

            availability = video_info.get('availability', 'public')
            title = video_info.get('title', 'Unknown Title')
            video_id = video_info.get('id', 'unknown')

            logging.info(f"🔍 [FORMAT DEBUG] - Title: {title}")
            logging.info(f"🔍 [FORMAT DEBUG] - ID: {video_id}")
            logging.info(f"🔍 [FORMAT DEBUG] - Availability: {availability}")

            if not video_id or video_id == 'unknown':
                raise ValueError(f"Invalid video ID: {video_id}")

            if 'Private video' in title or 'Deleted video' in title:
                raise ValueError(f"Video unavailable: {title}")

            formatted_data = {
                'id': video_id,
                'title': title,
                'webpage_url': video_info.get('webpage_url') or f"https://www.youtube.com/watch?v={video_id}",
                'duration': video_info.get('duration'),
                'uploader': video_info.get('uploader', 'Unknown'),
                'view_count': video_info.get('view_count'),
                'description': (video_info.get('description', '') or '')[:100],
                'availability': availability,
                'source': 'youtube'
            }

            logging.info(f"✅ [FORMAT DEBUG] Successfully formatted: {formatted_data['title']}")
            return formatted_data

        except Exception as e:
            logging.error(f"❌ [FORMAT DEBUG] Error formatting video {video_info.get('id', 'unknown')}: {e}")
            raise

    async def search_playlist(self, playlist_url: str) -> Tuple[Optional[Dict], List[Dict]]:
        """⚡ ULTRA-FAST playlist processing - NO SIZE LIMITS"""
        try:
            loop = asyncio.get_event_loop()

            logging.info(f"🚀 [PLAYLIST] Starting processing: {playlist_url}")

            fast_opts = {
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'skip_download': True,
                'extract_flat': True,
                'socket_timeout': 15,
                'extractor_retries': 2,
                'fragment_retries': 2,
                'geo_bypass': True,
                'geo_bypass_country': None,
                'age_limit': 99,
            }

            if Config.PROXIES:
                proxy = random.choice(Config.PROXIES)
                fast_opts['proxy'] = proxy
                logging.info(f"🌐 Using proxy for playlist: {proxy}")
            elif Config.PROXY_URL:
                fast_opts['proxy'] = Config.PROXY_URL

            cookies_file = getattr(Config, "get_cookies_path", lambda: None)()
            if cookies_file:
                fast_opts['cookiefile'] = cookies_file
                logging.info(f"🍪 Using cookies for playlist: {cookies_file}")
            else:
                logging.warning("⚠️ No cookies for playlist extraction")

            ytdl = yt_dlp.YoutubeDL(fast_opts)  # type: ignore[arg-type]

            logging.info(f"🚀 [PLAYLIST] Using extraction options (no size limit)")

            start_time = time.time()

            try:
                data = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: ytdl.extract_info(playlist_url, download=False)),
                    timeout=30.0  # 30 second timeout
                )
            except asyncio.TimeoutError:
                logging.warning(f"⏰ [PLAYLIST] Timeout after 30s, trying fallback")
                return await self._fallback_playlist_extraction(playlist_url)

            if not data:
                logging.error(f"❌ [PLAYLIST] No data returned")
                return None, []

            playlist_info = {
                'title': data.get('title', 'Unknown Playlist'),
                'uploader': data.get('uploader', 'Unknown'),
                'total_songs': len(data.get('entries', [])),
                'source': 'youtube'
            }

            songs = []
            entries = data.get('entries', [])

            for entry in entries:
                if entry and entry.get('id'):
                    song_data = {
                        'id': entry['id'],
                        'title': entry.get('title', 'Unknown Title'),
                        'webpage_url': entry.get('webpage_url') or f"https://www.youtube.com/watch?v={entry['id']}",
                        'duration': entry.get('duration'),
                        'uploader': entry.get('uploader', 'Unknown'),
                        'source': 'youtube'
                    }
                    songs.append(song_data)

            playlist_info['valid_songs'] = len(songs)
            extraction_time = time.time() - start_time

            logging.info(f"🚀 [PLAYLIST] Completed in {extraction_time:.2f}s: {len(songs)} songs")

            return playlist_info, songs

        except Exception as e:
            logging.error(f"❌ [PLAYLIST] Error: {e}")
            logging.exception('Exception traceback')
            return None, []

    async def _fallback_playlist_extraction(self, playlist_url: str) -> Tuple[Optional[Dict], List[Dict]]:
        """Fallback method - extract just the first few songs"""
        try:
            logging.info(f"🔄 [PLAYLIST FALLBACK] Attempting limited extraction")

            playlist_info = {
                'title': 'YouTube Playlist (Limited)',
                'uploader': 'Unknown',
                'total_songs': 0,
                'valid_songs': 0,
                'source': 'youtube_fallback'
            }

            return playlist_info, []

        except Exception as e:
            logging.error(f"❌ [PLAYLIST FALLBACK] Error: {e}")
            return None, []

    def cleanup(self):
        self._search_pool.clear()
        

try:
    import discord as _discord_mod
    _PCMVolumeTransformer = getattr(_discord_mod, "PCMVolumeTransformer", None)
    _FFmpegPCMAudio = getattr(_discord_mod, "FFmpegPCMAudio", None)
except Exception:
    _PCMVolumeTransformer = None
    _FFmpegPCMAudio = None

if _PCMVolumeTransformer is None:
    class _BaseVolume(object):
        pass
else:
    _BaseVolume = _PCMVolumeTransformer  # type: ignore[assignment]

class YTDLSource(_BaseVolume):
    """Optimized Discord audio source for streaming"""
    def __init__(self, source, *, data, volume=0.5):
        if _PCMVolumeTransformer is not None:
            try:
                super().__init__(source, volume)  # type: ignore[misc]
            except Exception:
                pass
        self.source = source
        self.data = data
        self.title = data.get('title')
        self.url = data.get('webpage_url')
        self.duration = data.get('duration')
        self.uploader = data.get('uploader')
        self._cleaned_up = False

    def cleanup(self):
        if self._cleaned_up:
            return
        logging.info(f"🧹 [YTDLSource.cleanup] Cleaning up source for: {self.title}")
        if hasattr(self.source, 'cleanup'):
            try:
                self.source.cleanup()
                logging.info(f"✅ [YTDLSource.cleanup] Called self.source.cleanup() for: {self.title}")
            except Exception as e:
                logging.error(f"❌ [YTDLSource.cleanup] Error in self.source.cleanup() for {self.title}: {e}")

        base_cleanup = getattr(super(), 'cleanup', None)
        if base_cleanup:
            try:
                base_cleanup()
                logging.info(f"✅ [YTDLSource.cleanup] Called super().cleanup() for: {self.title}")
            except Exception as e:
                logging.error(f"❌ [YTDLSource.cleanup] Error in super().cleanup() for {self.title}: {e}")
        # Defensive: attempt to forcibly terminate any underlying ffmpeg
        # subprocess that may still be running after the normal cleanup.
        try:
            proc = None
            # common attribute names used by wrappers to store the Popen
            for attr in ('process', 'proc', 'popen'):
                proc = getattr(self.source, attr, None)
                if proc:
                    break

            # Some wrappers keep the subprocess on a nested attribute
            if proc is None:
                maybe = getattr(self.source, 'player', None)
                if maybe is not None:
                    proc = getattr(maybe, 'process', None) or getattr(maybe, 'proc', None)

            if proc:
                pid = getattr(proc, 'pid', None)
                logging.info(f"🛑 Forcing termination of ffmpeg subprocess (pid={pid}) for: {self.title}")
                try:
                    if hasattr(proc, 'terminate'):
                        proc.terminate()
                except Exception:
                    pass
                # wait briefly for process to exit
                start = time.time()
                while time.time() - start < 1.0:
                    try:
                        poll = getattr(proc, 'poll', None)
                        if poll and poll() is not None:
                            break
                    except Exception:
                        break
                    time.sleep(0.05)
                # if still alive, try kill
                try:
                    poll = getattr(proc, 'poll', None)
                    if poll and poll() is None and hasattr(proc, 'kill'):
                        proc.kill()
                except Exception:
                    pass
        except Exception:
            logging.exception("Error forcing ffmpeg subprocess termination")
        self._cleaned_up = True

    @classmethod
    async def from_url(cls, url: str, *, loop=None, volume_percent=100, start_time=0):
        try:
            loop = loop or asyncio.get_event_loop()
            handler = youtube_handler
            
            # Get a ytdl instance without a specific format to list available formats
            ytdl_list_formats = handler._get_stream_instance(use_cookies=True)
            # Override format to just get info
            ytdl_list_formats.params['format'] = None 

            data = await loop.run_in_executor(
                None,
                lambda: ytdl_list_formats.extract_info(url, download=False)
            )

            if not data:
                raise Exception(f"Could not extract info from: {url}")
            if 'entries' in data and data['entries']:
                data = data['entries'][0]

            # --- Start of new format selection logic ---
            audio_url = None
            chosen_format = None

            if 'formats' in data and data['formats']:
                candidates = []
                for f in data['formats']:
                    # Basic filtering for audio-only streams with a URL
                    if not f or f.get('acodec') == 'none' or not f.get('url'):
                        continue

                    proto = (f.get('protocol') or '').lower()
                    ext = (f.get('ext') or '').lower()
                    
                    # Deprioritize segmented or problematic formats
                    deprioritize = proto in ('dash', 'f4m', 'rtmp') or ext in ('m3u8', 'm3u8_native') or 'hls' in proto
                    
                    # Prioritize standard HTTP progressive streams
                    preferred_proto = 0 if proto in ('https', 'http', 'https_native') else 1
                    
                    # Get bitrate, fall back to 0 if not available
                    tbr = f.get('tbr') or f.get('abr') or 0
                    
                    candidates.append((deprioritize, preferred_proto, -int(tbr), f))

                # Sort candidates: non-deprioritized first, then by protocol, then by bitrate (highest first)
                if candidates:
                    candidates.sort(key=lambda t: (t[0], t[1], t[2]))
                    chosen_format = candidates[0][-1]
                    audio_url = chosen_format.get('url')
            
            # Fallback if the above logic fails
            if not audio_url and 'url' in data:
                 audio_url = data['url']
                 chosen_format = {'note': 'direct_fallback', 'url': audio_url}

            # --- End of new format selection logic ---

            logging.info(f"🔊 [YTDLSource.from_url] Chosen audio_url present: {bool(audio_url)} for {url}")
            if chosen_format:
                try:
                    logging.info(f"🔊 [YTDLSource.from_url] chosen format protocol={chosen_format.get('protocol')} ext={chosen_format.get('ext')} tbr={chosen_format.get('tbr')}")
                except Exception:
                    pass
            if not _FFmpegPCMAudio:
                raise Exception("FFmpegPCMAudio unavailable")

            if not audio_url:
                raise Exception("No audio URL found for streaming")
            # Use conservative ffmpeg options. Avoid aggressive seeking unless
            # start_time > 0. Add -nostdin and some buffering flags to reduce
            # unexpected seeking behavior on segmented streams.
            before_options = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
            
            # Inject proxy if one was used for extraction
            proxy_url = ytdl_list_formats.params.get('proxy')
            if proxy_url:
                # ffmpeg requires http_proxy option for http/https streams
                before_options += f' -http_proxy "{proxy_url}"'
                logging.info(f"🌐 [FFmpeg] Using proxy: {proxy_url}")

            if start_time and start_time > 0:
                before_options += f' -ss {start_time}'
            options = '-vn -bufsize 1024k -nostdin -hide_banner -loglevel warning'
            logging.info(f"🔊 [YTDLSource.from_url] ffmpeg before_options={before_options} options={options} audio_url_preview={str(audio_url)[:220]}")
            source = _FFmpegPCMAudio(audio_url, before_options=before_options, options=options)  # type: ignore[misc]
            volume = volume_percent / 100.0
            instance = cls(source, data=data, volume=volume)

            

            return instance
        except Exception as e:
            logging.error(f"❌ Error creating YTDLSource: {e}")
            raise

youtube_handler = YouTubeHandlerSingleton()
YouTubeHandler = YouTubeHandlerSingleton
