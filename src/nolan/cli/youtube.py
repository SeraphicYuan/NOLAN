"""YouTube download utilities (yt-download, yt-search, yt-info).

Split verbatim from the legacy monolithic CLI module.
"""

import asyncio
import sys
from pathlib import Path

import click

from ._root import main


@main.command('yt-download')
@click.argument('url_or_file')
@click.option('--output', '-o', type=click.Path(), default='.scratch/downloads',
              help='Output directory for downloaded videos (default: .scratch/downloads).')
@click.option('--format', '-f', 'video_format', default='bestvideo[height<=720]+bestaudio/best[height<=720]',
              help='yt-dlp format string.')
@click.option('--subtitles/--no-subtitles', default=True,
              help='Download subtitles.')
@click.option('--langs', '-l', default='en',
              help='Subtitle languages (comma-separated).')
@click.option('--playlist', is_flag=True,
              help='Download entire playlist.')
@click.option('--limit', type=int, default=None,
              help='Limit playlist downloads to N videos.')
@click.pass_context
def yt_download(ctx, url_or_file, output, video_format, subtitles, langs, playlist, limit):
    """Download YouTube videos using yt-dlp.

    URL_OR_FILE can be:
      - A YouTube video URL
      - A YouTube playlist URL (use --playlist)
      - A text file with URLs (one per line)

    Examples:

      nolan yt-download "https://youtube.com/watch?v=xxxxx"

      nolan yt-download urls.txt -o ./videos

      nolan yt-download "https://youtube.com/playlist?list=xxxxx" --playlist --limit 10

      nolan yt-download "https://youtube.com/watch?v=xxxxx" -f "bestvideo[height<=1080]+bestaudio"
    """
    from nolan.youtube import YouTubeClient, is_youtube_url, is_playlist_url

    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    subtitle_langs = [l.strip() for l in langs.split(',')]

    client = YouTubeClient(
        output_dir=output_path,
        format=video_format,
        download_subtitles=subtitles,
        subtitle_langs=subtitle_langs,
    )

    url_or_file_path = Path(url_or_file)

    def progress_callback(current, total, result):
        status = "OK" if result.success else f"FAILED: {result.error}"
        click.echo(f"  [{current}/{total}] {result.title[:50]}... {status}")

    if url_or_file_path.exists() and url_or_file_path.is_file():
        # Download from file
        click.echo(f"Downloading from file: {url_or_file_path}")
        click.echo(f"Output: {output_path}")
        results = client.download_from_file(url_or_file_path, progress_callback=progress_callback)
    elif playlist or is_playlist_url(url_or_file):
        # Download playlist
        click.echo(f"Downloading playlist: {url_or_file}")
        click.echo(f"Output: {output_path}")
        if limit:
            click.echo(f"Limit: {limit} videos")
        results = client.download_playlist(url_or_file, limit=limit, progress_callback=progress_callback)
    elif is_youtube_url(url_or_file):
        # Download single video
        click.echo(f"Downloading: {url_or_file}")
        click.echo(f"Output: {output_path}")

        def single_progress(d):
            if d['status'] == 'downloading':
                pct = d.get('_percent_str', '?%')
                speed = d.get('_speed_str', '?')
                click.echo(f"\r  {pct} at {speed}", nl=False)
            elif d['status'] == 'finished':
                click.echo(f"\r  Download complete, processing...")

        result = client.download(url_or_file, progress_callback=single_progress)
        results = [result]
    else:
        click.echo(f"Error: '{url_or_file}' is not a valid YouTube URL or file.")
        return

    # Summary
    success = sum(1 for r in results if r.success)
    failed = len(results) - success

    click.echo(f"\nDownloaded {success}/{len(results)} videos")
    if failed > 0:
        click.echo(f"Failed: {failed}")
        for r in results:
            if not r.success:
                click.echo(f"  - {r.error}")

    for r in results:
        if r.success and r.output_path:
            click.echo(f"  {r.output_path}")


@main.command('yt-search')
@click.argument('query')
@click.option('--limit', '-n', type=int, default=10,
              help='Maximum number of results.')
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Output JSON file for results.')
@click.option('--download', '-d', is_flag=True,
              help='Download the first result.')
@click.option('--download-dir', type=click.Path(), default='./downloads',
              help='Directory for downloaded videos (with --download).')
@click.pass_context
def yt_search(ctx, query, limit, output, download, download_dir):
    """Search YouTube for videos.

    QUERY is the search term.

    Examples:

      nolan yt-search "python tutorial"

      nolan yt-search "machine learning" -n 20 -o results.json

      nolan yt-search "documentary" --download
    """
    import json
    from nolan.youtube import YouTubeClient

    client = YouTubeClient()

    click.echo(f"Searching: {query}")
    click.echo(f"Limit: {limit}")

    def progress(current, total):
        click.echo(f"\r  Found {current}/{total}...", nl=False)

    try:
        results = client.search(query, limit=limit, progress_callback=progress)
        click.echo()  # newline after progress

        if not results:
            click.echo("No results found.")
            return

        click.echo(f"\nFound {len(results)} videos:\n")

        for i, video in enumerate(results, 1):
            duration = video.duration_formatted
            views = f"{int(video.view_count):,}" if video.view_count else "?"
            click.echo(f"  {i}. [{duration}] {video.title[:60]}")
            click.echo(f"     Channel: {video.channel or 'Unknown'} | Views: {views}")
            click.echo(f"     {video.url}")
            click.echo()

        # Save to JSON if requested
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_data = {
                "query": query,
                "count": len(results),
                "results": [v.to_dict() for v in results],
            }
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            click.echo(f"Results saved to: {output_path}")

        # Download first result if requested
        if download and results:
            click.echo("\nDownloading first result...")
            download_path = Path(download_dir)
            download_path.mkdir(parents=True, exist_ok=True)

            download_client = YouTubeClient(output_dir=download_path)
            result = download_client.download(results[0].url)

            if result.success:
                click.echo(f"Downloaded: {result.output_path}")
            else:
                click.echo(f"Download failed: {result.error}")

    except Exception as e:
        click.echo(f"Error: {e}")


@main.command('yt-info')
@click.argument('url')
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Output JSON file for video info.')
@click.pass_context
def yt_info(ctx, url, output):
    """Get information about a YouTube video.

    URL is the YouTube video URL.

    Examples:

      nolan yt-info "https://youtube.com/watch?v=xxxxx"

      nolan yt-info "https://youtube.com/watch?v=xxxxx" -o video_info.json
    """
    import json
    from nolan.youtube import YouTubeClient

    client = YouTubeClient()

    click.echo(f"Fetching info: {url}")

    try:
        info = client.get_info(url)

        click.echo(f"\nTitle: {info.title}")
        click.echo(f"Channel: {info.channel or 'Unknown'}")
        click.echo(f"Duration: {info.duration_formatted}")
        click.echo(f"Views: {int(info.view_count):,}" if info.view_count else "Views: Unknown")
        click.echo(f"Upload date: {info.upload_date or 'Unknown'}")
        click.echo(f"URL: {info.url}")

        if info.description:
            desc = info.description[:200] + "..." if len(info.description) > 200 else info.description
            click.echo(f"\nDescription:\n{desc}")

        if info.tags:
            click.echo(f"\nTags: {', '.join(info.tags[:10])}")

        if info.categories:
            click.echo(f"Categories: {', '.join(info.categories)}")

        # Save to JSON if requested
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(info.to_dict(), f, indent=2, ensure_ascii=False)
            click.echo(f"\nInfo saved to: {output_path}")

    except Exception as e:
        click.echo(f"Error: {e}")


