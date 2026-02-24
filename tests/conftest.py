"""Pytest fixtures for nwb-video-widgets tests."""

import shutil
from pathlib import Path

import numpy as np
import pytest
from pynwb import NWBHDF5IO, read_nwb

from tests.fixtures.synthetic_nwb import create_nwbfile_with_external_videos
from tests.fixtures.synthetic_nwb import (
    create_nwbfile_with_external_videos,
    create_nwbfile_with_pose_estimation,
    create_nwbfile_with_videos_and_pose,
    create_synthetic_video,
)
from tests.fixtures.synthetic_video import create_synthetic_video

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


@pytest.fixture
def nwbfile_with_single_camera_pose(tmp_path):
    """Create an NWB file with pose estimation for a single camera."""
    nwbfile = create_nwbfile_with_pose_estimation(
        camera_names=["LeftCamera"],
        keypoint_names=["Nose", "LeftEar", "RightEar"],
        num_frames=30,
    )
    nwb_path = tmp_path / "test_pose.nwb"

    with NWBHDF5IO(nwb_path, "w") as io:
        io.write(nwbfile)

    return read_nwb(nwb_path)


@pytest.fixture
def nwbfile_with_multiple_cameras_pose(tmp_path):
    """Create an NWB file with pose estimation for multiple cameras."""
    nwbfile = create_nwbfile_with_pose_estimation(
        camera_names=["LeftCamera", "RightCamera", "BodyCamera"],
        keypoint_names=["Nose", "LeftEar", "RightEar", "LeftPaw", "RightPaw"],
        num_frames=30,
    )
    nwb_path = tmp_path / "test_multi_pose.nwb"

    with NWBHDF5IO(nwb_path, "w") as io:
        io.write(nwbfile)

    return read_nwb(nwb_path)


@pytest.fixture
def nwbfile_with_videos_and_pose(tmp_path, synthetic_video_paths):
    """Create an NWB file with both videos and pose estimation."""
    copied_paths = {}
    for name, path in synthetic_video_paths.items():
        video_copy = tmp_path / path.name
        shutil.copy(path, video_copy)
        copied_paths[name] = video_copy

    # Create pose estimation for cameras that match video names
    # VideoLeftCamera -> LeftCamera, etc.
    camera_names = [name.replace("Video", "") for name in copied_paths.keys()]

    nwbfile = create_nwbfile_with_videos_and_pose(
        video_paths=copied_paths,
        camera_names=camera_names,
        keypoint_names=["Nose", "LeftEar", "RightEar"],
        num_frames=30,
    )
    nwb_path = tmp_path / "test_combined.nwb"

    with NWBHDF5IO(nwb_path, "w") as io:
        io.write(nwbfile)

    return read_nwb(nwb_path)
