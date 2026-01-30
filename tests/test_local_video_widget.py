"""Unit tests for NWBLocalVideoPlayer."""

import pytest

from nwb_video_widgets import NWBLocalVideoPlayer


class TestVideoPathDiscovery:
    """Tests for discovering video paths from NWB files."""

    def test_discover_single_video(self, nwbfile_with_single_video):
        """Test discovering a single external video."""
        video_urls = NWBLocalVideoPlayer.get_video_urls_from_local(
            nwbfile_with_single_video
        )

        assert len(video_urls) == 1
        assert "VideoCamera" in video_urls
        assert video_urls["VideoCamera"].startswith("http://127.0.0.1:")
        assert video_urls["VideoCamera"].endswith(".mp4")

    def test_discover_multiple_videos(self, nwbfile_with_multiple_videos):
        """Test discovering multiple external videos."""
        video_urls = NWBLocalVideoPlayer.get_video_urls_from_local(
            nwbfile_with_multiple_videos
        )

        assert len(video_urls) == 3
        assert "VideoLeftCamera" in video_urls
        assert "VideoRightCamera" in video_urls
        assert "VideoBodyCamera" in video_urls

        for name, url in video_urls.items():
            assert url.startswith("http://127.0.0.1:")

    def test_raises_for_in_memory_nwbfile(self):
        """Test that error is raised for NWB files not loaded from disk."""
        from pynwb.testing.mock.file import mock_NWBFile

        nwbfile = mock_NWBFile()

        with pytest.raises(ValueError, match="loaded from disk"):
            NWBLocalVideoPlayer.get_video_urls_from_local(nwbfile)


class TestTimestampExtraction:
    """Tests for extracting video timestamps."""

    def test_explicit_timestamps(self, nwbfile_with_explicit_timestamps):
        """Test extraction when timestamps are explicit."""
        from nwb_video_widgets._utils import get_video_timestamps

        timestamps = get_video_timestamps(nwbfile_with_explicit_timestamps)

        assert "VideoCamera" in timestamps
        assert len(timestamps["VideoCamera"]) == 30
        assert timestamps["VideoCamera"][0] == pytest.approx(0.0)
        assert timestamps["VideoCamera"][-1] == pytest.approx(1.0)

    def test_rate_based_timestamps(self, nwbfile_with_single_video):
        """Test extraction when using starting_time + rate."""
        from nwb_video_widgets._utils import get_video_timestamps

        timestamps = get_video_timestamps(nwbfile_with_single_video)

        assert "VideoCamera" in timestamps
        # Rate-based: only starting_time is returned
        assert timestamps["VideoCamera"][0] == 0.0


class TestWidgetCreation:
    """Tests for widget instantiation."""

    def test_create_widget_single_video(self, nwbfile_with_single_video):
        """Test creating widget with single video."""
        widget = NWBLocalVideoPlayer(nwbfile_with_single_video)

        assert len(widget.video_urls) == 1
        assert "VideoCamera" in widget.video_urls

    def test_create_widget_custom_layout(self, nwbfile_with_multiple_videos):
        """Test creating widget with custom grid layout."""
        custom_layout = [["VideoLeftCamera", "VideoRightCamera"]]
        widget = NWBLocalVideoPlayer(
            nwbfile_with_multiple_videos, grid_layout=custom_layout
        )

        assert widget.grid_layout == custom_layout

    def test_default_grid_layout(self, nwbfile_with_single_video):
        """Test that default grid layout is applied."""
        widget = NWBLocalVideoPlayer(nwbfile_with_single_video)

        assert widget.grid_layout == [
            ["VideoLeftCamera", "VideoBodyCamera", "VideoRightCamera"]
        ]
