"""Unit tests for NWBLocalVideoPlayer."""

import shutil

import pytest

from nwb_video_widgets import NWBLocalVideoPlayer


class TestVideoPathDiscovery:
    """Tests for discovering video paths from NWB files."""

    def test_discover_single_video(self, nwbfile_with_single_video):
        """Test discovering a single external video."""
        video_urls = NWBLocalVideoPlayer.get_video_urls_from_local(nwbfile_with_single_video)

        assert len(video_urls) == 1
        assert "VideoCamera" in video_urls
        assert video_urls["VideoCamera"].startswith("http://127.0.0.1:")
        assert video_urls["VideoCamera"].endswith(".mp4")

    def test_discover_multiple_videos(self, nwbfile_with_multiple_videos):
        """Test discovering multiple external videos."""
        video_urls = NWBLocalVideoPlayer.get_video_urls_from_local(nwbfile_with_multiple_videos)

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

    def test_create_widget_multiple_videos(self, nwbfile_with_multiple_videos):
        """Test creating widget with multiple videos."""
        widget = NWBLocalVideoPlayer(nwbfile_with_multiple_videos)

        assert len(widget.video_urls) == 3
        assert len(widget.available_videos) == 3
        assert widget.layout_mode == "grid"

    def test_default_layout_mode(self, nwbfile_with_single_video):
        """Test that default layout mode is grid."""
        widget = NWBLocalVideoPlayer(nwbfile_with_single_video)

        assert widget.layout_mode == "grid"
        assert widget.settings_open is True
        assert widget.selected_videos == []


class TestMp4vCodecTranscoding:
    """Tests for automatic transcoding of mp4v videos."""

    @pytest.fixture
    def nwbfile_with_mp4v_video(self, tmp_path, synthetic_video_mp4v_path):
        """Create an NWB file pointing to an mp4v-encoded video."""
        from pynwb import NWBHDF5IO, read_nwb

        from tests.fixtures.synthetic_nwb import create_nwbfile_with_external_videos

        video_copy = tmp_path / synthetic_video_mp4v_path.name
        shutil.copy(synthetic_video_mp4v_path, video_copy)

        nwbfile = create_nwbfile_with_external_videos({"VideoCamera": video_copy})
        nwb_path = tmp_path / "test_mp4v.nwb"

        with NWBHDF5IO(nwb_path, "w") as io:
            io.write(nwbfile)

        return read_nwb(nwb_path)

    def test_mp4v_video_is_transcoded(self, nwbfile_with_mp4v_video):
        """Test that mp4v videos are transparently transcoded to H.264 before serving."""

        video_urls = NWBLocalVideoPlayer.get_video_urls_from_local(nwbfile_with_mp4v_video)

        assert "VideoCamera" in video_urls
        url = video_urls["VideoCamera"]
        assert url.startswith("http://127.0.0.1:")
        # The URL should point to the H.264-transcoded cache file
        assert "_h264.mp4" in url
