"""Pytest fixtures for nwb-video-widgets tests."""

import shutil

import numpy as np
import pytest
from pynwb import NWBHDF5IO, read_nwb

from tests.fixtures.synthetic_nwb import (
    create_nwbfile_with_external_videos,
    create_nwbfile_with_pose_estimation,
    create_nwbfile_with_videos_and_pose,
)
from tests.fixtures.synthetic_video import create_synthetic_video


@pytest.fixture(scope="session")
def session_tmp_path(tmp_path_factory):
    """Create a session-scoped temporary directory."""
    return tmp_path_factory.mktemp("session")


@pytest.fixture(scope="session")
def synthetic_video_path(session_tmp_path):
    """Create a single synthetic video file for the test session."""
    video_path = session_tmp_path / "test_video.mp4"
    create_synthetic_video(video_path, num_frames=30, width=160, height=120)
    return video_path


@pytest.fixture(scope="session")
def synthetic_video_paths(session_tmp_path):
    """Create multiple synthetic video files for the test session."""
    video_names = ["VideoLeftCamera", "VideoBodyCamera", "VideoRightCamera"]
    paths = {}

    for name in video_names:
        video_path = session_tmp_path / f"{name}.mp4"
        create_synthetic_video(video_path, num_frames=30)
        paths[name] = video_path

    return paths


@pytest.fixture
def nwbfile_with_single_video(tmp_path, synthetic_video_path):
    """Create an NWB file with a single external video."""
    video_copy = tmp_path / synthetic_video_path.name
    shutil.copy(synthetic_video_path, video_copy)

    nwbfile = create_nwbfile_with_external_videos({"VideoCamera": video_copy})
    nwb_path = tmp_path / "test.nwb"

    with NWBHDF5IO(nwb_path, "w") as io:
        io.write(nwbfile)

    return read_nwb(nwb_path)


@pytest.fixture
def nwbfile_with_multiple_videos(tmp_path, synthetic_video_paths):
    """Create an NWB file with multiple external videos."""
    copied_paths = {}
    for name, path in synthetic_video_paths.items():
        video_copy = tmp_path / path.name
        shutil.copy(path, video_copy)
        copied_paths[name] = video_copy

    nwbfile = create_nwbfile_with_external_videos(copied_paths)
    nwb_path = tmp_path / "test.nwb"

    with NWBHDF5IO(nwb_path, "w") as io:
        io.write(nwbfile)

    return read_nwb(nwb_path)


@pytest.fixture
def nwbfile_with_explicit_timestamps(tmp_path, synthetic_video_path):
    """Create an NWB file with explicit timestamps."""
    video_copy = tmp_path / synthetic_video_path.name
    shutil.copy(synthetic_video_path, video_copy)

    timestamps = {"VideoCamera": np.linspace(0.0, 1.0, 30)}
    nwbfile = create_nwbfile_with_external_videos({"VideoCamera": video_copy}, timestamps=timestamps)
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
