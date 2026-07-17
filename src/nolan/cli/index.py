"""Video indexing and export commands (index, export, cluster).

Split verbatim from the legacy monolithic CLI module.
"""

import asyncio
import sys
from pathlib import Path

import click

from ._root import main


@main.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--recursive/--no-recursive', default=True,
              help='Scan subdirectories (only applies to directories).')
@click.option('--frame-interval', default=5, type=int,
              help='Seconds between sampled frames (for fixed sampler).')
@click.option('--sampler', '-s', default=None,
              type=click.Choice(['ffmpeg_scene', 'hybrid', 'fixed', 'scene_change']),
              help='Frame sampling strategy. ffmpeg_scene (default) is 10-50x faster.')
@click.option('--vision', default='openrouter',
              type=click.Choice(['openrouter', 'gemini', 'ollama']),
              help='Vision provider for frame analysis. Default: openrouter (qwen/qwen3.7-plus, reasoning off).')
@click.option('--whisper/--no-whisper', default=True,
              help='Auto-generate transcripts with Whisper when no subtitle file exists (default: enabled).')
@click.option('--whisper-model', default='base',
              type=click.Choice(['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3']),
              help='Whisper model size (default: base). Larger = better quality, slower.')
@click.option('--project', '-p', type=str, default=None,
              help='Project slug to associate indexed videos with.')
@click.option('--concurrency', '-c', default=None, type=int,
              help='Max concurrent API calls (defaults to config.indexing.concurrency).')
@click.option('--force', is_flag=True, default=False,
              help='Force reindexing even if video is already indexed.')
@click.pass_context
def index(ctx, path, recursive, frame_interval, sampler, vision, whisper, whisper_model, project, concurrency, force):
    """Index videos for asset matching.

    PATH can be a video file or a directory containing videos.

    This scans video files, samples frames, and uses AI to describe
    what's in each segment. The index is stored locally for fast
    searching during the process command.

    Transcripts are automatically generated with Whisper when no subtitle
    file (.srt, .vtt) exists. Use --no-whisper to disable this.
    Requires ffmpeg for audio extraction.

    Use --project to associate indexed videos with a specific project.
    Create a project first with: nolan projects create "My Project"

    Use --concurrency to control parallel API calls (defaults to config.indexing.concurrency).
    Lower values for rate-limited accounts, higher for paid tiers.
    """
    config = ctx.obj['config']
    input_path = Path(path)

    if concurrency is None:
        concurrency = config.indexing.concurrency

    # Detect if input is a file or directory
    is_single_file = input_path.is_file()

    # Resolve project slug to ID
    project_id = None
    if project:
        from nolan.indexer import VideoIndex
        db_path = Path(config.indexing.database).expanduser()
        idx = VideoIndex(db_path)
        proj = idx.get_project(project)
        if not proj:
            click.echo(f"Error: Project '{project}' not found.")
            click.echo("Create it with: nolan projects create \"Project Name\"")
            click.echo("Or list existing: nolan projects list")
            return
        project_id = proj['id']
        click.echo(f"Project: {proj['name']} ({proj['slug']})")

    # Use CLI sampler or fall back to config default
    sampling_strategy = sampler or config.indexing.sampling_strategy

    if is_single_file:
        click.echo(f"Indexing file: {input_path.name}")
    else:
        click.echo(f"Indexing directory: {input_path}")
        click.echo(f"Recursive: {recursive}")
    click.echo(f"Sampler: {sampling_strategy}")
    click.echo(f"Concurrency: {concurrency}")
    if force:
        click.echo("Force reindex: enabled")

    asyncio.run(_index_videos(config, input_path, recursive, frame_interval, sampling_strategy, vision, whisper, whisper_model, project_id, concurrency, force, is_single_file))


async def _index_videos(config, input_path, recursive, frame_interval, sampling_strategy, vision_provider='ollama', whisper_enabled=False, whisper_model='base', project_id=None, concurrency=10, force=False, is_single_file=False):
    """Async implementation of index command."""
    from nolan.indexer import HybridVideoIndexer, VideoIndex
    from nolan.vision import create_vision_provider, VisionConfig
    from nolan.sampler import create_sampler, SamplerConfig, SamplingStrategy
    from nolan.llm import create_text_llm

    # Initialize database
    db_path = Path(config.indexing.database).expanduser()
    index = VideoIndex(db_path)

    # Determine vision model based on provider
    if vision_provider == "gemini":
        vision_model = "gemini-3-flash-preview"
        api_key = config.gemini.api_key
    elif vision_provider == "openrouter":
        # OpenRouter model slugs contain '/'; fall back to the default if the
        # configured model looks like an Ollama tag (e.g. "qwen3-vl:8b").
        vision_model = config.vision.model if "/" in config.vision.model else "qwen/qwen3.7-plus"
        api_key = config.vision.openrouter_api_key
    else:  # ollama
        vision_model = config.vision.model if "/" not in config.vision.model else "qwen3-vl:8b"
        api_key = None

    # Initialize vision provider
    vision_config = VisionConfig(
        provider=vision_provider,
        model=vision_model,
        host=config.vision.host,
        port=config.vision.port,
        timeout=config.vision.timeout,
        api_key=api_key,
        base_url=config.vision.base_url,
        reasoning_enabled=config.vision.reasoning_enabled,
        reasoning_max_tokens=config.vision.reasoning_max_tokens,
    )
    vision = create_vision_provider(vision_config)

    # Check vision provider connection
    click.echo(f"\nVision provider: {vision_provider} ({vision_model})")
    if not await vision.check_connection():
        click.echo(f"Error: Cannot connect to {vision_provider}. Is it running?")
        return

    # Initialize sampler
    sampler_config = SamplerConfig(
        strategy=SamplingStrategy(sampling_strategy),
        fixed_interval=float(frame_interval),
        min_interval=config.indexing.min_interval,
        max_interval=config.indexing.max_interval,
        scene_threshold=config.indexing.scene_threshold,
        ffmpeg_scene_threshold=getattr(config.indexing, 'ffmpeg_scene_threshold', None),  # None = adaptive 5σ
        ffmpeg_adaptive_sigma=getattr(config.indexing, 'ffmpeg_adaptive_sigma', 5.0),
    )
    sampler = create_sampler(sampler_config)
    click.echo(f"Sampling strategy: {sampling_strategy}")

    # Initialize Whisper transcriber (if enabled)
    whisper_transcriber = None
    if whisper_enabled:
        try:
            from nolan.whisper import WhisperTranscriber, WhisperConfig, check_ffmpeg
            if not check_ffmpeg():
                click.echo("Warning: ffmpeg not found. Whisper transcription disabled.")
            else:
                # Try CUDA first, fall back to CPU
                whisper_config = WhisperConfig(
                    model_size=whisper_model,
                    device='cuda',
                    compute_type='float16'
                )
                try:
                    whisper_transcriber = WhisperTranscriber(whisper_config)
                    # Test if CUDA works by accessing the model
                    _ = whisper_transcriber.model
                    click.echo(f"Whisper: enabled (model: {whisper_model}, device: cuda)")
                except Exception:
                    # Fall back to CPU
                    whisper_config = WhisperConfig(
                        model_size=whisper_model,
                        device='cpu',
                        compute_type='int8'
                    )
                    whisper_transcriber = WhisperTranscriber(whisper_config)
                    click.echo(f"Whisper: enabled (model: {whisper_model}, device: cpu)")
        except ImportError as e:
            click.echo(f"Warning: Whisper unavailable ({e}). Transcription disabled.")

    if not whisper_transcriber:
        click.echo("Whisper: disabled")

    # Initialize LLM for inference (if enabled)
    llm = None
    if config.indexing.enable_inference:
        llm = create_text_llm(config)
        click.echo(f"Inference: enabled ({config.llm.provider}:{config.llm.model})")
    else:
        click.echo("Inference: disabled")

    click.echo(f"Transcript: {'enabled' if config.indexing.enable_transcript else 'disabled'}")

    # Create indexer
    indexer = HybridVideoIndexer(
        vision_provider=vision,
        index=index,
        sampler=sampler,
        llm_client=llm,
        whisper_transcriber=whisper_transcriber,
        enable_transcript=config.indexing.enable_transcript,
        enable_inference=config.indexing.enable_inference,
        project_id=project_id,
        concurrency=concurrency,
        force_reindex=force
    )

    def progress(current, total, message):
        click.echo(f"  [{current}/{total}] {message}")

    if is_single_file:
        # Index single video file
        click.echo(f"\nIndexing single video...")
        segments = await indexer.index_video(input_path, progress_callback=progress)
        stats = {
            'total': 1,
            'indexed': 1 if segments > 0 else 0,
            'skipped': 0 if segments > 0 else 1,
            'segments': segments
        }
    else:
        # Index directory
        click.echo("\nScanning for videos...")
        stats = await indexer.index_directory(input_path, recursive=recursive, progress_callback=progress)

    click.echo(f"\nIndexing complete:")
    click.echo(f"  Videos found: {stats['total']}")
    click.echo(f"  Newly indexed: {stats['indexed']}")
    click.echo(f"  Skipped (unchanged): {stats['skipped']}")
    click.echo(f"  Segments added: {stats['segments']}")
    click.echo(f"\nDatabase: {db_path}")

    # Auto-sync vectors if any videos were indexed
    if stats['indexed'] > 0:
        click.echo("\n[Auto] Syncing vectors for semantic search...")
        try:
            from nolan.vector_search import VectorSearch
            vector_db_path = db_path.parent / "vectors"
            vector_search = VectorSearch(vector_db_path, index=index)

            # Only sync the newly indexed videos (incremental sync handles this via fingerprints)
            def vec_progress(current, total, msg):
                click.echo(f"\r  [{current}/{total}] {msg[:50]:<50}", nl=False)

            result = vector_search.sync_from_index(
                project_id=project_id,
                progress_callback=vec_progress,
                incremental=True
            )
            click.echo()  # newline

            skipped = result.get('skipped', 0)
            if skipped > 0:
                click.echo(f"  Vectors: {result['segments']} segments, {result['clusters']} clusters (skipped {skipped} unchanged)")
            else:
                click.echo(f"  Vectors: {result['segments']} segments, {result['clusters']} clusters")
        except Exception as e:
            click.echo(f"  Warning: Vector sync failed: {e}")
            click.echo("  Run 'nolan sync-vectors' manually to enable semantic search.")


@main.command()
@click.argument('video', type=click.Path(exists=True), required=False)
@click.option('--output', '-o', type=click.Path(), help='Output JSON file path.')
@click.option('--all', 'export_all', is_flag=True, help='Export all indexed videos.')
@click.pass_context
def export(ctx, video, output, export_all):
    """Export indexed video segments to JSON.

    VIDEO is the path to an indexed video file.

    Examples:
        nolan export video.mp4 -o segments.json
        nolan export --all -o library.json
    """
    import json
    from nolan.indexer import VideoIndex

    config = ctx.obj['config']
    db_path = Path(config.indexing.database).expanduser()

    if not db_path.exists():
        click.echo(f"Error: Database not found at {db_path}")
        click.echo("Run 'nolan index' first to index videos.")
        return

    index = VideoIndex(db_path)

    if export_all:
        # Export all videos
        _export_all_videos(index, output)
    elif video:
        # Export single video
        _export_single_video(index, Path(video), output)
    else:
        click.echo("Error: Provide a VIDEO path or use --all flag.")
        return


def _export_single_video(index, video_path: Path, output_path):
    """Export segments for a single video."""
    import json

    # Try both absolute and relative paths
    segments = index.get_segments(str(video_path))
    if not segments:
        segments = index.get_segments(str(video_path.resolve()))
    if not segments:
        # Try matching by filename
        import sqlite3
        with sqlite3.connect(index.db_path) as conn:
            for row in conn.execute('SELECT path FROM videos'):
                if video_path.name in row[0]:
                    segments = index.get_segments(row[0])
                    break

    if not segments:
        click.echo(f"Error: No indexed segments found for {video_path}")
        return

    output = {
        'video': {
            'path': str(video_path),
            'name': video_path.name
        },
        'segments': []
    }

    for seg in segments:
        segment_data = {
            'timestamp_start': seg.timestamp_start,
            'timestamp_end': seg.timestamp_end,
            'timestamp_formatted': seg.timestamp_formatted,
            'duration': seg.duration,
            'frame_description': seg.frame_description,
            'transcript': seg.transcript,
            'combined_summary': seg.combined_summary,
            'inferred_context': seg.inferred_context.to_dict() if seg.inferred_context else None,
            'sample_reason': seg.sample_reason
        }
        output['segments'].append(segment_data)

    # Determine output path
    if output_path is None:
        output_path = video_path.with_suffix('.segments.json')
    else:
        output_path = Path(output_path)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    click.echo(f"Exported {len(segments)} segments to {output_path}")


def _export_all_videos(index, output_path):
    """Export all indexed videos."""
    import json
    import sqlite3

    with sqlite3.connect(index.db_path) as conn:
        videos = [row[0] for row in conn.execute('SELECT path FROM videos')]

    if not videos:
        click.echo("No indexed videos found.")
        return

    output = {'videos': []}

    for video_path in videos:
        segments = index.get_segments(video_path)
        video_data = {
            'path': video_path,
            'name': Path(video_path).name,
            'segments': []
        }

        for seg in segments:
            segment_data = {
                'timestamp_start': seg.timestamp_start,
                'timestamp_end': seg.timestamp_end,
                'timestamp_formatted': seg.timestamp_formatted,
                'duration': seg.duration,
                'frame_description': seg.frame_description,
                'transcript': seg.transcript,
                'combined_summary': seg.combined_summary,
                'inferred_context': seg.inferred_context.to_dict() if seg.inferred_context else None,
                'sample_reason': seg.sample_reason
            }
            video_data['segments'].append(segment_data)

        output['videos'].append(video_data)

    # Determine output path - default to .scratch/ to avoid root clutter
    if output_path is None:
        scratch_dir = Path('.scratch')
        scratch_dir.mkdir(exist_ok=True)
        output_path = scratch_dir / 'library_export.json'
    output_path = Path(output_path)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    total_segments = sum(len(v['segments']) for v in output['videos'])
    click.echo(f"Exported {len(videos)} videos ({total_segments} segments) to {output_path}")


@main.command()
@click.argument('video', type=click.Path(exists=True), required=False)
@click.option('--output', '-o', type=click.Path(), help='Output JSON file path.')
@click.option('--all', 'cluster_all', is_flag=True, help='Cluster all indexed videos.')
@click.option('--summarize/--no-summarize', default=True,
              help='Generate cluster summaries using LLM.')
@click.option('--refine/--no-refine', default=True,
              help='Use LLM to detect story boundaries (default: enabled). Use --no-refine to skip.')
@click.option('--max-gap', default=2.0, type=float,
              help='Maximum time gap (seconds) between segments to consider clustering.')
@click.option('--concurrency', '-c', default=10, type=int,
              help='Max concurrent API calls for summary generation (default 10).')
@click.option('--chunk-size', default=50, type=int,
              help='Segments per batch for boundary detection (default 50).')
@click.option('--overlap', default=15, type=int,
              help='Overlap between chunks for boundary detection (default 15).')
@click.pass_context
def cluster(ctx, video, output, cluster_all, summarize, refine, max_gap, concurrency, chunk_size, overlap):
    """Cluster video segments into story moments.

    VIDEO is the path to an indexed video file.

    Clustering groups continuous segments that share:
    - Same characters/people
    - Same location
    - Related story context

    Examples:
        nolan cluster video.mp4 -o clusters.json
        nolan cluster --all -o all_clusters.json
        nolan cluster video.mp4 --no-refine  # Skip LLM boundary detection (faster)
        nolan cluster video.mp4 -c 15 --chunk-size 40  # Custom settings
    """
    config = ctx.obj['config']
    db_path = Path(config.indexing.database).expanduser()

    if not db_path.exists():
        click.echo(f"Error: Database not found at {db_path}")
        click.echo("Run 'nolan index' first to index videos.")
        return

    if cluster_all:
        asyncio.run(_cluster_all_videos(config, db_path, output, summarize, refine, max_gap, concurrency, chunk_size, overlap))
    elif video:
        asyncio.run(_cluster_video(config, db_path, Path(video), output, summarize, refine, max_gap, concurrency, chunk_size, overlap))
    else:
        click.echo("Error: Provide a VIDEO path or use --all flag.")


async def _cluster_video(config, db_path, video_path, output_path, summarize, refine, max_gap, concurrency, chunk_size, overlap):
    """Cluster segments for a single video."""
    import json
    from nolan.indexer import VideoIndex
    from nolan.clustering import cluster_segments, ClusterAnalyzer, StoryBoundaryDetector

    index = VideoIndex(db_path)

    # Find segments
    segments = index.get_segments(str(video_path))
    if not segments:
        segments = index.get_segments(str(video_path.resolve()))
    if not segments:
        # Try matching by filename
        import sqlite3
        with sqlite3.connect(index.db_path) as conn:
            for row in conn.execute('SELECT path FROM videos'):
                if video_path.name in row[0]:
                    segments = index.get_segments(row[0])
                    break

    if not segments:
        click.echo(f"Error: No indexed segments found for {video_path}")
        return

    click.echo(f"Found {len(segments)} segments")

    # Cluster segments
    click.echo("Clustering segments...")
    clusters = cluster_segments(segments, max_gap=max_gap)
    click.echo(f"Created {len(clusters)} initial clusters")

    # Refine with LLM story boundary detection (smart chunking)
    if refine and config.gemini.api_key:
        click.echo(f"Detecting story boundaries (chunk_size={chunk_size})...")
        from nolan.llm import create_text_llm
        llm = create_text_llm(config)
        detector = StoryBoundaryDetector(llm, chunk_size=chunk_size, overlap=overlap)

        def refine_progress(current, total, msg):
            click.echo(f"  [{current}/{total}] {msg}")

        clusters = await detector.refine_clusters(clusters, progress_callback=refine_progress)
        click.echo(f"Refined to {len(clusters)} clusters")

    # Generate summaries (async batch processing)
    if summarize and config.gemini.api_key:
        click.echo(f"Generating cluster summaries (concurrency={concurrency})...")
        from nolan.llm import create_text_llm
        llm = create_text_llm(config)
        analyzer = ClusterAnalyzer(llm, concurrency=concurrency)

        def summary_progress(current, total, msg):
            click.echo(f"  [{current}/{total}] {msg}")

        clusters = await analyzer.analyze_clusters(clusters, progress_callback=summary_progress)

    # Save clusters to database
    import sqlite3
    # Find video in database by matching path
    video_id = None
    with sqlite3.connect(index.db_path) as conn:
        for row in conn.execute('SELECT id, path FROM videos'):
            if video_path.name in row[1] or str(video_path) == row[1]:
                video_id = row[0]
                break

    if video_id:
        # Clear existing clusters for this video
        with sqlite3.connect(index.db_path) as conn:
            conn.execute("DELETE FROM clusters WHERE video_id = ?", (video_id,))
            conn.commit()

        # Add new clusters
        click.echo("Saving clusters to database...")
        for i, c in enumerate(clusters):
            index.add_cluster(
                video_id=video_id,
                cluster_index=i,
                timestamp_start=c.timestamp_start,
                timestamp_end=c.timestamp_end,
                cluster_summary=c.cluster_summary,
                people=c.people,
                locations=c.locations,
                segment_ids=None
            )

    # Build output
    output = {
        'video': {
            'path': str(video_path),
            'name': video_path.name
        },
        'clustering': {
            'max_gap': max_gap,
            'refined': refine,
            'summarized': summarize
        },
        'clusters': [c.to_dict() for c in clusters]
    }

    # Determine output path
    if output_path is None:
        output_path = video_path.with_suffix('.clusters.json')
    else:
        output_path = Path(output_path)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    click.echo(f"\nExported {len(clusters)} clusters to {output_path}")

    # Print summary
    for c in clusters:
        click.echo(f"  Cluster {c.id}: {c.timestamp_formatted} ({len(c.segments)} segments, {c.duration:.1f}s)")


async def _cluster_all_videos(config, db_path, output_path, summarize, refine, max_gap, concurrency, chunk_size, overlap):
    """Cluster all indexed videos."""
    import json
    import sqlite3
    from nolan.indexer import VideoIndex
    from nolan.clustering import cluster_segments, ClusterAnalyzer, StoryBoundaryDetector

    index = VideoIndex(db_path)

    with sqlite3.connect(db_path) as conn:
        videos = [row[0] for row in conn.execute('SELECT path FROM videos')]

    if not videos:
        click.echo("No indexed videos found.")
        return

    # Setup LLM if needed
    llm = None
    detector = None
    analyzer = None
    if (summarize or refine) and config.gemini.api_key:
        from nolan.llm import create_text_llm
        llm = create_text_llm(config)
        if refine:
            detector = StoryBoundaryDetector(llm, chunk_size=chunk_size, overlap=overlap)
        if summarize:
            analyzer = ClusterAnalyzer(llm, concurrency=concurrency)

    output = {'videos': []}

    for video_path in videos:
        click.echo(f"\nProcessing: {Path(video_path).name}")
        segments = index.get_segments(video_path)

        if not segments:
            click.echo("  No segments found, skipping")
            continue

        # Cluster
        clusters = cluster_segments(segments, max_gap=max_gap)
        click.echo(f"  Created {len(clusters)} initial clusters from {len(segments)} segments")

        # Refine with smart chunking
        if refine and detector:
            clusters = await detector.refine_clusters(clusters)
            click.echo(f"  Refined to {len(clusters)} clusters")

        # Summarize with async batch processing
        if summarize and analyzer:
            clusters = await analyzer.analyze_clusters(clusters)
            click.echo(f"  Generated {len(clusters)} summaries")

        # Save clusters to database
        video_id = index.get_video_id_by_path(video_path)
        if video_id:
            # Clear existing clusters for this video
            with sqlite3.connect(db_path) as conn:
                conn.execute("DELETE FROM clusters WHERE video_id = ?", (video_id,))
                conn.commit()

            # Add new clusters
            for i, c in enumerate(clusters):
                index.add_cluster(
                    video_id=video_id,
                    cluster_index=i,
                    timestamp_start=c.timestamp_start,
                    timestamp_end=c.timestamp_end,
                    cluster_summary=c.cluster_summary,
                    people=c.people,
                    locations=c.locations,
                    segment_ids=None  # Could track segment IDs if needed
                )

        video_data = {
            'path': video_path,
            'name': Path(video_path).name,
            'clusters': [c.to_dict() for c in clusters]
        }
        output['videos'].append(video_data)

    # Save - default to .scratch/ to avoid root clutter
    if output_path is None:
        scratch_dir = Path('.scratch')
        scratch_dir.mkdir(exist_ok=True)
        output_path = scratch_dir / 'library_clusters.json'
    output_path = Path(output_path)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    total_clusters = sum(len(v['clusters']) for v in output['videos'])
    click.echo(f"\nExported {len(videos)} videos ({total_clusters} clusters) to {output_path}")



@main.command()
@click.argument('path', type=str)
@click.option('--delete-file', is_flag=True, default=False,
              help='Also delete the source video FILE from disk (default: keep the file).')
@click.option('--yes', '-y', is_flag=True, default=False, help='Skip the confirmation prompt.')
@click.pass_context
def remove(ctx, path, delete_file, yes):
    """Completely remove ONE ingested video and ALL its derived data from the library.

    PATH is the video's stored path (as shown by the library). Removes its DB rows
    (segments, clusters, shots, saved clips, caches, project links) AND its embedding vectors.
    The source file is KEPT unless --delete-file is given. This is irreversible.
    """
    from nolan.indexer import VideoIndex
    config = ctx.obj['config']
    db_path = Path(config.indexing.database).expanduser()
    index = VideoIndex(db_path)
    vid = index.get_video_id_by_path(path)
    if vid is None:
        click.echo(f"No indexed video at: {path}", err=True)
        sys.exit(1)
    if not yes and not click.confirm(
            f"Delete video {vid} ({path}) and ALL its data"
            + (" + the source FILE" if delete_file else "") + "?"):
        click.echo("Aborted.")
        return
    summary = index.delete_video(vid, delete_file=delete_file)
    # drop the embeddings too (kept out of delete_video so indexer has no Chroma dependency)
    try:
        from nolan.vector_search import VectorSearch
        VectorSearch(db_path=db_path.parent / "vectors", index=index).delete_video_vectors(vid)
        vec = "ok"
    except Exception as e:
        vec = f"skipped ({type(e).__name__}: {e})"
    t = summary.get("tables", {})
    click.echo(f"Removed video {vid}: " + ", ".join(f"{k}={v}" for k, v in t.items()))
    click.echo(f"  vectors: {vec}" + (f"  |  file deleted: {summary.get('file_deleted')}" if delete_file else ""))
