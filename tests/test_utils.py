"""Unit tests for utility functions."""

import numpy as np
import pytest
from pynwb.image import ImageSeries
from pynwb.testing.mock.file import mock_NWBFile

from nwb_video_widgets._utils import discover_video_series, get_video_timestamps


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
