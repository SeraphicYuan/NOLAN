"""NOLAN picture library — persistent, searchable, license-aware image store, in two tiers.

HELD (the Picture Library): images whose bytes we keep. NOT-HELD (**Visual Lib**): a
catalog-scale discovery index of images we don't — museum/archive collections harvested as
metadata + a 512px thumbnail, so a search can answer "this exists, here, under these terms",
and `ImageLibrary.promote` fetches the bytes when a beat actually earns it. One catalog, one
`held` flag, one promotion edge — the shape the transcript library used to add a discovery tier
to the video library. The discovery tier is OPT-IN on every read path (`held=0`), so nothing
that expects a file on disk can be handed a row that has none.

    from nolan.imagelib import ImageLibrary, search_all

    lib = ImageLibrary("global")
    lib.add_url("https://example.org/photo.jpg", source="web", license="CC0")
    for hit in lib.search("a steam locomotive"):
        print(hit.score, hit.asset.path, hit.asset.license)

Scopes live inside the project tree: global -> ``_library/images/``,
project -> ``projects/<name>/imagelib/``. CLIP embeddings (image+text shared
space) power semantic text->image search via ChromaDB.
"""

from nolan.imagelib.catalog import Asset, AssetCatalog, Collection
from nolan.imagelib.embeddings import ClipEmbedder
from nolan.imagelib.store import (
    ImageLibrary, LibraryHit, library_paths, promote_to_global, search_all,
)

__all__ = [
    "Asset", "AssetCatalog", "ClipEmbedder", "Collection",
    "ImageLibrary", "LibraryHit", "library_paths", "promote_to_global", "search_all",
]
