"""Synthetic NWB file generation for testing."""

from pathlib import Path

import numpy as np
from neuroconv.tools.testing.mock_interfaces import MockPoseEstimationInterface
from pynwb import NWBFile
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


def _add_cameras_via_mock_interface(
    nwbfile: NWBFile,
    camera_names: list[str],
    num_nodes: int,
    num_frames: int,
    seed: int,
) -> None:
    """Add PoseEstimation containers to an NWBFile using MockPoseEstimationInterface.add_to_nwbfile.

    Uses add_to_nwbfile for the first camera (which creates the behavior module, device,
    and skeleton), then adds subsequent cameras directly to the existing behavior module.

    Parameters
    ----------
    nwbfile : NWBFile
        The NWB file to add pose estimation data to
    camera_names : list[str]
        Names for each PoseEstimation container
    num_nodes : int
        Number of keypoint nodes per camera
    num_frames : int
        Number of frames of pose data
    seed : int
        Random seed for reproducible data generation
    """
    from ndx_pose import PoseEstimation, PoseEstimationSeries

    for i, camera_name in enumerate(camera_names):
        mock = MockPoseEstimationInterface(
            pose_estimation_metadata_key=camera_name,
            num_nodes=num_nodes,
            num_samples=num_frames,
            seed=seed,
        )
        if i == 0:
            # First camera: use add_to_nwbfile to create the behavior module, device, and skeleton
            mock.add_to_nwbfile(nwbfile)
        else:
            # Additional cameras: add PoseEstimation directly to the existing behavior module
            # (avoids Device/Skeleton naming conflicts from repeated add_to_nwbfile calls)
            behavior_module = nwbfile.processing["behavior"]
            timestamps = mock.get_timestamps()
            pose_series_list = []
            for idx, node_name in enumerate(mock.nodes):
                pascal_case_node = "".join(word.capitalize() for word in node_name.replace("_", " ").split())
                series = PoseEstimationSeries(
                    name=f"PoseEstimationSeries{pascal_case_node}",
                    data=mock.pose_data[:num_frames, idx, :],
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
            behavior_module.add(pose_estimation)


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
        NWB file with pose estimation in the behavior processing module
    """
    nwbfile = mock_NWBFile()
    _add_cameras_via_mock_interface(nwbfile, camera_names, num_nodes, num_frames, seed)
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

    _add_cameras_via_mock_interface(nwbfile, camera_names, num_nodes, num_frames, seed)

    return nwbfile
