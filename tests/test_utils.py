"""Unit tests for utility functions."""

import numpy as np
import pytest
from pynwb.image import ImageSeries
from pynwb.testing.mock.file import mock_NWBFile

from nwb_video_widgets._utils import (
    BROWSER_COMPATIBLE_CODECS,
    detect_video_codec,
    discover_video_series,
    get_video_timestamps,
    validate_video_codec,
)
from tests.conftest import STUB_H264_PATH, STUB_MJPEG_PATH, STUB_MP4V_PATH


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


class TestDetectVideoCodec:
    """Tests for codec detection from video file headers."""

    def test_detect_h264(self):
        """Test that H.264 MP4 is detected as avc1."""
        codec = detect_video_codec(STUB_H264_PATH)
        assert codec == "avc1"

    def test_detect_mjpeg(self):
        """Test that MJPEG AVI is detected as MJPG."""
        codec = detect_video_codec(STUB_MJPEG_PATH)
        assert codec == "MJPG"

    def test_detect_mp4v(self):
        """Test that mp4v MP4 is detected as mp4v."""
        codec = detect_video_codec(STUB_MP4V_PATH)
        assert codec == "mp4v"

    def test_h264_is_browser_compatible(self):
        """Test that detected H.264 codec is in the compatible set."""
        codec = detect_video_codec(STUB_H264_PATH)
        assert codec in BROWSER_COMPATIBLE_CODECS

    def test_mjpeg_is_not_browser_compatible(self):
        """Test that detected MJPEG codec is not in the compatible set."""
        codec = detect_video_codec(STUB_MJPEG_PATH)
        assert codec not in BROWSER_COMPATIBLE_CODECS

    def test_mp4v_is_not_browser_compatible(self):
        """Test that detected mp4v codec is not in the compatible set."""
        codec = detect_video_codec(STUB_MP4V_PATH)
        assert codec not in BROWSER_COMPATIBLE_CODECS


class TestValidateVideoCodec:
    """Tests for codec validation."""

    def test_passes_for_h264(self):
        """Test that H.264 video passes validation."""
        validate_video_codec(STUB_H264_PATH)

    def test_raises_for_mjpeg(self):
        """Test that MJPEG video raises ValueError with ffmpeg command."""
        with pytest.raises(ValueError, match="MJPG.*ffmpeg"):
            validate_video_codec(STUB_MJPEG_PATH)

    def test_raises_for_mp4v(self):
        """Test that mp4v video raises ValueError with ffmpeg command."""
        with pytest.raises(ValueError, match="mp4v.*ffmpeg"):
            validate_video_codec(STUB_MP4V_PATH)
