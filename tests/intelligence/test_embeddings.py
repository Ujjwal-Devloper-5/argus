"""
Unit tests for EmbeddingDB in argus.intelligence.embeddings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from argus.intelligence.embeddings import DEFAULT_EMBEDDING_DIM, EmbeddingDB


class TestEmbeddingDB:
    """Test suite for EmbeddingDB."""

    def test_initialization_defaults(self) -> None:
        """Verify default dimension is 512 and index starts empty."""
        db = EmbeddingDB()
        assert db.dimension == DEFAULT_EMBEDDING_DIM
        assert len(db) == 0
        assert db.profile_ids == []

    def test_initialization_custom_dimension(self) -> None:
        """Verify custom dimension initialization."""
        db = EmbeddingDB(dimension=128)
        assert db.dimension == 128
        assert len(db) == 0

    def test_initialization_invalid_dimension(self) -> None:
        """Verify non-positive dimensions raise ValueError."""
        with pytest.raises(ValueError, match="positive integer"):
            EmbeddingDB(dimension=0)
        with pytest.raises(ValueError, match="positive integer"):
            EmbeddingDB(dimension=-10)

    def test_empty_database_lookup(self) -> None:
        """Verify find_closest on empty database returns (None, 0.0)."""
        db = EmbeddingDB()
        query = np.random.randn(512).astype(np.float32)
        profile_id, similarity = db.find_closest(query)
        assert profile_id is None
        assert similarity == 0.0

    def test_identical_vectors_high_similarity(self) -> None:
        """Verify identical vectors yield cosine similarity approximately 1.0."""
        db = EmbeddingDB()
        rng = np.random.default_rng(42)
        vec = rng.standard_normal(512).astype(np.float32)

        db.add(profile_id=101, embedding=vec)
        assert len(db) == 1

        matched_id, similarity = db.find_closest(vec)
        assert matched_id == 101
        assert pytest.approx(similarity, rel=1e-4) == 1.0

    def test_scaled_vectors_high_similarity(self) -> None:
        """Verify scaled vector yields similarity ~ 1.0 due to L2 normalization."""
        db = EmbeddingDB()
        rng = np.random.default_rng(123)
        vec = rng.standard_normal(512).astype(np.float32)

        db.add(profile_id=42, embedding=vec)
        matched_id, similarity = db.find_closest(vec * 5.5)
        assert matched_id == 42
        assert pytest.approx(similarity, rel=1e-4) == 1.0

    def test_orthogonal_vectors_low_similarity(self) -> None:
        """Verify orthogonal vectors yield cosine similarity close to 0.0."""
        db = EmbeddingDB(dimension=512)
        vec_a = np.zeros(512, dtype=np.float32)
        vec_b = np.zeros(512, dtype=np.float32)

        vec_a[0] = 1.0  # Unit vector along axis 0
        vec_b[1] = 1.0  # Unit vector along axis 1 (orthogonal)

        db.add(profile_id=1, embedding=vec_a)
        matched_id, similarity = db.find_closest(vec_b)

        assert matched_id == 1
        assert similarity < 1e-4

    def test_opposite_vectors_clamped_similarity(self) -> None:
        """Verify opposing vectors (-vec) result in similarity clamped to 0.0."""
        db = EmbeddingDB()
        rng = np.random.default_rng(77)
        vec = rng.standard_normal(512).astype(np.float32)

        db.add(profile_id=5, embedding=vec)
        matched_id, similarity = db.find_closest(-vec)

        assert matched_id == 5
        assert similarity == 0.0

    def test_closest_profile_selection(self) -> None:
        """Verify correct closest profile is returned among multiple enrolled faces."""
        db = EmbeddingDB()
        rng = np.random.default_rng(999)

        # Generate orthogonal-ish basis vectors
        v1 = rng.standard_normal(512).astype(np.float32)
        v2 = rng.standard_normal(512).astype(np.float32)
        v3 = rng.standard_normal(512).astype(np.float32)

        db.add(profile_id=1, embedding=v1)
        db.add(profile_id=2, embedding=v2)
        db.add(profile_id=3, embedding=v3)

        assert len(db) == 3

        # Add small perturbation to v2
        query_v2 = v2 + rng.standard_normal(512).astype(np.float32) * 0.05
        matched_id, similarity = db.find_closest(query_v2)

        assert matched_id == 2
        assert similarity > 0.90

    def test_multiple_embeddings_per_profile(self) -> None:
        """Verify multiple embeddings can be added for the same profile_id."""
        db = EmbeddingDB()
        rng = np.random.default_rng(88)

        v1_angle1 = rng.standard_normal(512).astype(np.float32)
        v1_angle2 = rng.standard_normal(512).astype(np.float32)
        v2 = rng.standard_normal(512).astype(np.float32)

        db.add(profile_id=10, embedding=v1_angle1)
        db.add(profile_id=10, embedding=v1_angle2)
        db.add(profile_id=20, embedding=v2)

        assert len(db) == 3
        assert db.profile_ids == [10, 10, 20]

        # Query close to angle 2 of profile 10
        matched_id, sim = db.find_closest(v1_angle2)
        assert matched_id == 10
        assert pytest.approx(sim, rel=1e-4) == 1.0

    def test_add_shape_variations(self) -> None:
        """Verify accepting both 1D and 2D single-row arrays."""
        db = EmbeddingDB()
        vec_1d = np.ones(512, dtype=np.float32)
        vec_2d = np.ones((1, 512), dtype=np.float32)

        db.add(profile_id=1, embedding=vec_1d)
        db.add(profile_id=2, embedding=vec_2d)
        assert len(db) == 2

    def test_add_invalid_shapes_raise_error(self) -> None:
        """Verify dimension mismatches raise ValueError."""
        db = EmbeddingDB()
        with pytest.raises(ValueError, match="Expected embedding shape"):
            db.add(profile_id=1, embedding=np.ones(256, dtype=np.float32))

        with pytest.raises(ValueError, match="Expected embedding shape"):
            db.add(profile_id=1, embedding=np.ones((2, 512), dtype=np.float32))

        with pytest.raises(ValueError, match="dimensions"):
            db.add(profile_id=1, embedding=np.ones((1, 1, 512), dtype=np.float32))

    def test_add_invalid_values_raise_error(self) -> None:
        """Verify NaN or Inf values raise ValueError."""
        db = EmbeddingDB()
        nan_vec = np.ones(512, dtype=np.float32)
        nan_vec[10] = np.nan
        with pytest.raises(ValueError, match="NaN or Inf"):
            db.add(profile_id=1, embedding=nan_vec)

        inf_vec = np.ones(512, dtype=np.float32)
        inf_vec[50] = np.inf
        with pytest.raises(ValueError, match="NaN or Inf"):
            db.add(profile_id=1, embedding=inf_vec)

    def test_add_invalid_profile_id_raises_error(self) -> None:
        """Verify non-integer profile_id raises TypeError."""
        db = EmbeddingDB()
        vec = np.ones(512, dtype=np.float32)
        with pytest.raises(TypeError, match="profile_id must be an integer"):
            db.add(profile_id=True, embedding=vec)  # bool is subclass of int

        with pytest.raises(TypeError, match="profile_id must be an integer"):
            db.add(profile_id="abc", embedding=vec)  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="profile_id must be an integer"):
            db.add(profile_id=1.5, embedding=vec)  # type: ignore[arg-type]

    def test_none_embedding_raises_error(self) -> None:
        """Verify None embedding raises ValueError."""
        db = EmbeddingDB()
        with pytest.raises(ValueError, match="Embedding cannot be None"):
            db.add(profile_id=1, embedding=None)  # type: ignore[arg-type]

        vec = np.ones(512, dtype=np.float32)
        db.add(profile_id=1, embedding=vec)
        with pytest.raises(ValueError, match="Embedding cannot be None"):
            db.find_closest(None)  # type: ignore[arg-type]

    def test_zero_norm_vector_handled_gracefully(self) -> None:
        """Verify zero-norm vector does not raise and does not produce NaNs."""
        db = EmbeddingDB()
        zero_vec = np.zeros(512, dtype=np.float32)
        db.add(profile_id=1, embedding=zero_vec)
        assert len(db) == 1

        matched_id, similarity = db.find_closest(zero_vec)
        assert matched_id == 1
        assert similarity == 0.0

    def test_clear_database(self) -> None:
        """Verify clear resets index and profile IDs."""
        db = EmbeddingDB()
        vec = np.ones(512, dtype=np.float32)
        db.add(profile_id=1, embedding=vec)
        db.add(profile_id=2, embedding=vec)
        assert len(db) == 2

        db.clear()
        assert len(db) == 0
        assert db.profile_ids == []

        pid, sim = db.find_closest(vec)
        assert pid is None
        assert sim == 0.0

    def test_column_vector_shape_accepted(self) -> None:
        """Verify (512, 1) column vectors are properly reshaped and accepted."""
        db = EmbeddingDB()
        col_vec = np.ones((512, 1), dtype=np.float32)
        db.add(profile_id=42, embedding=col_vec)
        assert len(db) == 1

        matched_id, similarity = db.find_closest(col_vec)
        assert matched_id == 42
        assert pytest.approx(similarity, rel=1e-4) == 1.0

    def test_concurrent_database_access(self) -> None:
        """Verify thread-safe concurrent reads and writes to EmbeddingDB."""
        import concurrent.futures

        db = EmbeddingDB()
        rng = np.random.default_rng(42)

        def worker_add(profile_id: int) -> None:
            vec = rng.standard_normal(512).astype(np.float32)
            db.add(profile_id=profile_id, embedding=vec)

        def worker_query() -> tuple[int | None, float]:
            vec = rng.standard_normal(512).astype(np.float32)
            return db.find_closest(vec)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            add_futures: list[concurrent.futures.Future[Any]] = [
                executor.submit(worker_add, i) for i in range(1, 25)
            ]
            query_futures: list[concurrent.futures.Future[Any]] = [
                executor.submit(worker_query) for _ in range(50)
            ]

            for f in concurrent.futures.as_completed(add_futures + query_futures):
                f.result()

        assert len(db) == 24
        assert len(db.profile_ids) == 24

    def test_save_and_load_from_file(self, tmp_path: Path) -> None:
        """Verify saving to disk and reconstituting EmbeddingDB via load_from_file."""
        db = EmbeddingDB()
        rng = np.random.default_rng(101)
        v1 = rng.standard_normal(512).astype(np.float32)
        v2 = rng.standard_normal(512).astype(np.float32)

        db.add(profile_id=10, embedding=v1)
        db.add(profile_id=20, embedding=v2)

        save_file = tmp_path / "embeddings.index"
        db.save(save_file)

        assert save_file.exists()
        assert (tmp_path / "embeddings.index.meta.json").exists()

        # Load into brand new instance
        loaded_db = EmbeddingDB.load_from_file(save_file)
        assert len(loaded_db) == 2
        assert loaded_db.profile_ids == [10, 20]
        assert loaded_db.dimension == 512

        # Verify search results are identical
        matched_id, sim = loaded_db.find_closest(v1)
        assert matched_id == 10
        assert pytest.approx(sim, rel=1e-4) == 1.0

        matched_id2, sim2 = loaded_db.find_closest(v2)
        assert matched_id2 == 20
        assert pytest.approx(sim2, rel=1e-4) == 1.0

    def test_save_and_inplace_load(self, tmp_path: Path) -> None:
        """Verify in-place reloading into an existing EmbeddingDB instance."""
        db = EmbeddingDB()
        rng = np.random.default_rng(202)
        v = rng.standard_normal(512).astype(np.float32)
        db.add(profile_id=99, embedding=v)

        save_file = tmp_path / "faces.idx"
        db.save(save_file)

        # Clear and reload in place
        db.clear()
        assert len(db) == 0
        db.load(save_file)
        assert len(db) == 1
        assert db.profile_ids == [99]

        matched_id, sim = db.find_closest(v)
        assert matched_id == 99
        assert pytest.approx(sim, rel=1e-4) == 1.0

    def test_save_empty_database(self, tmp_path: Path) -> None:
        """Verify saving and loading an empty EmbeddingDB."""
        db = EmbeddingDB()
        save_file = tmp_path / "empty.idx"
        db.save(save_file)

        loaded = EmbeddingDB.load_from_file(save_file)
        assert len(loaded) == 0
        assert loaded.profile_ids == []
        assert loaded.find_closest(np.ones(512, dtype=np.float32)) == (None, 0.0)

    def test_load_nonexistent_file_raises(self, tmp_path: Path) -> None:
        """Verify FileNotFoundError when target index file does not exist."""
        db = EmbeddingDB()
        with pytest.raises(FileNotFoundError, match="not found"):
            db.load(tmp_path / "does_not_exist.idx")

    def test_load_mismatched_metadata_raises(self, tmp_path: Path) -> None:
        """Verify ValueError when metadata profile count does not match FAISS index count."""
        import json

        db = EmbeddingDB()
        db.add(profile_id=1, embedding=np.ones(512, dtype=np.float32))
        save_file = tmp_path / "mismatch.idx"
        db.save(save_file)

        # Corrupt the metadata file to have wrong number of profile_ids
        meta_file = tmp_path / "mismatch.idx.meta.json"
        with open(meta_file) as f:
            meta = json.load(f)
        meta["profile_ids"] = [1, 2, 3]  # Index has 1, meta claims 3
        with open(meta_file, "w") as f:
            json.dump(meta, f)

        with pytest.raises(ValueError, match="Mismatch between index vector count"):
            EmbeddingDB.load_from_file(save_file)

    def test_clear_and_state_recovery_cycle(self, tmp_path: Path) -> None:
        """Verify clear/reset cycle followed by reload restores search functionality."""
        db = EmbeddingDB()
        vec = np.ones(512, dtype=np.float32)
        db.add(profile_id=7, embedding=vec)

        save_file = tmp_path / "cycle.idx"
        db.save(save_file)

        # Multiple clear and reload cycles
        for _ in range(3):
            db.clear()
            assert len(db) == 0
            assert db.find_closest(vec) == (None, 0.0)
            db.load(save_file)
            assert len(db) == 1
            matched_id, sim = db.find_closest(vec)
            assert matched_id == 7
            assert pytest.approx(sim, rel=1e-4) == 1.0
