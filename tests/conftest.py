"""Pytest fixtures for nwb-video-widgets tests."""

import shutil
from pathlib import Path

import numpy as np
import pytest
from pynwb import NWBHDF5IO, read_nwb

from tests.fixtures.synthetic_nwb import create_nwbfile_with_external_videos

# Committed stub videos from DANDI (trimmed, 160x120, ~0.5s)
_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "videos"
STUB_H264_PATH = _FIXTURES_DIR / "stub_h264.mp4"
STUB_MJPEG_PATH = _FIXTURES_DIR / "stub_mjpeg.avi"
STUB_MP4V_PATH = _FIXTURES_DIR / "stub_mp4v.mp4"


@pytest.fixture
def nwbfile_with_single_video(tmp_path):
    """Create an NWB file with a single external video."""
    video_path = tmp_path / "test_video.mp4"
    shutil.copy(STUB_H264_PATH, video_path)

    nwbfile = create_nwbfile_with_external_videos({"VideoCamera": video_path})
    nwb_path = tmp_path / "test.nwb"

    with NWBHDF5IO(nwb_path, "w") as io:
        io.write(nwbfile)

    return read_nwb(nwb_path)


@pytest.fixture
def nwbfile_with_multiple_videos(tmp_path):
    """Create an NWB file with multiple external videos."""
    video_paths = {}
    for name in ["VideoLeftCamera", "VideoBodyCamera", "VideoRightCamera"]:
        video_path = tmp_path / f"{name}.mp4"
        shutil.copy(STUB_H264_PATH, video_path)
        video_paths[name] = video_path

    nwbfile = create_nwbfile_with_external_videos(video_paths)
    nwb_path = tmp_path / "test.nwb"

    with NWBHDF5IO(nwb_path, "w") as io:
        io.write(nwbfile)

    return read_nwb(nwb_path)


@pytest.fixture
def nwbfile_with_explicit_timestamps(tmp_path):
    """Create an NWB file with explicit timestamps."""
    video_path = tmp_path / "test_video.mp4"
    shutil.copy(STUB_H264_PATH, video_path)

    timestamps = {"VideoCamera": np.linspace(0.0, 1.0, 30)}
    nwbfile = create_nwbfile_with_external_videos({"VideoCamera": video_path}, timestamps=timestamps)
    nwb_path = tmp_path / "test.nwb"

    with NWBHDF5IO(nwb_path, "w") as io:
        io.write(nwbfile)

    return read_nwb(nwb_path)
