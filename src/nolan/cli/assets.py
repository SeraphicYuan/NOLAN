"""Asset sourcing and matching commands (image-search, extract-assets, match-broll, match-clips, cutout, broll, acquire-review).

Split verbatim from the legacy monolithic CLI module.
"""

import asyncio
import sys
from pathlib import Path

import click

from ._root import main


def _scoring_vision_config(config, vision: str) -> dict:
    """Build the ImageScorer vision_config dict for the chosen provider."""
    if vision == "gemini":
        return {"api_key": config.gemini.api_key, "model": "gemini-3-flash-preview"}
    if vision == "openrouter":
        model = config.vision.model if "/" in config.vision.model else "qwen/qwen3.7-plus"
        return {
            "api_key": config.vision.openrouter_api_key,
            "model": model,
            "base_url": config.vision.base_url,
            "reasoning_enabled": config.vision.reasoning_enabled,
            "reasoning_max_tokens": config.vision.reasoning_max_tokens,
        }
    # ollama
    return {
        "host": config.vision.host,
        "port": config.vision.port,
        "model": config.vision.model if "/" not in config.vision.model else "qwen3-vl:8b",
    }


@main.command('image-search')
@click.argument('query')
@click.option('--source', '-s', type=click.Choice(['ddgs', 'pexels', 'pixabay', 'wikimedia', 'smithsonian', 'loc', 'wellcome', 'europeana', 'dpla', 'artvee', 'all']),
              default='ddgs', help='Image source to search.')
@click.option('--output', '-o', type=click.Path(), default='.scratch/image_search_results.json',
              help='Output JSON file for results (default: .scratch/image_search_results.json).')
@click.option('--max-results', '-n', type=int, default=10,
              help='Maximum number of results per source.')
@click.option('--score/--no-score', default=False,
              help='Score images by relevance using vision model.')
@click.option('--vision', type=click.Choice(['openrouter', 'gemini', 'ollama']),
              default='openrouter', help='Vision provider for scoring. Default: openrouter (qwen/qwen3.7-plus).')
@click.option('--context', '-c', type=str, default=None,
              help='Additional context for scoring (e.g., "for a documentary about history").')
@click.option('--resolve/--no-resolve', default=False,
              help='Upgrade thumbnails to full-res by extracting from each result\'s source page '
                   '(useful for aggregators like DPLA that return previews).')
@click.option('--save/--no-save', default=False,
              help='Save results into the picture library (tagged with the query).')
@click.option('--scope', type=click.Choice(['global', 'project']), default='global',
              help='Picture-library scope when --save is used.')
@click.option('--project', '-p', default=None, help='Project name (for --scope project).')
@click.pass_context
def image_search(ctx, query, source, output, max_results, score, vision, context, resolve, save, scope, project):
    """Search for images from various sources.

    QUERY is the search term for finding images.

    Sources:
      - ddgs: DuckDuckGo image search (no API key needed)
      - pexels: Pexels stock photos (requires PEXELS_API_KEY)
      - pixabay: Pixabay stock photos (requires PIXABAY_API_KEY)
      - wikimedia: Wikimedia Commons (no API key needed, public domain)
      - smithsonian: Smithsonian Open Access (requires SMITHSONIAN_API_KEY, CC0)
      - loc: Library of Congress (no API key needed, public domain)
      - wellcome: Wellcome Collection (no API key needed, CC/PD history & medicine)
      - europeana: Europeana EU cultural heritage (needs EUROPEANA_API_KEY)
      - dpla: Digital Public Library of America (needs DPLA_API_KEY)
      - all: Search all available sources

    Scoring:
      Use --score to rank images by relevance using a vision model.
      Use --vision to choose 'openrouter' (default), 'gemini', or 'ollama'.

    Examples:

      nolan image-search "sunset mountains"

      nolan image-search "sunset mountains" -s wikimedia -n 20

      nolan image-search "historical photographs" -s loc

      nolan image-search "sunset mountains" -s all -o results.json

      nolan image-search "sunset mountains" --score --vision gemini
    """
    config = ctx.obj['config']
    output_path = Path(output)

    from nolan.image_search import ImageSearchClient, ImageScorer

    # Initialize client with API keys from config
    client = ImageSearchClient(
        pexels_api_key=config.image_sources.pexels_api_key,
        pixabay_api_key=config.image_sources.pixabay_api_key,
        smithsonian_api_key=config.image_sources.smithsonian_api_key,
        keys=config.image_sources.provider_keys(),
    )

    # Show available providers
    available = client.get_available_providers()
    click.echo(f"Available sources: {', '.join(available)}")

    if source != "all" and source not in available:
        click.echo(f"Error: Source '{source}' is not available. Check API keys.")
        return

    click.echo(f"Searching '{query}' on {source}...")

    try:
        results = client.search(query, source, max_results)
        click.echo(f"Found {len(results)} results")

        # Upgrade thumbnails -> full-res via the extractor registry
        if resolve and results:
            click.echo("\nResolving full-res from source pages...")
            from nolan.extractors import resolve_results
            before = [r.url for r in results]
            results = resolve_results(results)
            upgraded = sum(1 for old, r in zip(before, results) if r.url != old)
            click.echo(f"Upgraded {upgraded}/{len(results)} to full-res.")

        # Score images if requested
        if score:
            click.echo(f"\nScoring images with {vision}...")

            # Configure vision provider
            vision_config = _scoring_vision_config(config, vision)

            scorer = ImageScorer(vision_provider=vision, vision_config=vision_config)

            def progress(current, total, result):
                score_str = f"{result.score:.1f}" if result.score else "?"
                quality_str = f" Q:{result.quality_score:.0f}" if result.quality_score is not None else ""
                click.echo(f"  [{current}/{total}] Score: {score_str}{quality_str} - {result.title[:40] if result.title else 'No title'}...")

            results = scorer.score_results(results, query, context=context, progress_callback=progress)
            click.echo(f"\nScoring complete. Results sorted by relevance.")

        # Save results to JSON
        import json
        output_data = {
            "query": query,
            "source": source,
            "count": len(results),
            "scored": score,
            "scored_by": vision if score else None,
            "context": context,
            "results": [r.to_dict() for r in results],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        click.echo(f"\nResults saved to: {output_path}")

        # Save into the picture library (tagged with the query)
        if save and results:
            from nolan.imagelib import ImageLibrary
            lib = ImageLibrary(scope=scope, project=project)
            click.echo(f"\nSaving to {scope} picture library...")
            added = dup = failed = 0
            for r in results:
                if not r.url:
                    continue
                try:
                    _, created = lib.add_result(r, query=query)
                    added += int(created); dup += int(not created)
                except Exception:
                    failed += 1
            click.echo(f"Library: +{added} new, {dup} duplicate, {failed} failed.")

        # Show results
        for i, r in enumerate(results[:5]):
            score_str = f" (Score: {r.score:.1f}" if r.score is not None else ""
            if score_str and r.quality_score is not None:
                score_str += f", Quality: {r.quality_score:.0f}/10)"
            elif score_str:
                score_str += ")"
            click.echo(f"  {i+1}. [{r.source}]{score_str} {r.title[:50] if r.title else 'No title'}...")
            if r.score_reason:
                click.echo(f"     Relevance: {r.score_reason}")
            if r.quality_reason:
                click.echo(f"     Quality: {r.quality_reason}")
            click.echo(f"     {r.url[:80]}...")

        if len(results) > 5:
            click.echo(f"  ... and {len(results) - 5} more")

    except Exception as e:
        click.echo(f"Error: {e}")


@main.command('artvee')
@click.argument('query', required=False, default=None)
@click.option('--artist', '-a', default=None,
              help='Artist name or slug — searches their canonical /artist/ page.')
@click.option('--sort', type=click.Choice(['relevance', 'year', 'title', 'artist', 'pixels', 'filesize']),
              default='relevance', help='Sort order for filtered results.')
@click.option('--desc/--asc', default=False, help='Sort descending (default ascending).')
@click.option('--category', '-c', multiple=True,
              help='Keep only these categories/genres (repeatable), e.g. -c Mythology.')
@click.option('--year-min', type=int, default=None, help='Minimum year.')
@click.option('--year-max', type=int, default=None, help='Maximum year.')
@click.option('--orientation', type=click.Choice(['portrait', 'landscape', 'square']), default=None)
@click.option('--min-width', type=int, default=None, help='Minimum standard-download width (px).')
@click.option('--min-megapixels', type=float, default=None, help='Minimum SD megapixels.')
@click.option('--exclude-anonymous/--include-anonymous', default=False,
              help='Drop unattributed / "Anonymous" works.')
@click.option('--max-results', '-n', type=int, default=20, help='Max results after filtering.')
@click.option('--scan-limit', type=int, default=120,
              help='Raw results to pull before filtering (give picky filters room).')
@click.option('--download', '-d', 'download_dir', type=click.Path(), default=None,
              help='Download the low-res (SDL) image of each result into this directory.')
@click.option('--output', '-o', type=click.Path(), default='.scratch/artvee_results.json',
              help='JSON output file for the metadata (default: .scratch/artvee_results.json).')
def artvee(query, artist, sort, desc, category, year_min, year_max, orientation,
           min_width, min_megapixels, exclude_anonymous, max_results, scan_limit,
           download_dir, output):
    """Search Artvee (public-domain fine art) with advanced metadata filters.

    Provide a QUERY (keyword) and/or --artist. Results carry full metadata
    (artist, year, genre, dimensions, file sizes) parsed from the listing — no
    per-item page fetch is needed until --download resolves the presigned link.

    Examples:

      nolan artvee athena --orientation landscape --year-max 1900 --sort year --desc

      nolan artvee --artist "William Etty" -n 40

      nolan artvee "sea storm" -c Marine --min-width 1500 -d .scratch/art
    """
    import json
    from pathlib import Path
    from nolan.artvee import ArtveeClient, ArtveeFilter

    if not query and not artist:
        raise click.UsageError("Provide a QUERY and/or --artist.")

    flt = ArtveeFilter(
        categories=list(category) or None,
        year_min=year_min, year_max=year_max,
        orientation=orientation, min_width=min_width,
        min_megapixels=min_megapixels, exclude_anonymous=exclude_anonymous,
    )
    with ArtveeClient() as cli:
        click.echo(f"Searching Artvee: query={query!r} artist={artist!r} ...")
        results = cli.advanced_search(
            query, artist=artist, filters=flt, sort_by=sort, descending=desc,
            max_results=max_results, scan_limit=scan_limit)
        click.echo(f"Found {len(results)} matching artworks.\n")
        for i, r in enumerate(results, 1):
            yr = r.year if r.year is not None else "----"
            dims = f"{r.sd_width}x{r.sd_height}" if r.sd_width else "?"
            click.echo(f"  {i:>2}. [{yr}] {r.title[:52]}")
            click.echo(f"       {r.artist or 'Unknown'} · {r.category or '-'} · "
                       f"{dims} {r.orientation or ''} · {r.detail_url}")

        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps([r.to_dict() for r in results], indent=2,
                                       ensure_ascii=False), encoding="utf-8")
        click.echo(f"\nSaved metadata -> {out_path}")

        if download_dir:
            ddir = Path(download_dir)
            ddir.mkdir(parents=True, exist_ok=True)
            click.echo(f"Downloading low-res images -> {ddir} ...")
            ok = 0
            for r in results:
                dest = ddir / f"{r.sk}.jpg"
                if cli.download(r, dest, size="sd"):
                    ok += 1
                else:
                    click.echo(f"  [skip] could not download {r.sk} ({r.title[:40]})")
            click.echo(f"Downloaded {ok}/{len(results)} images.")


@main.command('extract-assets')
@click.argument('url')
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Directory to download assets into (default: .scratch/extracted/<host>).')
@click.option('--limit', '-n', type=int, default=None,
              help='Maximum number of assets to extract.')
@click.option('--manifest', '-m', type=click.Path(), default=None,
              help='JSON manifest path (default: <output>/manifest.json).')
@click.option('--download/--no-download', default=True,
              help='Download the full-resolution assets (default: on).')
@click.option('--save-to-library/--no-save-to-library', 'save_to_library', default=False,
              help='Also ingest the assets into the picture library.')
@click.option('--scope', type=click.Choice(['global', 'project']), default='global',
              help='Picture-library scope for --save-to-library.')
@click.option('--project', '-p', default=None, help='Project name (for --scope project).')
@click.pass_context
def extract_assets(ctx, url, output, limit, manifest, download, save_to_library, scope, project):
    """Extract high-definition image assets from a web page URL.

    Uses a registry of parsers (Project Gutenberg, Wikimedia Commons, The Met,
    Internet Archive, Library of Congress, and any IIIF manifest/info.json) plus
    a universal HTML fallback that prefers linked full-res over thumbnails,
    srcset, and og:image.

    Examples:

      nolan extract-assets https://www.gutenberg.org/files/21790/21790-h/21790-h.htm

      nolan extract-assets https://commons.wikimedia.org/wiki/File:The_Blue_Marble.jpg -n 1

      nolan extract-assets https://www.loc.gov/item/2021669449/

      nolan extract-assets https://iiif.io/api/cookbook/recipe/0009-book-1/manifest.json
    """
    import asyncio
    import json
    from urllib.parse import urlparse

    from nolan.extractors import download_assets, extract_from_url, get_extractor

    ex = get_extractor(url)
    click.echo(f"Extractor: {ex.name}")
    try:
        results = extract_from_url(url, limit=limit)
    except Exception as e:
        click.echo(f"Error fetching/parsing: {e}")
        return

    click.echo(f"Found {len(results)} asset(s)")
    for i, r in enumerate(results[:10]):
        click.echo(f"  {i + 1}. {r.url}")
    if len(results) > 10:
        click.echo(f"  ... and {len(results) - 10} more")
    if not results:
        return

    host = urlparse(url).netloc.replace(":", "_") or "page"
    out_dir = Path(output) if output else Path(".scratch/extracted") / host
    records = [r.to_dict() for r in results]

    if download:
        click.echo(f"\nDownloading to {out_dir} ...")
        records = asyncio.run(download_assets(results, out_dir))
        ok = sum(1 for r in records if r.get("local_path"))
        click.echo(f"Downloaded {ok}/{len(records)}")
        for r in records:
            if r.get("error"):
                click.echo(f"  ! {r['url']}: {r['error']}")

    manifest_path = Path(manifest) if manifest else out_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {"url": url, "extractor": ex.name, "count": len(records), "results": records},
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    click.echo(f"Manifest: {manifest_path}")

    if save_to_library and results:
        from nolan.imagelib import ImageLibrary
        click.echo(f"\nSaving to {scope} picture library...")
        lib = ImageLibrary(scope=scope, project=project)
        local_by_url = {r.get("url"): r.get("local_path") for r in records}
        added = dup = 0
        with click.progressbar(results, label='Ingesting') as bar:
            for r in bar:
                try:
                    local = local_by_url.get(r.url)
                    if local and Path(local).exists():
                        _, created = lib.add_file(
                            local, url=r.url, source=r.source, source_url=r.source_url,
                            license=r.license, title=r.title, width=r.width,
                            height=r.height, query=url)
                    else:
                        _, created = lib.add_result(r, query=url)
                    added += int(created); dup += int(not created)
                except Exception:
                    pass
        click.echo(f"Library: +{added} new, {dup} duplicate.")


@main.command('match-broll')
@click.argument('scene_plan', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Output directory for downloaded images (defaults to assets/broll next to scene_plan).')
@click.option('--source', '-s', type=click.Choice(['ddgs', 'pexels', 'pixabay', 'wikimedia', 'loc', 'all']),
              default='wikimedia', help='Image source to search.')
@click.option('--max-results', '-n', type=int, default=5,
              help='Maximum results to consider per scene.')
@click.option('--score/--no-score', default=True,
              help='Score images by relevance using vision model.')
@click.option('--vision', type=click.Choice(['openrouter', 'gemini', 'ollama']),
              default='openrouter', help='Vision provider for scoring. Default: openrouter (qwen/qwen3.7-plus).')
@click.option('--skip-existing/--no-skip-existing', default=True,
              help='Skip scenes that already have matched assets.')
@click.option('--dry-run', is_flag=True,
              help='Show what would be downloaded without actually downloading.')
@click.pass_context
def match_broll(ctx, scene_plan, output, source, max_results, score, vision, skip_existing, dry_run):
    """Search and download images for b-roll scenes.

    SCENE_PLAN is the path to scene_plan.json.

    This command will:
    1. Find all b-roll scenes with search_query
    2. Search for images using the specified source
    3. Score images by relevance (optional)
    4. Download the best match for each scene
    5. Update scene_plan.json with matched_asset paths

    Examples:

      nolan match-broll test_output/scene_plan.json

      nolan match-broll scene_plan.json -s pexels --score --vision gemini

      nolan match-broll scene_plan.json --dry-run
    """
    config = ctx.obj['config']
    asyncio.run(_match_broll(config, scene_plan, output, source, max_results, score, vision, skip_existing, dry_run))


async def _match_broll(config, scene_plan_path, output_dir, source, max_results, score, vision, skip_existing, dry_run):
    """Async implementation of match-broll command."""
    import json
    from pathlib import Path
    from nolan.scenes import ScenePlan
    from nolan.image_search import ImageSearchClient, ImageScorer

    scene_plan_path = Path(scene_plan_path)
    plan = ScenePlan.load(str(scene_plan_path))

    # Default output directory
    if output_dir is None:
        output_dir = scene_plan_path.parent / "assets" / "broll"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Find b-roll scenes with search queries
    broll_scenes = []
    for section_name, scenes in plan.sections.items():
        for scene in scenes:
            if scene.visual_type == "b-roll" and scene.search_query:
                if skip_existing and scene.matched_asset:
                    continue
                broll_scenes.append((section_name, scene))

    if not broll_scenes:
        click.echo("No b-roll scenes to match (all may already have matched_asset).")
        return

    click.echo(f"Found {len(broll_scenes)} b-roll scenes to match")
    click.echo(f"Source: {source}")
    click.echo(f"Output: {output_dir}")
    if dry_run:
        click.echo("Mode: DRY RUN (no downloads)")

    # Initialize search client
    client = ImageSearchClient(
        pexels_api_key=config.image_sources.pexels_api_key,
        pixabay_api_key=config.image_sources.pixabay_api_key,
        smithsonian_api_key=config.image_sources.smithsonian_api_key,
        keys=config.image_sources.provider_keys(),
    )

    # Check if source is available
    available = client.get_available_providers()
    if source != "all" and source not in available:
        click.echo(f"Error: Source '{source}' is not available. Check API keys.")
        click.echo(f"Available: {', '.join(available)}")
        return

    # Initialize scorer if needed
    scorer = None
    if score:
        vision_config = _scoring_vision_config(config, vision)
        scorer = ImageScorer(vision_provider=vision, vision_config=vision_config)

    matched_count = 0
    failed_count = 0

    for i, (section_name, scene) in enumerate(broll_scenes):
        click.echo(f"\n[{i+1}/{len(broll_scenes)}] {scene.id}")
        click.echo(f"  Query: {scene.search_query}")

        try:
            # Search for images
            results = client.search(scene.search_query, source, max_results)

            # Provenance gate: stock-preview domains / sub-floor candidates
            # never even get scored (this exact path once stamped Alamy
            # previews into a plan).
            from nolan.asset_gate import check_candidate
            gated = []
            for r in results:
                verdict = check_candidate(r, tier="stock")
                if verdict.ok:
                    gated.append(r)
                else:
                    click.echo(f"  Gate rejected: {(r.url or '')[:70]} "
                               f"({'; '.join(verdict.reasons)})")
            results = gated

            if not results:
                click.echo(f"  No results found")
                failed_count += 1
                continue

            click.echo(f"  Found {len(results)} results")

            # Score if enabled
            if scorer and results:
                click.echo(f"  Scoring with {vision}...")
                results = scorer.score_results(
                    results,
                    scene.search_query,
                    context=f"for a video essay scene: {scene.visual_description}",
                    include_quality=True
                )

            # Pick best result
            best = results[0]
            score_info = f" (score: {best.score:.1f})" if best.score else ""
            click.echo(f"  Best: {best.title or 'No title'}{score_info}")
            click.echo(f"  URL: {best.url[:80]}...")

            if dry_run:
                click.echo(f"  [DRY RUN] Would download to: {output_dir / f'{scene.id}.jpg'}")
                continue

            # Download image
            output_path = output_dir / scene.id
            downloaded_path = client.download_image(best, output_path, prefer_large=True)

            if downloaded_path:
                from nolan.asset_gate import check_file
                verdict = check_file(downloaded_path, tier="stock")
                if not verdict.ok:
                    downloaded_path.unlink(missing_ok=True)
                    click.echo(f"  Gate rejected downloaded file "
                               f"({'; '.join(verdict.reasons)})")
                    failed_count += 1
                    continue
                # Update scene with relative path
                rel_path = downloaded_path.relative_to(scene_plan_path.parent)
                scene.matched_asset = str(rel_path)
                click.echo(f"  Downloaded: {downloaded_path.name}")
                matched_count += 1
            else:
                click.echo(f"  Failed to download")
                failed_count += 1

        except Exception as e:
            click.echo(f"  Error: {e}")
            failed_count += 1

    # Save updated plan
    if not dry_run and matched_count > 0:
        plan.save(str(scene_plan_path))
        click.echo(f"\nScene plan updated: {scene_plan_path}")

    click.echo(f"\nSummary:")
    click.echo(f"  Matched: {matched_count}")
    click.echo(f"  Failed: {failed_count}")
    click.echo(f"  Skipped: {len([s for s in plan.all_scenes if s.visual_type == 'b-roll' and s.matched_asset]) - matched_count}")


@main.command('match-clips')
@click.argument('scene_plan', type=click.Path(exists=True))
@click.option('--candidates', '-c', type=int, default=None,
              help='Candidates per scene (overrides config, default: 3).')
@click.option('--min-similarity', type=float, default=None,
              help='Minimum similarity threshold 0-1 (overrides config, default: 0.5).')
@click.option('--project', '-p', type=str, default=None,
              help='Filter to clips from this project.')
@click.option('--skip-existing/--no-skip-existing', default=True,
              help='Skip scenes that already have matched_clip.')
@click.option('--dry-run', is_flag=True,
              help='Show matches without saving to scene plan.')
@click.option('--search-level', type=click.Choice(['segments', 'clusters', 'both']),
              default=None, help='Search level (overrides config).')
@click.option('--concurrency', '-C', type=int, default=None,
              help='Parallel scene matches (defaults to config.clip_matching.concurrency).')
@click.pass_context
def match_clips(ctx, scene_plan, candidates, min_similarity, project, skip_existing, dry_run, search_level, concurrency):
    """Match scenes to video library clips using semantic search.

    SCENE_PLAN is the path to scene_plan.json.

    This command will:
    1. Search indexed video library for relevant clips
    2. Use LLM to select best candidate for each scene
    3. Apply smart clip tailoring for optimal start/end points
    4. Update scene_plan.json with matched_clip field

    The matched_clip includes video_path, clip_start, clip_end, and reasoning.

    Examples:

      nolan match-clips scene_plan.json

      nolan match-clips scene_plan.json -p venezuela --candidates 5

      nolan match-clips scene_plan.json --min-similarity 0.6 --dry-run
    """
    config = ctx.obj['config']
    asyncio.run(_match_clips(config, scene_plan, candidates, min_similarity, project, skip_existing, dry_run, search_level, concurrency))


async def _match_clips(config, scene_plan_path, candidates, min_similarity, project, skip_existing, dry_run, search_level, concurrency):
    """Async implementation of match-clips command."""
    from pathlib import Path
    from nolan.scenes import ScenePlan
    from nolan.clip_matcher import ClipMatcher
    from nolan.vector_search import VectorSearch
    from nolan.indexer import VideoIndex
    from nolan.llm import create_text_llm
    from nolan.config import ClipMatchingConfig

    scene_plan_path = Path(scene_plan_path)
    plan = ScenePlan.load(str(scene_plan_path))

    # Build config with CLI overrides
    match_config = ClipMatchingConfig(
        candidates_per_scene=candidates if candidates is not None else config.clip_matching.candidates_per_scene,
        min_similarity=min_similarity if min_similarity is not None else config.clip_matching.min_similarity,
        search_level=search_level if search_level is not None else config.clip_matching.search_level,
        skip_edge_percent=config.clip_matching.skip_edge_percent,
        concurrency=concurrency if concurrency is not None else config.clip_matching.concurrency
    )

    # Count scenes
    total_scenes = len(plan.all_scenes)
    scenes_with_query = sum(1 for s in plan.all_scenes if s.search_query or s.visual_description or s.narration_excerpt)

    click.echo(f"Scene plan: {scene_plan_path.name}")
    click.echo(f"Total scenes: {total_scenes}")
    click.echo(f"Matchable scenes: {scenes_with_query}")
    click.echo(f"Candidates per scene: {match_config.candidates_per_scene}")
    click.echo(f"Min similarity: {match_config.min_similarity}")
    click.echo(f"Search level: {match_config.search_level}")
    click.echo(f"Concurrency: {match_config.concurrency}")
    if project:
        click.echo(f"Project filter: {project}")
    if dry_run:
        click.echo("Mode: DRY RUN (no changes saved)")

    # Initialize components
    db_path = Path(config.indexing.database).expanduser()

    # Check if database exists
    if not db_path.exists():
        click.echo(f"\nError: Video library not found at {db_path}")
        click.echo("Run 'nolan index <video_folder>' first to index your library")
        return

    index = VideoIndex(db_path)

    # Initialize vector search
    vector_db_path = db_path.parent / "vectors"
    vector_search = VectorSearch(db_path=vector_db_path, index=index)

    # Check vector DB has content
    stats = vector_search.get_stats()
    if stats["segments"] == 0 and stats["clusters"] == 0:
        click.echo(f"\nError: Vector search database is empty")
        click.echo("Run 'nolan sync-vectors' first to build the search index")
        return

    click.echo(f"\nVector DB: {stats['segments']} segments, {stats['clusters']} clusters")

    # Resolve project slug to ID if provided
    project_id = None
    if project:
        proj = index.get_project(project)
        if not proj:
            click.echo(f"\nWarning: Project '{project}' not found. Searching all projects.")
        else:
            project_id = proj['id']

    # Initialize LLM
    llm = create_text_llm(config)

    # Initialize matcher
    matcher = ClipMatcher(vector_search, llm, match_config)

    # Whole-script context: load the ScriptContext from the plan's project dir so retrieval +
    # LLM selection are subject/era aware (bare "the horse" → the Trojan horse in this script).
    try:
        from nolan.script_context import ScriptContext
        _sctx = ScriptContext.load(Path(scene_plan_path).parent)
        if _sctx.beats:
            matcher.set_script_context(_sctx)
            click.echo(f"  (context: {_sctx.subject or _sctx.slug})")
    except Exception:
        pass

    # Progress callback
    def progress(current, total, message):
        click.echo(f"[{current}/{total}] {message}")

    # Match scenes
    click.echo("\nMatching scenes to library clips...")
    result = await matcher.match_plan(
        plan,
        project_id=project_id,
        skip_existing=skip_existing,
        progress_callback=progress
    )

    # Show results
    click.echo(f"\nResults:")
    click.echo(f"  Matched: {result['matched']}")
    click.echo(f"  No match found: {result['no_match']}")
    click.echo(f"  Skipped (existing): {result['skipped']}")

    # Show matches in dry-run mode
    if dry_run and result['matched'] > 0:
        click.echo("\nMatched clips (DRY RUN - not saved):")
        for scene in plan.all_scenes:
            if scene.matched_clip:
                mc = scene.matched_clip
                video_name = Path(mc['video_path']).name if mc.get('video_path') else 'Unknown'
                click.echo(f"\n  {scene.id}:")
                click.echo(f"    Video: {video_name}")
                click.echo(f"    Clip: {mc['clip_start']:.1f}s - {mc['clip_end']:.1f}s")
                click.echo(f"    Confidence: {mc['confidence']:.2f}")
                reason = mc.get('match_reasoning', '')[:80]
                if len(mc.get('match_reasoning', '')) > 80:
                    reason += "..."
                click.echo(f"    Reason: {reason}")

    # Save updated plan (unless dry-run)
    if not dry_run and result['matched'] > 0:
        plan.save(str(scene_plan_path))
        click.echo(f"\nScene plan updated: {scene_plan_path}")
    elif not dry_run:
        click.echo("\nNo changes to save.")


@main.command()
@click.argument('image', type=click.Path(exists=True))
@click.option('--model', '-m',
              type=click.Choice(['isnet', 'birefnet', 'u2net', 'u2netp',
                                 'isnet-anime', 'birefnet-portrait', 'silueta']),
              default='birefnet', show_default=True,
              help='Background-removal model (birefnet=best edges [default], isnet=~14x faster).')
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Output PNG path (default: <image>.cutout.png).')
@click.option('--alpha-matting', is_flag=True,
              help='Refine soft / hairy edges (slower; good for birefnet + portraits).')
@click.option('--to-library', is_flag=True,
              help='Also add the cutout to the global picture library (tagged "cutout").')
def cutout(image, model, output, alpha_matting, to_library):
    """Remove an image background -> transparent RGBA PNG cutout.

    IMAGE is the source photo/frame. First use of a model downloads its weights once.

    Examples:

        nolan cutout photo.jpg

        nolan cutout portrait.jpg -m birefnet --alpha-matting

        nolan cutout frame.png -o subject.png --to-library
    """
    from nolan.cutout import cutout_file

    src = Path(image)
    extra = ' + alpha-matting' if alpha_matting else ''
    click.echo(f"Cutout: {src.name}  (model={model}{extra})")
    out = cutout_file(src, output, model=model, alpha_matting=alpha_matting)
    click.echo(f"  -> {out}")

    if to_library:
        try:
            from nolan.imagelib import ImageLibrary
            lib = ImageLibrary("global")
            lib.add_file(str(out), source="cutout", tags=["cutout", model],
                         describe=False)
            click.echo("  added to picture library (global)")
        except Exception as e:
            click.echo(f"  [warn] library add failed: {e}")


@main.command('broll')
@click.argument('line')
@click.option('--operator', '-op', type=click.Choice(['tonal', 'literal', 'conceptual', 'ironic', 'trait', 'relational', 'scale', 'knowledge', 'auto']),
              default='tonal', help='Pairing operator (auto = agent picks).')
@click.option('--theme', default='dark-editorial', help='Count-up theme for the scale operator (styles number/caption).')
@click.option('--mode', '-m', type=click.Choice(['stock', 'library', 'generate', 'both']), default='stock',
              help='Asset source: stock / your indexed library / Krea-2 generation / both (stock+library).')
@click.option('--period', default='', help='Story period (enables the anachronism gate).')
@click.option('--locale', default='', help='Story locale (enables the wrong-culture gate).')
@click.option('--literalness', '-l', type=float, default=0.25, help='0=abstract … 1=literal.')
@click.option('--mood', default=None, help='Mood steer (tonal).')
@click.option('--media', multiple=True, type=click.Choice(['video', 'image']), help='Asset types (default both).')
@click.option('--gen-style', default='Fooocus Cinematic', help='Fooocus style for generate mode.')
@click.option('--project', '-p', default=None, help='Project scope + ScriptContext (whole-script context).')
@click.option('--beat', type=int, default=None, help='Beat index in the project script (context-aware search).')
@click.option('--output', '-o', type=click.Path(), default=None, help='Write the full result as JSON.')
@click.option('--render', is_flag=True, help='Render the top pick(s) with their recommended motion to mp4.')
@click.option('--out-dir', type=click.Path(), default='broll_out', help='Output dir for --render.')
@click.pass_context
def broll(ctx, line, operator, mode, theme, period, locale, literalness, mood, media, gen_style, project, beat, output, render, out_dir):
    """Narrative→asset b-roll pairing for a narration LINE.

    Finds b-roll that carries the line's meaning via a pairing OPERATOR, from stock / your
    library / Krea-2 generation, gates on period/locale, abstains when nothing fits, and
    recommends a motion for each pick. `--render` turns the recommended motion into mp4.

    Examples:

      nolan broll "a lone figure watches the sea at dusk, full of grief"

      nolan broll "he maneuvered and waited for them to overextend" -op conceptual

      nolan broll "they toasted profits while the people queued for food" -op relational --render
    """
    import asyncio
    import json
    config = ctx.obj['config']
    from nolan.evoke_broll import EvokeBrollSearch

    searcher = EvokeBrollSearch(config=config, progress=lambda f, m: click.echo(f"  [{f:.2f}] {m}", err=True))
    r = asyncio.run(searcher.search(
        line, operator=operator, mode=mode, period=period, locale=locale, literalness=literalness,
        mood=mood, media=(list(media) or None), gen_style=gen_style, project=project, beat=beat))

    click.echo(f"\n{r['status']}  ·  {operator}/{mode}  ·  {r.get('goal_label', 'goal')}: {r.get('goal', '')}")
    if r.get('quantity'):
        q = r['quantity']
        click.echo(f"  count-up: {q.get('prefix', '')}{q.get('display') or q.get('value')}{q.get('suffix', '')} — {q.get('caption', '')}")
    if r['status'] == 'UNMATCHED' and r.get('reason'):
        click.echo(f"  reason: {r['reason']}")

    def _show(c):
        mo = c.get('motion') or {}
        loc = c.get('video_name') or c.get('source') or ''
        click.echo(f"  - [{c.get('kind')}] fit={c.get('mood')} 2nd={c.get('nonliteral')}  "
                   f"motion={mo.get('id')}  {loc}")
        if c.get('why'):
            click.echo(f"      {c['why']}")
        click.echo(f"      {c.get('url', '')}")

    if r.get('sides'):
        click.echo(f"  synthesis: {r.get('synthesis', '')}")
        for s in r['sides']:
            click.echo(f"\n  SIDE '{s['label']}': {len(s['picks'])} pick(s)")
            for c in s['picks']:
                _show(c)
    else:
        for c in r['picks']:
            _show(c)

    if output:
        Path(output).write_text(json.dumps(r, indent=2, default=str), encoding='utf-8')
        click.echo(f"\n-> {output}")

    if render:
        _broll_render(r, Path(out_dir), theme=theme)


def _broll_localize_img(src, outdir):
    """Resolve a pick's still (served /broll-gen path or remote URL) to a local jpg for rendering."""
    import hashlib
    import io
    from PIL import Image
    from nolan.evoke_broll import GEN_DIR
    from nolan.image_search import ImageScorer
    if src.startswith('/broll-gen/'):
        return GEN_DIR / src.split('/broll-gen/', 1)[1]
    data = ImageScorer()._download_image(src)
    if not data:
        return None
    out = Path(outdir) / f"src_{hashlib.md5(src.encode()).hexdigest()[:10]}.jpg"
    Image.open(io.BytesIO(data)).convert('RGB').save(out, 'JPEG', quality=90)
    return out


def _broll_render(r, out_dir, theme='dark-editorial'):
    """Render the recommended motion for image picks (or split-screen / scale count-up) to mp4."""
    from nolan.still_motion import render_still, render_split, render_stat_over
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if r.get('quantity') and r.get('picks'):
        q = r['quantity']
        for i, c in enumerate(r['picks']):
            src = c.get('poster') or c.get('url')
            li = _broll_localize_img(src, out_dir) if src else None
            if li:
                o = render_stat_over(str(li), q['value'], out_dir / f'stat{i}.mp4',
                                     prefix=q.get('prefix', ''), suffix=q.get('suffix', ''),
                                     caption=q.get('caption', ''), decimals=int(q.get('decimals', 0)),
                                     theme=theme, duration=5.0)
                click.echo(f"  rendered count-up ({theme}) -> {o}")
        return
    if r.get('sides'):
        pa = r['sides'][0]['picks'][0] if r['sides'][0]['picks'] else None
        pb = r['sides'][1]['picks'][0] if len(r['sides']) > 1 and r['sides'][1]['picks'] else None
        if pa and pb:
            la, lb = _broll_localize_img(pa['url'], out_dir), _broll_localize_img(pb['url'], out_dir)
            if la and lb:
                o = render_split(str(la), str(lb), out_dir / 'split.mp4', 4.0,
                                 r['sides'][0]['label'], r['sides'][1]['label'])
                click.echo(f"  rendered split-screen -> {o}")
        return
    for i, c in enumerate(r['picks']):
        if c.get('kind') == 'image' and c.get('url'):
            li = _broll_localize_img(c['url'], out_dir)
            if li:
                mid = (c.get('motion') or {}).get('id', 'ken-burns-in')
                o = render_still(str(li), mid, out_dir / f'pick{i}_{mid}.mp4', 4.0)
                click.echo(f"  rendered {mid} -> {o}")


@main.command('acquire-review')
@click.argument('project')
@click.option('--brains', default='engine', help='Comma list: engine,plan,agent (large-context brains).')
@click.option('--beats', default=None, help='Comma list of beat indices (default: all beats).')
@click.option('--media', multiple=True, type=click.Choice(['image', 'video']), help='Asset types (default image).')
@click.option('--agent', default='nolan4', help='NOLAN tmux agent for the agent brain.')
@click.option('--add', is_flag=True, help='Merge into an existing review (do not clear other brains).')
def acquire_review(project, brains, beats, media, agent, add):
    """Beat-by-beat asset acquisition with full project context — saves the TOP-5 + tags per beat
    (regardless of match) and renders a review gallery. Compare brains: engine / plan / agent.

      nolan acquire-review homer --brains engine,plan,agent
    """
    import asyncio
    from nolan.asset_review import run_review
    br = tuple(b.strip() for b in brains.split(',') if b.strip())
    bt = [int(x) for x in beats.split(',')] if beats else None
    r = asyncio.run(run_review(project, brains=br, beats=bt, media=(list(media) or None),
                               agent=agent, fresh=(not add), progress=lambda f, m: click.echo(f'[{f:.2f}] {m}')))
    click.echo(f"\ndone — {len(r['beats'])} beats · brains {r['brains']}")
    click.echo(f"gallery: /broll-gen/asset_review_{project}.html  (also projects/{project}/asset_review.json)")


if __name__ == '__main__':
    main()
