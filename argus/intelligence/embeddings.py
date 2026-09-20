"""
Vector embedding database for face recognition using FAISS.

Provides fast cosine-similarity search over 512-dimensional facial embeddings
backed by faiss.IndexFlatIP with L2 normalization.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from pathlib import Path

import faiss
import numpy as np
import structlog

logger = structlog.get_logger(__name__)

DEFAULT_EMBEDDING_DIM = 512


class EmbeddingDB:
    """
    Vector database for facial embeddings backed by FAISS IndexFlatIP.

    Vectors are normalized to unit L2 length prior to insertion and querying,
    ensuring that inner-product operations compute exact cosine similarity.
    """

    def __init__(self, dimension: int = DEFAULT_EMBEDDING_DIM) -> None:
        """
        Initialize the embedding database.

        Args:
            dimension: Dimensionality of embedding vectors (default 512).
        """
        if dimension <= 0:
            raise ValueError(f"dimension must be a positive integer, got {dimension}")

        self.dimension = dimension
        self.index: faiss.IndexFlatIP = faiss.IndexFlatIP(dimension)
        self._profile_ids: list[int] = []
        self._lock = threading.RLock()

    def _prepare_vector(self, embedding: np.ndarray | Sequence[float]) -> np.ndarray:
        """
        Validate, copy, reshape, and L2-normalize an embedding vector.

        Args:
            embedding: Vector of floats representing the embedding.

        Returns:
            Normalized 2D float32 numpy array of shape (1, dimension).
        """
        if embedding is None:
            raise ValueError("Embedding cannot be None")

        try:
            arr = np.array(embedding, dtype=np.float32, copy=True)
        except Exception as exc:
            raise ValueError(f"Failed to convert embedding to numpy array: {exc}") from exc

        if arr.ndim == 1 or (arr.ndim == 2 and arr.shape == (self.dimension, 1)):
            arr = arr.reshape(1, -1)
        elif arr.ndim != 2:
            raise ValueError(f"Embedding must be a 1D or 2D array, got {arr.ndim} dimensions")

        if arr.shape[0] != 1 or arr.shape[1] != self.dimension:
            raise ValueError(
                f"Expected embedding shape (1, {self.dimension}) or ({self.dimension},), "
                f"got {arr.shape}"
            )

        if not np.all(np.isfinite(arr)):
            raise ValueError("Embedding contains NaN or Inf values")

        norm = float(np.linalg.norm(arr))
        if norm > 0:
            faiss.normalize_L2(arr)
        else:
            logger.warning("Attempted to normalize a zero-norm vector")

        return arr

    def add(self, profile_id: int, embedding: np.ndarray) -> None:
        """
        Add a 512-dimensional float32 vector for a given profile_id.

        Args:
            profile_id: Unique identifier of the enrolled face profile.
            embedding: 512-dimensional numpy array or sequence.
        """
        if isinstance(profile_id, bool) or not isinstance(profile_id, (int, np.integer)):
            raise TypeError(f"profile_id must be an integer, got {type(profile_id).__name__}")

        vec = self._prepare_vector(embedding)
        with self._lock:
            self.index.add(vec)
            self._profile_ids.append(int(profile_id))

        logger.debug(
            "Added embedding to database",
            profile_id=profile_id,
            total_embeddings=len(self),
        )

    def find_closest(self, embedding: np.ndarray) -> tuple[int | None, float]:
        """
        Find the closest matched profile_id and cosine similarity score.

        Args:
            embedding: 512-dimensional query vector.

        Returns:
            Tuple of (profile_id, similarity) where similarity is in [0.0, 1.0].
            If the database is empty or no valid match is found, returns (None, 0.0).
        """
        with self._lock:
            if self.index.ntotal == 0 or len(self._profile_ids) == 0:
                return None, 0.0

            vec = self._prepare_vector(embedding)
            distances, indices = self.index.search(vec, 1)

            idx = int(indices[0][0])
            score = float(distances[0][0])

            if idx < 0 or idx >= len(self._profile_ids):
                return None, 0.0

            # Cosine similarity for normalized vectors is in [-1.0, 1.0]; clamp to [0.0, 1.0]
            clamped_score = max(0.0, min(1.0, score))
            matched_id = self._profile_ids[idx]

            logger.debug(
                "Found closest embedding match",
                profile_id=matched_id,
                similarity=clamped_score,
                raw_score=score,
            )

            return matched_id, clamped_score

    def clear(self) -> None:
        """Clear all indexed embeddings and profile mappings."""
        with self._lock:
            self.index.reset()
            self._profile_ids.clear()
        logger.info("Cleared embedding database")

    def __len__(self) -> int:
        """Return the total number of indexed vectors."""
        with self._lock:
            return self.index.ntotal

    @property
    def profile_ids(self) -> list[int]:
        """Return the list of profile IDs corresponding to indexed vectors."""
        with self._lock:
            return list(self._profile_ids)

    def save(self, filepath: str | Path) -> None:
        """
        Save the FAISS index and profile IDs to disk.

        Args:
            filepath: Target file path for the index. A companion metadata file
                with extension .meta.json will be created alongside it.
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        meta_path = path.with_suffix(path.suffix + ".meta.json")

        with self._lock:
            meta = {
                "dimension": self.dimension,
                "profile_ids": self._profile_ids,
                "ntotal": self.index.ntotal,
            }
            faiss.write_index(self.index, str(path))
            tmp_meta = meta_path.with_suffix(".tmp")
            with open(tmp_meta, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
            tmp_meta.replace(meta_path)

        logger.info(
            "Saved EmbeddingDB to disk",
            path=str(path),
            total_embeddings=len(self._profile_ids),
        )

    def load(self, filepath: str | Path) -> None:
        """
        Load index and profile IDs from disk into this instance.

        Args:
            filepath: Path to the FAISS index file.
        """
        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(f"Embedding index file not found: {path}")

        meta_path = path.with_suffix(path.suffix + ".meta.json")
        if not meta_path.is_file():
            raise FileNotFoundError(f"Embedding metadata file not found: {meta_path}")

        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

        dimension = int(meta["dimension"])
        profile_ids = [int(p) for p in meta["profile_ids"]]

        loaded_index = faiss.read_index(str(path))
        if not isinstance(loaded_index, faiss.IndexFlatIP):
            raise TypeError(f"Expected faiss.IndexFlatIP, got {type(loaded_index).__name__}")
        index: faiss.IndexFlatIP = loaded_index

        if index.ntotal != len(profile_ids):
            raise ValueError(
                f"Mismatch between index vector count ({index.ntotal}) and "
                f"profile ID count ({len(profile_ids)})"
            )

        with self._lock:
            self.dimension = dimension
            self.index = index
            self._profile_ids = profile_ids

        logger.info(
            "Loaded EmbeddingDB from disk",
            path=str(path),
            total_embeddings=len(self._profile_ids),
        )

    @classmethod
    def load_from_file(cls, filepath: str | Path) -> EmbeddingDB:
        """
        Load an EmbeddingDB instance from disk.

        Args:
            filepath: Path to the FAISS index file.

        Returns:
            Reconstituted EmbeddingDB instance with index and profile IDs.
        """
        db = cls(dimension=DEFAULT_EMBEDDING_DIM)
        db.load(filepath)
        return db
