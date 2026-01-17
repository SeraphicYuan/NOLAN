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
            subtitle_langs: Subtitle languages to download (default: ['en']).
        """
        self.output_dir = Path(output_dir) if output_dir else Path.cwd()
        self.format = format or self.DEFAULT_FORMAT
        self.download_subtitles = download_subtitles
        self.subtitle_langs = subtitle_langs or ['en']

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
    ) -> dict:
        """Get yt-dlp options for downloading."""
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

        if self.download_subtitles:
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

    def download(
        self,
        url: str,
        output_template: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ) -> DownloadResult:
        """Download a single video.

        Args:
            url: Video URL.
            output_template: Custom output template (optional).
            progress_callback: Optional callback for progress updates.

        Returns:
            DownloadResult object.
        """
        opts = self._get_download_opts(output_template, progress_callback)

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

        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                # Get info first (for cleanup on failure)
                info = ydl.extract_info(url, download=False)
                video_id = info.get('id', '')
                video_title = info.get('title', 'Unknown')

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
