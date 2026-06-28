"""CLIP embeddings for the picture library.

Uses sentence-transformers' CLIP model, which maps **images and text into one
shared vector space** — so a text query ("soldiers in a trench") can retrieve
images by semantic similarity. The model is lazy-loaded (first call downloads
~600 MB from HuggingFace, then it's cached).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

CLIP_MODEL = "clip-ViT-B-32"
# Text embedding model for asset *descriptions* — same as the video library's
# segment search (nolan.vector_search) so descriptions live in a proven space.
DESC_MODEL = "BAAI/bge-base-en-v1.5"


def description_embedding_function():
    """Chroma embedding function for asset descriptions (BGE, text->text)."""
    from chromadb.utils import embedding_functions
    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=DESC_MODEL)


class ClipEmbedder:
    """Lazy CLIP encoder for images and text (normalized, cosine-ready)."""

    def __init__(self, model_name: str = CLIP_MODEL):
        self.model_name = model_name
        self._model = None

    def _model_obj(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_image(self, path: Union[str, Path]) -> Optional[List[float]]:
        """Encode an image file. Returns None if it can't be opened/decoded."""
        from PIL import Image
        try:
            with Image.open(path) as im:
                vec = self._model_obj().encode(im.convert("RGB"),
                                               normalize_embeddings=True)
        except Exception:
            return None
        return vec.tolist()

    def embed_text(self, text: str) -> List[float]:
        """Encode a text query into the shared image/text space."""
        vec = self._model_obj().encode(text, normalize_embeddings=True)
        return vec.tolist()
