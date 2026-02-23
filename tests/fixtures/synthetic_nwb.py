"""Synthetic NWB file generation for testing."""

from pathlib import Path

import numpy as np
from neuroconv.tools.testing.mock_interfaces import MockPoseEstimationInterface
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


def _add_pose_estimation_to_module(
    pose_module: ProcessingModule,
    camera_names: list[str],
    mock_interface: MockPoseEstimationInterface,
    timestamps: np.ndarray,
) -> None:
    """Add PoseEstimation containers to a processing module using MockPoseEstimationInterface data.

    Parameters
    ----------
    pose_module : ProcessingModule
        The NWB processing module to add pose estimation containers to
    camera_names : list[str]
        Names for each PoseEstimation container
    mock_interface : MockPoseEstimationInterface
        NeuroConv mock interface providing pose data and node names
    timestamps : np.ndarray
        Timestamps for all pose estimation series
    """
    from ndx_pose import PoseEstimation, PoseEstimationSeries

    num_frames = len(timestamps)
    for camera_name in camera_names:
        pose_series_list = []
        for idx, node_name in enumerate(mock_interface.nodes):
            pascal_case_node = "".join(word.capitalize() for word in node_name.replace("_", " ").split())
            series = PoseEstimationSeries(
                name=f"PoseEstimationSeries{pascal_case_node}",
                data=mock_interface.pose_data[:num_frames, idx, :],
                unit="pixels",
                reference_frame="top-left corner",
                timestamps=timestamps,
                confidence=np.ones(num_frames),
                confidence_definition="Mock confidence",
            )
            pose_series_list.append(series)

        pose_estimation = PoseEstimation(
            name=camera_name,
            pose_estimation_series=pose_series_list,
            description=f"Pose estimation for {camera_name}",
        )
        pose_module.add(pose_estimation)


def create_nwbfile_with_pose_estimation(
    camera_names: list[str],
    num_nodes: int = 3,
    num_frames: int = 30,
    seed: int = 0,
) -> NWBFile:
    """Create an NWBFile with PoseEstimation data using NeuroConv's MockPoseEstimationInterface.

    Parameters
    ----------
    camera_names : list[str]
        Names of cameras to create pose estimation data for
    num_nodes : int, optional
        Number of keypoint nodes per camera, by default 3
    num_frames : int, optional
        Number of frames of pose data, by default 30
    seed : int, optional
        Random seed for reproducible data generation, by default 0

    Returns
    -------
    NWBFile
        NWB file with pose estimation processing module
    """
    nwbfile = mock_NWBFile()

    pose_module = ProcessingModule(
        name="pose_estimation",
        description="Pose estimation data from DeepLabCut or similar",
    )
    nwbfile.add_processing_module(pose_module)

    mock_interface = MockPoseEstimationInterface(num_nodes=num_nodes, num_samples=num_frames, seed=seed)
    timestamps = mock_interface.get_timestamps()

    _add_pose_estimation_to_module(pose_module, camera_names, mock_interface, timestamps)

    return nwbfile


def create_nwbfile_with_videos_and_pose(
    video_paths: dict[str, Path],
    camera_names: list[str],
    num_nodes: int = 3,
    num_frames: int = 30,
    timestamps: dict[str, np.ndarray] | None = None,
    seed: int = 0,
) -> NWBFile:
    """Create an NWBFile with both external videos and pose estimation.

    Uses NeuroConv's MockPoseEstimationInterface for synthetic pose data generation.

    Parameters
    ----------
    video_paths : dict[str, Path]
        Mapping of video names to file paths
    camera_names : list[str]
        Names of cameras for pose estimation (should match video names pattern)
    num_nodes : int, optional
        Number of keypoint nodes per camera, by default 3
    num_frames : int, optional
        Number of frames of pose data, by default 30
    timestamps : dict[str, np.ndarray], optional
        Mapping of video names to timestamp arrays. If None, uses rate-based.
    seed : int, optional
        Random seed for reproducible data generation, by default 0

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

    # Use first video's timestamps if provided, otherwise use mock's timestamps
    if timestamps:
        pose_timestamps = next(iter(timestamps.values()))
    else:
        mock_interface = MockPoseEstimationInterface(num_nodes=num_nodes, num_samples=num_frames, seed=seed)
        pose_timestamps = mock_interface.get_timestamps()

    mock_interface = MockPoseEstimationInterface(num_nodes=num_nodes, num_samples=len(pose_timestamps), seed=seed)

    _add_pose_estimation_to_module(pose_module, camera_names, mock_interface, pose_timestamps)

    return nwbfile
