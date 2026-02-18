"""Unit tests for utility functions."""

import numpy as np
import pytest
from pynwb.image import ImageSeries
from pynwb.testing.mock.file import mock_NWBFile

from nwb_video_widgets._utils import (
    discover_video_series,
    ensure_browser_compatible_video,
    get_video_codec,
    get_video_timestamps,
)


class TestDiscoverVideoSeries:
    """Tests for discovering ImageSeries in NWB files."""

    def test_discover_video_series_in_acquisition(self):
        """Test discovery of ImageSeries with external_file in acquisition."""
        nwbfile = mock_NWBFile()

        image_series = ImageSeries(
            name="VideoCamera",
            format="external",
            external_file=["./video.mp4"],
            starting_time=0.0,
            rate=30.0,
        )
        nwbfile.add_acquisition(image_series)

        result = discover_video_series(nwbfile)

        assert len(result) == 1
        assert "VideoCamera" in result
        assert result["VideoCamera"] is image_series

    def test_skip_series_without_external_file(self):
        """Test that ImageSeries without external_file are skipped."""
        nwbfile = mock_NWBFile()

        image_series = ImageSeries(
            name="EmbeddedVideo",
            data=np.zeros((10, 64, 64, 3), dtype=np.uint8),
            unit="n.a.",
            starting_time=0.0,
            rate=30.0,
        )
        nwbfile.add_acquisition(image_series)

        result = discover_video_series(nwbfile)

        assert len(result) == 0

    def test_discover_multiple_series(self):
        """Test discovery of multiple ImageSeries."""
        nwbfile = mock_NWBFile()

        for name in ["VideoLeft", "VideoRight"]:
            image_series = ImageSeries(
                name=name,
                format="external",
                external_file=[f"./{name}.mp4"],
                starting_time=0.0,
                rate=30.0,
            )
            nwbfile.add_acquisition(image_series)

        result = discover_video_series(nwbfile)

        assert len(result) == 2
        assert "VideoLeft" in result
        assert "VideoRight" in result


class TestGetVideoTimestamps:
    """Tests for extracting video timestamps."""

    def test_explicit_timestamps(self):
        """Test extraction of explicit timestamps."""
        nwbfile = mock_NWBFile()

        timestamps = np.array([0.0, 0.1, 0.2, 0.3, 0.4])
        image_series = ImageSeries(
            name="VideoCamera",
            format="external",
            external_file=["./video.mp4"],
            timestamps=timestamps,
        )
        nwbfile.add_acquisition(image_series)

        result = get_video_timestamps(nwbfile)

        assert "VideoCamera" in result
        assert result["VideoCamera"] == pytest.approx([0.0, 0.1, 0.2, 0.3, 0.4])

    def test_rate_based_starting_time(self):
        """Test extraction when only starting_time is available."""
        nwbfile = mock_NWBFile()

        image_series = ImageSeries(
            name="VideoCamera",
            format="external",
            external_file=["./video.mp4"],
            starting_time=5.0,
            rate=30.0,
        )
        nwbfile.add_acquisition(image_series)

        result = get_video_timestamps(nwbfile)

        assert "VideoCamera" in result
        assert result["VideoCamera"] == [5.0]

    def test_default_timestamp_when_none(self):
        """Test that [0.0] is returned when no timing info available."""
        nwbfile = mock_NWBFile()

        image_series = ImageSeries(
            name="VideoCamera",
            format="external",
            external_file=["./video.mp4"],
            rate=30.0,
        )
        nwbfile.add_acquisition(image_series)

        result = get_video_timestamps(nwbfile)

        assert "VideoCamera" in result
        assert result["VideoCamera"] == [0.0]


class TestGetVideoCodec:
    """Tests for codec detection using PyAV."""

    def test_returns_h264_for_h264_video(self, synthetic_video_path):
        """Test that H.264-encoded video is detected correctly."""
        codec = get_video_codec(synthetic_video_path)
        assert codec == "h264"

    def test_returns_mpeg4_for_mp4v_video(self, synthetic_video_mp4v_path):
        """Test that mp4v-encoded video is detected as mpeg4."""
        codec = get_video_codec(synthetic_video_mp4v_path)
        assert codec == "mpeg4"


class TestEnsureBrowserCompatibleVideo:
    """Tests for automatic transcoding of non-browser-compatible videos."""

    def test_returns_same_path_for_h264(self, synthetic_video_path):
        """Test that an H.264 video is returned unchanged."""
        result = ensure_browser_compatible_video(synthetic_video_path)
        assert result == synthetic_video_path

    def test_transcodes_mp4v_to_h264(self, synthetic_video_mp4v_path):
        """Test that an mp4v video is transcoded and the output is H.264."""
        result = ensure_browser_compatible_video(synthetic_video_mp4v_path)
        assert result != synthetic_video_mp4v_path
        assert result.exists()
        assert get_video_codec(result) == "h264"

    def test_uses_cache_on_second_call(self, synthetic_video_mp4v_path):
        """Test that a second call returns the cached file without re-transcoding."""
        result1 = ensure_browser_compatible_video(synthetic_video_mp4v_path)
        mtime1 = result1.stat().st_mtime
        result2 = ensure_browser_compatible_video(synthetic_video_mp4v_path)
        assert result1 == result2
        assert result2.stat().st_mtime == mtime1
