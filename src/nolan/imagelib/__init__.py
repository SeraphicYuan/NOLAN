"""NOLAN picture library — persistent, searchable, license-aware image store.

    from nolan.imagelib import ImageLibrary, search_all

    lib = ImageLibrary("global")
    lib.add_url("https://example.org/photo.jpg", source="web", license="CC0")
    for hit in lib.search("a steam locomotive"):
        print(hit.score, hit.asset.path, hit.asset.license)

Scopes live inside the project tree: global -> ``_library/images/``,
project -> ``projects/<name>/imagelib/``. CLIP embeddings (image+text shared
space) power semantic text->image search via ChromaDB.
"""

from nolan.imagelib.catalog import Asset, AssetCatalog
from nolan.imagelib.embeddings import ClipEmbedder
from nolan.imagelib.store import (
    ImageLibrary, LibraryHit, library_paths, promote_to_global, search_all,
)

__all__ = [
    "Asset", "AssetCatalog", "ClipEmbedder",
    "ImageLibrary", "LibraryHit", "library_paths", "promote_to_global", "search_all",
]
