"""Synthetic NWB file generation for testing."""

from pathlib import Path

import numpy as np
from ndx_pose import PoseEstimation, PoseEstimationSeries
from pynwb import NWBFile, ProcessingModule
from pynwb.image import ImageSeries
from pynwb.testing.mock.file import mock_NWBFile


def create_nwbfile_with_external_videos(
    video_paths: dict[str, Path],
    timestamps: dict[str, np.ndarray] | None = None,
) -> NWBFile:
    """Create an NWBFile with ImageSeries pointing to external video files.

    Parameters
    ----------
    video_paths : dict[str, Path]
        Mapping of video names to file paths
    timestamps : dict[str, np.ndarray], optional
        Mapping of video names to timestamp arrays. If None, uses rate-based.

    Returns
    -------
    NWBFile
        NWB file with configured ImageSeries
    """
    nwbfile = mock_NWBFile()

    for name, path in video_paths.items():
        external_path = f"./{path.name}"

        if timestamps and name in timestamps:
            image_series = ImageSeries(
                name=name,
                format="external",
                external_file=[external_path],
                timestamps=timestamps[name],
            )
        else:
            image_series = ImageSeries(
                name=name,
                format="external",
                external_file=[external_path],
                starting_time=0.0,
                rate=30.0,
            )

        nwbfile.add_acquisition(image_series)

    return nwbfile


def create_nwbfile_with_pose_estimation(
    camera_names: list[str],
    keypoint_names: list[str],
    num_frames: int = 30,
    timestamps: np.ndarray | None = None,
    video_width: int = 160,
    video_height: int = 120,
) -> NWBFile:
    """Create an NWBFile with PoseEstimation data.

    Parameters
    ----------
    camera_names : list[str]
        Names of cameras to create pose estimation data for
    keypoint_names : list[str]
        Names of keypoints to track
    num_frames : int, optional
        Number of frames of pose data, by default 30
    timestamps : np.ndarray, optional
        Timestamps for the pose data. If None, uses evenly spaced from 0 to 1.
    video_width : int, optional
        Width of the source video in pixels, by default 160
    video_height : int, optional
        Height of the source video in pixels, by default 120

    Returns
    -------
    NWBFile
        NWB file with pose estimation processing module
    """
    nwbfile = mock_NWBFile()

    # Create pose_estimation processing module
    pose_module = ProcessingModule(
        name="pose_estimation",
        description="Pose estimation data from DeepLabCut or similar",
    )
    nwbfile.add_processing_module(pose_module)

    # Default timestamps
    if timestamps is None:
        timestamps = np.linspace(0.0, 1.0, num_frames)

    # Create a PoseEstimation container for each camera
    frame_indices = np.arange(num_frames)
    circle_x = video_width * (0.2 + 0.6 * frame_indices / num_frames)
    circle_y = np.full(num_frames, video_height / 2)
    noise_scale = max(1, int(video_width * 0.01))
    for camera_name in camera_names:
        # Create PoseEstimationSeries for each keypoint
        pose_series_list = []
        for idx, keypoint_name in enumerate(keypoint_names):
            # Generate synthetic pose data tracking the moving circle in synthetic_video.py
            x_offset = idx * int(video_width * 0.05)
            y_offset = idx * int(video_height * 0.05)
            x_coords = circle_x + x_offset + np.random.randn(num_frames) * noise_scale
            y_coords = circle_y + y_offset + np.random.randn(num_frames) * noise_scale
            data = np.column_stack([x_coords, y_coords])

            series = PoseEstimationSeries(
                name=f"{keypoint_name}PoseEstimationSeries",
                data=data,
                unit="pixels",
                reference_frame="top-left corner",
                timestamps=timestamps,
                confidence=np.random.rand(num_frames),
            )
            pose_series_list.append(series)

        # Create PoseEstimation container for this camera
        pose_estimation = PoseEstimation(
            name=camera_name,
            pose_estimation_series=pose_series_list,
            description=f"Pose estimation for {camera_name}",
            dimensions=np.array([[video_width, video_height]], dtype="uint16"),
        )
        pose_module.add(pose_estimation)

    return nwbfile


def create_nwbfile_with_videos_and_pose(
    video_paths: dict[str, Path],
    camera_names: list[str],
    keypoint_names: list[str],
    num_frames: int = 30,
    timestamps: dict[str, np.ndarray] | None = None,
    video_width: int = 160,
    video_height: int = 120,
) -> NWBFile:
    """Create an NWBFile with both external videos and pose estimation.

    Parameters
    ----------
    video_paths : dict[str, Path]
        Mapping of video names to file paths
    camera_names : list[str]
        Names of cameras for pose estimation (should match video names pattern)
    keypoint_names : list[str]
        Names of keypoints to track
    num_frames : int, optional
        Number of frames of pose data, by default 30
    timestamps : dict[str, np.ndarray], optional
        Mapping of video names to timestamp arrays. If None, uses rate-based.
    video_width : int, optional
        Width of the source video in pixels, by default 160
    video_height : int, optional
        Height of the source video in pixels, by default 120

    Returns
    -------
    NWBFile
        NWB file with both videos and pose estimation
    """
    nwbfile = mock_NWBFile()

    # Add videos
    for name, path in video_paths.items():
        external_path = f"./{path.name}"

        if timestamps and name in timestamps:
            image_series = ImageSeries(
                name=name,
                format="external",
                external_file=[external_path],
                timestamps=timestamps[name],
            )
        else:
            image_series = ImageSeries(
                name=name,
                format="external",
                external_file=[external_path],
                starting_time=0.0,
                rate=30.0,
            )

        nwbfile.add_acquisition(image_series)

    # Add pose estimation
    pose_module = ProcessingModule(
        name="pose_estimation",
        description="Pose estimation data from DeepLabCut or similar",
    )
    nwbfile.add_processing_module(pose_module)

    # Use first video's timestamps if available
    pose_timestamps = None
    if timestamps:
        first_video = next(iter(timestamps.values()))
        pose_timestamps = first_video
    else:
        pose_timestamps = np.linspace(0.0, 1.0, num_frames)

    # Create pose estimation for each camera
    n = len(pose_timestamps)
    frame_indices = np.arange(n)
    circle_x = video_width * (0.2 + 0.6 * frame_indices / n)
    circle_y = np.full(n, video_height / 2)
    noise_scale = max(1, int(video_width * 0.01))
    for camera_name in camera_names:
        pose_series_list = []
        for idx, keypoint_name in enumerate(keypoint_names):
            # Generate synthetic pose data tracking the moving circle in synthetic_video.py
            x_offset = idx * int(video_width * 0.05)
            y_offset = idx * int(video_height * 0.05)
            x_coords = circle_x + x_offset + np.random.randn(n) * noise_scale
            y_coords = circle_y + y_offset + np.random.randn(n) * noise_scale
            data = np.column_stack([x_coords, y_coords])

            series = PoseEstimationSeries(
                name=f"{keypoint_name}PoseEstimationSeries",
                data=data,
                unit="pixels",
                reference_frame="top-left corner",
                timestamps=pose_timestamps,
                confidence=np.random.rand(len(pose_timestamps)),
            )
            pose_series_list.append(series)

        pose_estimation = PoseEstimation(
            name=camera_name,
            pose_estimation_series=pose_series_list,
            description=f"Pose estimation for {camera_name}",
            dimensions=np.array([[video_width, video_height]], dtype="uint16"),
        )
        pose_module.add(pose_estimation)

    return nwbfile
