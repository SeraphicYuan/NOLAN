"""YouTube operations for NOLAN using yt-dlp."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Callable

import yt_dlp


@dataclass
class VideoInfo:
    """Information about a YouTube video."""
    id: str
    title: str
    url: str
    duration: Optional[int] = None  # seconds
    channel: Optional[str] = None
    channel_id: Optional[str] = None
    description: Optional[str] = None
    view_count: Optional[int] = None
    upload_date: Optional[str] = None
    thumbnail: Optional[str] = None
    categories: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    @property
    def duration_formatted(self) -> str:
        """Format duration as HH:MM:SS or MM:SS."""
        if not self.duration:
            return "--:--"
        dur = int(self.duration)
        hours = dur // 3600
        minutes = (dur % 3600) // 60
        seconds = dur % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'duration': self.duration,
            'duration_formatted': self.duration_formatted,
            'channel': self.channel,
            'channel_id': self.channel_id,
            'description': self.description,
            'view_count': self.view_count,
            'upload_date': self.upload_date,
            'thumbnail': self.thumbnail,
            'categories': self.categories,
            'tags': self.tags,
        }


@dataclass
class DownloadResult:
    """Result of a download operation."""
    success: bool
    video_id: str
    title: str
    output_path: Optional[Path] = None
    error: Optional[str] = None
    subtitles_path: Optional[Path] = None


class YouTubeClient:
    """Client for YouTube operations using yt-dlp."""

    # Prefer H.264 (avc1) over AV1 - H.264 is 5x faster to decode for scene detection
    # Falls back to any codec if H.264 not available at desired resolution
    DEFAULT_FORMAT = (
        "bestvideo[height<=720][vcodec^=avc1]+bestaudio/best[height<=720]"
        "/bestvideo[height<=720]+bestaudio/best[height<=720]"
    )

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        format: str = None,
        download_subtitles: bool = True,
        subtitle_langs: List[str] = None,
    ):
        """Initialize YouTube client.

        Args:
            output_dir: Directory to save downloaded videos.
            format: yt-dlp format string (default: H.264 720p, fallback to any codec).
            download_subtitles: Whether to download subtitles.
            subtitle_langs: Subtitle languages to download. Default covers English
                and Chinese (simplified + traditional), incl. region variants.
        """
        self.output_dir = Path(output_dir) if output_dir else Path.cwd()
        self.format = format or self.DEFAULT_FORMAT
        self.download_subtitles = download_subtitles
        # English + Chinese by default. yt-dlp matches these against the video's
        # available subtitle/auto-caption tracks; missing ones are simply skipped.
        self.subtitle_langs = subtitle_langs or [
            'en', 'en-US', 'en-GB',
            'zh', 'zh-Hans', 'zh-Hant', 'zh-CN', 'zh-TW', 'zh-HK',
        ]

    def _get_base_opts(self) -> dict:
        """Get base yt-dlp options."""
        return {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

    def _get_download_opts(
        self,
        output_template: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        with_subtitles: Optional[bool] = None,
    ) -> dict:
        """Get yt-dlp options for downloading.

        Args:
            with_subtitles: Override subtitle download for this attempt. When
                None, falls back to ``self.download_subtitles``. Used to retry a
                download with subtitles disabled after a subtitle rate-limit.
        """
        opts = self._get_base_opts()
        opts.update({
            'format': self.format,
            'outtmpl': output_template or str(self.output_dir / '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
        })

        subtitles = self.download_subtitles if with_subtitles is None else with_subtitles
        if subtitles:
            opts.update({
                'writesubtitles': True,
                'writeautomaticsub': True,  # Auto-generated subs as fallback
                'subtitleslangs': self.subtitle_langs,
                'subtitlesformat': 'srt/vtt/best',
            })

        if progress_callback:
            opts['progress_hooks'] = [progress_callback]

        return opts

    def search(
        self,
        query: str,
        limit: int = 10,
        progress_callback: Optional[Callable] = None,
    ) -> List[VideoInfo]:
        """Search YouTube for videos.

        Args:
            query: Search query.
            limit: Maximum number of results.
            progress_callback: Optional callback for progress updates.

        Returns:
            List of VideoInfo objects.
        """
        search_url = f"ytsearch{limit}:{query}"

        opts = self._get_base_opts()
        opts['extract_flat'] = 'in_playlist'  # Don't download, just get info

        results = []

        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(search_url, download=False)
                entries = info.get('entries', [])

                for entry in entries:
                    if entry:
                        video = VideoInfo(
                            id=entry.get('id', ''),
                            title=entry.get('title', 'Unknown'),
                            url=entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}",
                            duration=entry.get('duration'),
                            channel=entry.get('channel') or entry.get('uploader'),
                            channel_id=entry.get('channel_id'),
                            view_count=entry.get('view_count'),
                        )
                        results.append(video)

                        if progress_callback:
                            progress_callback(len(results), limit)

            except Exception as e:
                raise RuntimeError(f"Search failed: {e}")

        return results

    def get_info(self, url: str) -> VideoInfo:
        """Get information about a video without downloading.

        Args:
            url: Video URL.

        Returns:
            VideoInfo object.
        """
        opts = self._get_base_opts()

        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)

                return VideoInfo(
                    id=info.get('id', ''),
                    title=info.get('title', 'Unknown'),
                    url=info.get('webpage_url', url),
                    duration=info.get('duration'),
                    channel=info.get('channel') or info.get('uploader'),
                    channel_id=info.get('channel_id'),
                    description=info.get('description'),
                    view_count=info.get('view_count'),
                    upload_date=info.get('upload_date'),
                    thumbnail=info.get('thumbnail'),
                    categories=info.get('categories', []),
                    tags=info.get('tags', []),
                )

            except Exception as e:
                raise RuntimeError(f"Failed to get video info: {e}")

    def _cleanup_temp_files(self, title: str) -> None:
        """Clean up temporary files left by yt-dlp after download.

        Only removes yt-dlp fragment/intermediate files, NOT legitimate videos.
        Fragment files have patterns like: .f247.webm, .f251-11.webm, .part, .temp.mp4

        Args:
            title: Video title to match files against.
        """
        import re

        if not self.output_dir.exists():
            return

        # Pattern for yt-dlp fragment files (must match to delete)
        # e.g., .f247.webm, .f251-11.webm, .f140.m4a
        fragment_pattern = re.compile(r'\.f\d+(-\d+)?\.(webm|m4a|mp4)$')

        # Other temp file extensions (always delete if matched)
        temp_extensions = ['.part', '.ytdl']

        # Temp file patterns in filename
        temp_patterns = ['.temp.']

        for file_path in self.output_dir.iterdir():
            if not file_path.is_file():
                continue

            filename = file_path.name

            # Check if this file belongs to the downloaded video
            # (title may have special chars replaced, so be flexible)
            title_words = title.lower().split()[:3]  # First 3 words
            filename_lower = filename.lower()

            # Match if first few title words appear in filename
            matches_title = all(word in filename_lower for word in title_words if len(word) > 2)

            if not matches_title:
                continue

            should_delete = False

            # Check for yt-dlp fragment pattern (e.g., .f247.webm)
            if fragment_pattern.search(filename):
                should_delete = True

            # Check temp extensions (.part, .ytdl)
            if any(filename.endswith(ext) for ext in temp_extensions):
                should_delete = True

            # Check temp patterns (.temp.)
            if any(pattern in filename for pattern in temp_patterns):
                should_delete = True

            # Safety: Never delete final outputs
            if filename.endswith('.mp4') and not fragment_pattern.search(filename):
                should_delete = False
            if filename.endswith('.srt') or filename.endswith('.vtt'):
                should_delete = False

            if should_delete:
                try:
                    file_path.unlink()
                except Exception:
                    pass  # Ignore cleanup errors

    @staticmethod
    def _is_subtitle_error(error: str) -> bool:
        """True if a download error is about subtitles (not the video itself).

        YouTube rate-limits the subtitle/timedtext endpoint independently of the
        video stream, so a 429 (or other failure) while fetching subtitles
        should not be fatal — the video is what matters and Whisper can
        transcribe it afterwards.
        """
        e = (error or "").lower()
        return "subtitle" in e or "timedtext" in e

    def _pick_subtitle_langs(self, info: dict) -> List[str]:
        """Choose subtitle languages matching the video's original language.

        yt-dlp exposes the native language as ``info['language']`` and the tracks
        actually available under ``subtitles`` / ``automatic_captions``. We pick
        only the tracks whose base language matches the video's original language
        (e.g. an English video → English subtitles only). This avoids requesting
        languages that don't exist and the 429 rate-limit that comes from
        fetching many tracks at once. Falls back to the configured list when the
        language can't be determined.
        """
        available = set((info.get('subtitles') or {}).keys())
        available |= set((info.get('automatic_captions') or {}).keys())

        detected = (info.get('language') or '').strip()
        if detected:
            base = detected.split('-')[0].lower()
            matches = [l for l in available if l.split('-')[0].lower() == base]
            # Prefer available tracks in the original language; otherwise request
            # the detected code directly and let yt-dlp skip if absent.
            return matches or [detected]

        # Language unknown: keep only configured langs that actually exist, or
        # fall back to the full configured list if availability is unknown too.
        matches = [l for l in self.subtitle_langs if l in available]
        return matches or self.subtitle_langs

    def download(
        self,
        url: str,
        output_template: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ) -> DownloadResult:
        """Download a single video.

        If a download fails because of a subtitle error (e.g. YouTube returns
        HTTP 429 on the subtitle endpoint), it retries once with subtitles
        disabled so the video still downloads; the indexer's Whisper fallback
        then handles transcription.

        Args:
            url: Video URL.
            output_template: Custom output template (optional).
            progress_callback: Optional callback for progress updates.

        Returns:
            DownloadResult object.
        """
        result = self._download_once(url, output_template, progress_callback)
        if (not result.success and self.download_subtitles
                and self._is_subtitle_error(result.error or "")):
            # Subtitle endpoint failed (commonly a 429 rate-limit). Retry the
            # download without subtitles — Whisper fallback covers transcription.
            result = self._download_once(
                url, output_template, progress_callback, with_subtitles=False
            )
            if result.success:
                result.error = None
        return result

    def _download_once(
        self,
        url: str,
        output_template: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        with_subtitles: Optional[bool] = None,
    ) -> DownloadResult:
        """Perform a single download attempt (see ``download`` for retry logic)."""
        opts = self._get_download_opts(output_template, progress_callback, with_subtitles)

        # Track the actual output file
        downloaded_file = None
        video_title = None

        def track_filename(d):
            nonlocal downloaded_file
            if d['status'] == 'finished':
                downloaded_file = d.get('filename')

        if 'progress_hooks' not in opts:
            opts['progress_hooks'] = []
        opts['progress_hooks'].append(track_filename)

        subs_enabled = self.download_subtitles if with_subtitles is None else with_subtitles

        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                # Get info first (for cleanup on failure)
                info = ydl.extract_info(url, download=False)
                video_id = info.get('id', '')
                video_title = info.get('title', 'Unknown')

                # Narrow subtitle requests to the video's original language only.
                # Requesting every configured language hammers YouTube's subtitle
                # endpoint and triggers HTTP 429; one language is enough.
                if subs_enabled:
                    ydl.params['subtitleslangs'] = self._pick_subtitle_langs(info)

                # Now download
                info = ydl.extract_info(url, download=True)

                # Determine output path
                if downloaded_file:
                    output_path = Path(downloaded_file)
                    # yt-dlp might have changed extension during merge
                    if not output_path.exists():
                        output_path = output_path.with_suffix('.mp4')
                else:
                    output_path = self.output_dir / f"{video_title}.mp4"

                # Check for subtitles
                subtitles_path = None
                for lang in self.subtitle_langs:
                    for ext in ['.srt', '.vtt', f'.{lang}.srt', f'.{lang}.vtt']:
                        sub_path = output_path.with_suffix(ext)
                        if sub_path.exists():
                            subtitles_path = sub_path
                            break
                    if subtitles_path:
                        break

                # Clean up temp files
                if video_title:
                    self._cleanup_temp_files(video_title)

                return DownloadResult(
                    success=True,
                    video_id=video_id,
                    title=video_title,
                    output_path=output_path if output_path.exists() else None,
                    subtitles_path=subtitles_path,
                )

            except Exception as e:
                # Still try to clean up on failure
                if video_title:
                    self._cleanup_temp_files(video_title)

                return DownloadResult(
                    success=False,
                    video_id='',
                    title=video_title or '',
                    error=str(e),
                )

    def download_batch(
        self,
        urls: List[str],
        progress_callback: Optional[Callable] = None,
    ) -> List[DownloadResult]:
        """Download multiple videos.

        Args:
            urls: List of video URLs.
            progress_callback: Optional callback(current, total, result).

        Returns:
            List of DownloadResult objects.
        """
        results = []

        for i, url in enumerate(urls):
            result = self.download(url)
            results.append(result)

            if progress_callback:
                progress_callback(i + 1, len(urls), result)

        return results

    def download_from_file(
        self,
        file_path: Path,
        progress_callback: Optional[Callable] = None,
    ) -> List[DownloadResult]:
        """Download videos from a file containing URLs (one per line).

        Args:
            file_path: Path to file with URLs.
            progress_callback: Optional callback(current, total, result).

        Returns:
            List of DownloadResult objects.
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"URL file not found: {file_path}")

        urls = []
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith('#'):
                    urls.append(line)

        return self.download_batch(urls, progress_callback)

    def download_playlist(
        self,
        playlist_url: str,
        limit: Optional[int] = None,
        progress_callback: Optional[Callable] = None,
    ) -> List[DownloadResult]:
        """Download videos from a playlist.

        Args:
            playlist_url: Playlist URL.
            limit: Maximum number of videos to download (None for all).
            progress_callback: Optional callback(current, total, result).

        Returns:
            List of DownloadResult objects.
        """
        # First, get playlist info
        opts = self._get_base_opts()
        opts['extract_flat'] = 'in_playlist'

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            entries = info.get('entries', [])

        # Get video URLs
        urls = []
        for entry in entries:
            if entry:
                video_url = entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}"
                urls.append(video_url)
                if limit and len(urls) >= limit:
                    break

        return self.download_batch(urls, progress_callback)

    def fetch_transcript(self, url: str, out_dir: Optional[Path] = None) -> dict:
        """Fetch a video's original-language transcript WITHOUT the video.

        Downloads only the subtitle track (yt-dlp ``skip_download``), restricted
        to the video's original language (reusing ``_pick_subtitle_langs``), and
        parses it to plain text via ``TranscriptLoader``.

        Returns:
            dict with video_id, title, channel, upload_date, language, text.

        Raises:
            RuntimeError if no transcript is available for the video.
        """
        import tempfile
        from nolan.transcript import TranscriptLoader

        out_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp())
        out_dir.mkdir(parents=True, exist_ok=True)

        opts = self._get_base_opts()
        opts.update({
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitlesformat': 'srt/vtt/best',
            'outtmpl': str(out_dir / '%(id)s.%(ext)s'),
        })

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            # Transcript only needs ONE track — the original language. Requesting
            # the whole matched set (incl. auto-translations like 'en-de') wastes
            # requests and invites HTTP 429.
            langs = self._pick_subtitle_langs(info)
            detected = info.get('language')
            if detected and detected in langs:
                langs = [detected]
            elif langs:
                langs = [sorted(langs)[0]]
            ydl.params['subtitleslangs'] = langs
            ydl.extract_info(url, download=True)  # writes subtitle files only

        video_id = info.get('id', '')
        subs = sorted(out_dir.glob(f"{video_id}*.srt")) + sorted(out_dir.glob(f"{video_id}*.vtt"))
        if not subs:
            raise RuntimeError(
                f"no transcript available for '{info.get('title') or url}' "
                f"(no subtitles or auto-captions in the original language)"
            )
        transcript = TranscriptLoader.load(subs[0])
        return {
            "video_id": video_id,
            "title": info.get("title"),
            "channel": info.get("channel") or info.get("uploader"),
            "upload_date": info.get("upload_date"),  # YYYYMMDD
            "language": info.get("language"),
            "text": transcript.full_text,
        }

    @staticmethod
    def channel_videos_url(channel: str) -> str:
        """Normalize a channel reference to its uploads/videos tab URL.

        Accepts a full URL, an @handle, a UC… channel id, or a bare handle.
        """
        c = (channel or "").strip()
        if c.startswith("http://") or c.startswith("https://"):
            if any(k in c for k in ("/videos", "/watch", "list=", "/streams", "/shorts")):
                return c
            return c.rstrip("/") + "/videos"
        if c.startswith("@"):
            return f"https://www.youtube.com/{c}/videos"
        if re.fullmatch(r"UC[0-9A-Za-z_-]{22}", c):
            return f"https://www.youtube.com/channel/{c}/videos"
        return f"https://www.youtube.com/@{c}/videos"

    def list_channel_videos(self, channel: str, limit: Optional[int] = None) -> List[dict]:
        """Enumerate a channel's videos (newest first), without downloading.

        Uses flat extraction (fast). Note: flat entries often lack ``upload_date``
        — callers that need dates should probe per-video via ``get_info``.

        Returns:
            List of dicts: {video_id, url, title, upload_date}.
        """
        url = self.channel_videos_url(channel)
        opts = self._get_base_opts()
        opts['extract_flat'] = 'in_playlist'
        if limit:
            opts['playlistend'] = int(limit)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            entries = [e for e in (info.get('entries') or []) if e]
        out = []
        for e in entries:
            vid = e.get('id')
            if not vid:
                continue
            out.append({
                "video_id": vid,
                "url": e.get('url') or f"https://www.youtube.com/watch?v={vid}",
                "title": e.get('title'),
                "upload_date": e.get('upload_date'),  # often None in flat mode
            })
        return out


def extract_video_id(url: str) -> Optional[str]:
    """Extract video ID from a YouTube URL.

    Args:
        url: YouTube URL.

    Returns:
        Video ID or None if not found.
    """
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/v/([a-zA-Z0-9_-]{11})',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def is_youtube_url(url: str) -> bool:
    """Check if a URL is a YouTube URL.

    Args:
        url: URL to check.

    Returns:
        True if YouTube URL.
    """
    return bool(re.search(r'(youtube\.com|youtu\.be)', url))


def is_playlist_url(url: str) -> bool:
    """Check if a URL is a YouTube playlist URL.

    Args:
        url: URL to check.

    Returns:
        True if playlist URL.
    """
    return bool(re.search(r'(youtube\.com/playlist|list=)', url))
