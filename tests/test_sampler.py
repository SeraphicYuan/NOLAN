"""Tests for frame sampling module."""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from nolan.sampler import (
    SamplingStrategy,
    SamplerConfig,
    SampledFrame,
    FixedIntervalSampler,
    SceneChangeSampler,
    PerceptualHashSampler,
    HybridSampler,
    create_sampler,
)


class TestSamplerConfig:
    """Tests for SamplerConfig."""

    def test_defaults(self):
        """Test default configuration values."""
        config = SamplerConfig()
        assert config.strategy == SamplingStrategy.HYBRID
        assert config.fixed_interval == 5.0
        assert config.min_interval == 1.0
        assert config.max_interval == 30.0
        assert config.scene_threshold == 30.0

    def test_custom_values(self):
        """Test custom configuration values."""
        config = SamplerConfig(
            strategy=SamplingStrategy.FIXED,
            fixed_interval=10.0,
            scene_threshold=50.0
        )
        assert config.strategy == SamplingStrategy.FIXED
        assert config.fixed_interval == 10.0
        assert config.scene_threshold == 50.0


class TestSampledFrame:
    """Tests for SampledFrame dataclass."""

    def test_creation(self):
        """Test creating a sampled frame."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        sampled = SampledFrame(timestamp=5.0, frame=frame, reason="test")

        assert sampled.timestamp == 5.0
        assert sampled.frame.shape == (480, 640, 3)
        assert sampled.reason == "test"


class TestFixedIntervalSampler:
    """Tests for FixedIntervalSampler."""

    def test_init(self):
        """Test initialization."""
        sampler = FixedIntervalSampler(interval=10.0)
        assert sampler.interval == 10.0

    def test_sample_nonexistent_video(self):
        """Test sampling nonexistent video raises error."""
        sampler = FixedIntervalSampler(interval=2.0)

        # Should raise when trying to sample from nonexistent file
        with pytest.raises(ValueError, match="Could not open video"):
            list(sampler.sample(Path("nonexistent.mp4")))


class TestPerceptualHashSampler:
    """Tests for PerceptualHashSampler."""

    def test_compute_phash(self):
        """Test perceptual hash computation."""
        sampler = PerceptualHashSampler()

        # Create two similar frames
        frame1 = np.ones((480, 640, 3), dtype=np.uint8) * 128
        frame2 = np.ones((480, 640, 3), dtype=np.uint8) * 130

        hash1 = sampler._compute_phash(frame1)
        hash2 = sampler._compute_phash(frame2)

        # Similar frames should have low hamming distance
        distance = sampler._hamming_distance(hash1, hash2)
        assert distance < 10

    def test_hamming_distance(self):
        """Test hamming distance calculation."""
        sampler = PerceptualHashSampler()

        # Same values should have 0 distance
        assert sampler._hamming_distance(0b1111, 0b1111) == 0

        # One bit different
        assert sampler._hamming_distance(0b1111, 0b1110) == 1

        # All bits different in 4-bit number
        assert sampler._hamming_distance(0b1111, 0b0000) == 4


class TestCreateSampler:
    """Tests for sampler factory function."""

    def test_create_fixed(self):
        """Test creating fixed interval sampler."""
        config = SamplerConfig(strategy=SamplingStrategy.FIXED, fixed_interval=10.0)
        sampler = create_sampler(config)
        assert isinstance(sampler, FixedIntervalSampler)
        assert sampler.interval == 10.0

    def test_create_scene_change(self):
        """Test creating scene change sampler."""
        config = SamplerConfig(strategy=SamplingStrategy.SCENE_CHANGE, scene_threshold=40.0)
        sampler = create_sampler(config)
        assert isinstance(sampler, SceneChangeSampler)
        assert sampler.threshold == 40.0

    def test_create_perceptual_hash(self):
        """Test creating perceptual hash sampler."""
        config = SamplerConfig(strategy=SamplingStrategy.PERCEPTUAL_HASH)
        sampler = create_sampler(config)
        assert isinstance(sampler, PerceptualHashSampler)

    def test_create_hybrid(self):
        """Test creating hybrid sampler."""
        config = SamplerConfig(
            strategy=SamplingStrategy.HYBRID,
            min_interval=2.0,
            max_interval=20.0
        )
        sampler = create_sampler(config)
        assert isinstance(sampler, HybridSampler)
        assert sampler.min_interval == 2.0
        assert sampler.max_interval == 20.0
