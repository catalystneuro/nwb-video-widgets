"""Pytest fixtures for nwb-video-widgets tests."""

import shutil

import numpy as np
import pytest
from pynwb import NWBHDF5IO, read_nwb

from tests.fixtures.synthetic_nwb import create_nwbfile_with_external_videos
from tests.fixtures.synthetic_video import create_synthetic_video


@pytest.fixture(scope="session")
def session_tmp_path(tmp_path_factory):
    """Create a session-scoped temporary directory."""
    return tmp_path_factory.mktemp("session")


# ---------------------------------------------------------------------------
# Non-parametrized video fixtures — used by test_utils.py for explicit codec
# detection tests that require a known specific codec.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def synthetic_video_path(session_tmp_path):
    """Create a single H.264-encoded synthetic video file for the test session."""
    video_path = session_tmp_path / "test_video_avc1.mp4"
    create_synthetic_video(video_path, num_frames=30, width=160, height=120, codec="avc1")
    return video_path


@pytest.fixture(scope="session")
def synthetic_video_mp4v_path(session_tmp_path):
    """Create a single mp4v-encoded synthetic video file for the test session."""
    video_path = session_tmp_path / "test_video_mp4v.mp4"
    create_synthetic_video(video_path, num_frames=30, width=160, height=120, codec="mp4v")
    return video_path


# ---------------------------------------------------------------------------
# Codec-parametrized fixtures — drive widget tests across multiple codecs.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", params=["mp4v", "avc1"])
def video_codec(request):
    """Parametrized codec name for widget tests."""
    return request.param


@pytest.fixture(scope="session")
def synthetic_video_codec_path(video_codec, session_tmp_path):
    """Create a single synthetic video encoded with the parametrized codec."""
    video_path = session_tmp_path / f"test_video_{video_codec}.mp4"
    create_synthetic_video(video_path, num_frames=30, width=160, height=120, codec=video_codec)
    return video_path


@pytest.fixture(scope="session")
def synthetic_video_codec_paths(video_codec, session_tmp_path):
    """Create multiple synthetic videos encoded with the parametrized codec."""
    video_names = ["VideoLeftCamera", "VideoBodyCamera", "VideoRightCamera"]
    paths = {}
    for name in video_names:
        video_path = session_tmp_path / f"{name}_{video_codec}.mp4"
        create_synthetic_video(video_path, num_frames=30, codec=video_codec)
        paths[name] = video_path
    return paths


# ---------------------------------------------------------------------------
# NWB fixtures — depend on the codec-parametrized video fixtures so that all
# widget tests automatically run for every codec variant.
# ---------------------------------------------------------------------------


@pytest.fixture
def nwbfile_with_single_video(tmp_path, synthetic_video_codec_path):
    """Create an NWB file with a single external video (parametrized codec)."""
    video_copy = tmp_path / synthetic_video_codec_path.name
    shutil.copy(synthetic_video_codec_path, video_copy)

    nwbfile = create_nwbfile_with_external_videos({"VideoCamera": video_copy})
    nwb_path = tmp_path / "test.nwb"

    with NWBHDF5IO(nwb_path, "w") as io:
        io.write(nwbfile)

    return read_nwb(nwb_path)


@pytest.fixture
def nwbfile_with_multiple_videos(tmp_path, synthetic_video_codec_paths):
    """Create an NWB file with multiple external videos (parametrized codec)."""
    copied_paths = {}
    for name, path in synthetic_video_codec_paths.items():
        video_copy = tmp_path / path.name
        shutil.copy(path, video_copy)
        copied_paths[name] = video_copy

    nwbfile = create_nwbfile_with_external_videos(copied_paths)
    nwb_path = tmp_path / "test.nwb"

    with NWBHDF5IO(nwb_path, "w") as io:
        io.write(nwbfile)

    return read_nwb(nwb_path)


@pytest.fixture
def nwbfile_with_explicit_timestamps(tmp_path, synthetic_video_codec_path):
    """Create an NWB file with explicit timestamps (parametrized codec)."""
    video_copy = tmp_path / synthetic_video_codec_path.name
    shutil.copy(synthetic_video_codec_path, video_copy)

    timestamps = {"VideoCamera": np.linspace(0.0, 1.0, 30)}
    nwbfile = create_nwbfile_with_external_videos({"VideoCamera": video_copy}, timestamps=timestamps)
    nwb_path = tmp_path / "test.nwb"

    with NWBHDF5IO(nwb_path, "w") as io:
        io.write(nwbfile)

    return read_nwb(nwb_path)
