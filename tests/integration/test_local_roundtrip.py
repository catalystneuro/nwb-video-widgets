"""Integration tests for local NWB file handling."""

import urllib.request
from pathlib import Path

import numpy as np
import pytest
from pynwb import NWBHDF5IO, read_nwb

from nwb_video_widgets import NWBLocalVideoPlayer
from tests.fixtures.synthetic_nwb import create_nwbfile_with_external_videos
from tests.fixtures.synthetic_video import create_synthetic_video


@pytest.mark.integration
class TestLocalVideoRoundtrip:
    """End-to-end tests for local video widget."""

    def test_create_and_load_nwb_with_video(self, tmp_path):
        """Create NWB with external video, save, reload, and verify widget works."""
        video_path = tmp_path / "test_video.mp4"
        create_synthetic_video(video_path, num_frames=30)

        nwbfile = create_nwbfile_with_external_videos({"VideoCamera": video_path})
        nwb_path = tmp_path / "test.nwb"

        with NWBHDF5IO(nwb_path, "w") as io:
            io.write(nwbfile)

        loaded_nwb = read_nwb(nwb_path)
        widget = NWBLocalVideoPlayer(loaded_nwb)

        assert "VideoCamera" in widget.video_urls
        url = widget.video_urls["VideoCamera"]
        assert url.startswith("http://127.0.0.1:")

        # Verify the HTTP server responds
        req = urllib.request.Request(url, method="HEAD")
        response = urllib.request.urlopen(req)
        assert response.status == 200

    def test_multiple_cameras_roundtrip(self, tmp_path):
        """Test roundtrip with multiple cameras."""
        video_paths = {}
        for name in ["VideoLeftCamera", "VideoBodyCamera", "VideoRightCamera"]:
            video_path = tmp_path / f"{name}.mp4"
            create_synthetic_video(video_path, num_frames=20)
            video_paths[name] = video_path

        nwbfile = create_nwbfile_with_external_videos(video_paths)
        nwb_path = tmp_path / "multi_camera.nwb"

        with NWBHDF5IO(nwb_path, "w") as io:
            io.write(nwbfile)

        loaded_nwb = read_nwb(nwb_path)
        widget = NWBLocalVideoPlayer(loaded_nwb)

        assert len(widget.video_urls) == 3
        for name in video_paths:
            assert name in widget.video_urls
            url = widget.video_urls[name]
            assert url.startswith("http://127.0.0.1:")
            # Verify the HTTP server responds
            req = urllib.request.Request(url, method="HEAD")
            response = urllib.request.urlopen(req)
            assert response.status == 200

    def test_timestamps_preserved_through_roundtrip(self, tmp_path):
        """Test that explicit timestamps are correctly extracted after roundtrip."""
        video_path = tmp_path / "test_video.mp4"
        create_synthetic_video(video_path, num_frames=30)

        expected_timestamps = np.linspace(0.0, 2.0, 30)
        nwbfile = create_nwbfile_with_external_videos(
            {"VideoCamera": video_path},
            timestamps={"VideoCamera": expected_timestamps},
        )
        nwb_path = tmp_path / "test.nwb"

        with NWBHDF5IO(nwb_path, "w") as io:
            io.write(nwbfile)

        loaded_nwb = read_nwb(nwb_path)
        widget = NWBLocalVideoPlayer(loaded_nwb)

        assert "VideoCamera" in widget.video_timestamps
        actual_timestamps = widget.video_timestamps["VideoCamera"]
        assert len(actual_timestamps) == 30
        np.testing.assert_array_almost_equal(actual_timestamps, expected_timestamps)
