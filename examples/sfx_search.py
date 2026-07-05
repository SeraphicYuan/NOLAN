"""Example: SFX search + fetch (Freesound + Mixkit providers)

Demonstrates the pluggable sound-effect sourcing layer (`nolan.sfx_search`) that
automates the search-and-download step the audio-mix stage otherwise does by hand.

Usage:
    python examples/sfx_search.py "whoosh transition"          # default: mixkit (no key)
    python examples/sfx_search.py "coin pickup" freesound      # needs FREESOUND_API_KEY
    python examples/sfx_search.py "sword clang" mixkit --save   # download top hit to _library/sfx/

Output:
    Prints candidate results (title, license, url). With --save, downloads the top
    hit into projects/_library/sfx/ and records it in sfx.json.
"""

import sys
from nolan.sfx_search import search_sfx, source_sfx, get_provider


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    query = args[0] if args else "whoosh transition"
    provider = args[1] if len(args) > 1 else "mixkit"
    save = "--save" in sys.argv[1:]

    prov = get_provider(provider)
    if not prov.available():
        print(f"[!] provider '{provider}' unavailable — set its API key "
              f"(FREESOUND_API_KEY for freesound) in .env")
        return

    print(f"searching {provider} for: {query!r}\n")
    results = search_sfx(query, provider=provider, max_results=8)
    if not results:
        print("no results (try a simpler/category-like term for mixkit, e.g. 'whoosh')")
        return

    for i, r in enumerate(results, 1):
        dur = f"{r.duration:.1f}s" if r.duration else "?"
        print(f"{i}. {r.title}  [{dur}]")
        print(f"   {r.download_url}")
        print(f"   license: {r.license}" + (f"  · credit: {r.attribution}" if r.attribution else ""))

    if save:
        print("\nsaving top hit to projects/_library/sfx/ ...")
        path = source_sfx(query, provider=provider)
        print("saved:", path)


if __name__ == "__main__":
    main()
