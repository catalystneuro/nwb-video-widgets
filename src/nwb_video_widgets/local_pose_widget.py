"""Local NWB pose estimation video overlay widget."""

import pathlib
from pathlib import Path
from typing import Optional

import anywidget
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import traitlets
from pynwb import NWBFile

from nwb_video_widgets._utils import (
    discover_pose_estimation_cameras,
    discover_video_series,
    get_pose_estimation_info,
    start_video_server,
)


class NWBLocalPoseEstimationWidget(anywidget.AnyWidget):
    """Video player with pose estimation overlay for local NWB files.

    Overlays DeepLabCut keypoints on streaming video with support for
    camera selection via a settings panel.

    This widget discovers PoseEstimation containers in processing['pose_estimation']
    and resolves video paths relative to the NWB file location. An interactive
    settings panel allows users to select which camera to display.

    Supports two common NWB patterns:
    1. Single file: both videos and pose estimation in same NWB file
    2. Split files: videos in raw NWB file, pose estimation in processed file

    Parameters
    ----------
    nwbfile : pynwb.NWBFile
        NWB file containing pose estimation in processing['pose_estimation'].
        Must have been loaded from disk.
    video_nwbfile : pynwb.NWBFile, optional
        NWB file containing video ImageSeries in acquisition. If not provided,
        videos are assumed to be in `nwbfile`. Use this when videos are in a
        separate raw file from the processed pose data.
    keypoint_colors : str or dict, default 'tab10'
        Either a matplotlib colormap name (e.g., 'tab10', 'Set1', 'Paired') for
        automatic color assignment, or a dict mapping keypoint names to hex colors
        (e.g., {'LeftPaw': '#FF0000', 'RightPaw': '#00FF00'}).
    default_camera : str, optional
        Camera to display initially. Falls back to first available if not found.

    Example
    -------
    Single file (videos + pose in same file):

    >>> from pynwb import NWBHDF5IO
    >>> with NWBHDF5IO("experiment.nwb", "r") as io:
    ...     nwbfile = io.read()
    ...     widget = NWBLocalPoseEstimationWidget(nwbfile)
    ...     display(widget)

    Split files (videos in raw, pose in processed):

    >>> io_raw = NWBHDF5IO("raw.nwb", "r")
    >>> io_processed = NWBHDF5IO("processed.nwb", "r")
    >>> nwbfile_raw = io_raw.read()
    >>> nwbfile_processed = io_processed.read()
    >>> widget = NWBLocalPoseEstimationWidget(
    ...     nwbfile=nwbfile_processed,
    ...     video_nwbfile=nwbfile_raw,
    ... )
    >>> display(widget)

    Raises
    ------
    ValueError
        If the NWB file was not loaded from disk (read_io is None) or
        if no cameras have both pose data and video.
    """

    selected_camera = traitlets.Unicode("").tag(sync=True)
    available_cameras = traitlets.List([]).tag(sync=True)
    available_cameras_info = traitlets.Dict({}).tag(sync=True)

    # Video selection - users explicitly match cameras to videos
    available_videos = traitlets.List([]).tag(sync=True)
    available_videos_info = traitlets.Dict({}).tag(sync=True)
    video_name_to_url = traitlets.Dict({}).tag(sync=True)  # Video name -> URL mapping
    camera_to_video = traitlets.Dict({}).tag(sync=True)  # Camera -> video name mapping

    settings_open = traitlets.Bool(True).tag(sync=True)

    # Pose data for cameras - loaded lazily when selected
    all_camera_data = traitlets.Dict({}).tag(sync=True)

    # Loading state for progress indicator
    loading = traitlets.Bool(False).tag(sync=True)

    show_labels = traitlets.Bool(True).tag(sync=True)
    visible_keypoints = traitlets.Dict({}).tag(sync=True)

    _esm = pathlib.Path(__file__).parent / "pose_widget.js"
    _css = pathlib.Path(__file__).parent / "pose_widget.css"

    def __init__(
        self,
        nwbfile: NWBFile,
        video_nwbfile: Optional[NWBFile] = None,
        keypoint_colors: str | dict[str, str] = "tab10",
        default_camera: Optional[str] = None,
        **kwargs,
    ):
        # Use video_nwbfile for videos if provided, otherwise use nwbfile
        video_source = video_nwbfile if video_nwbfile is not None else nwbfile

        # Compute video URLs from local files
        video_urls = self._get_video_urls_from_local(video_source)

        # Parse keypoint_colors
        if isinstance(keypoint_colors, str):
            colormap_name = keypoint_colors
            custom_colors = {}
        else:
            colormap_name = "tab10"
            custom_colors = keypoint_colors

        # Get pose estimation container
        if "pose_estimation" not in nwbfile.processing:
            raise ValueError("NWB file does not contain pose_estimation processing module")
        pose_estimation = nwbfile.processing["pose_estimation"]

        # Get all PoseEstimation containers (excludes Skeletons and other metadata)
        pose_containers = discover_pose_estimation_cameras(nwbfile)
        available_cameras = list(pose_containers.keys())

        # Get camera info for settings panel display
        available_cameras_info = get_pose_estimation_info(nwbfile)

        # Get ALL available videos (sorted alphabetically)
        available_videos = sorted(video_urls.keys())
        available_videos_info = self._get_video_info(video_source)

        # Video name to URL mapping (sent to JS for URL resolution)
        video_name_to_url = video_urls

        # Start with empty mapping - users explicitly select videos
        camera_to_video = {}

        # Select default camera - start with empty to show settings
        if default_camera and default_camera in available_cameras:
            selected_camera = default_camera
        else:
            selected_camera = ""

        # Store references for lazy loading (not synced to JS)
        self._pose_estimation = pose_estimation
        self._cmap = plt.get_cmap(colormap_name)
        self._custom_colors = custom_colors

        super().__init__(
            selected_camera=selected_camera,
            available_cameras=available_cameras,
            available_cameras_info=available_cameras_info,
            available_videos=available_videos,
            available_videos_info=available_videos_info,
            video_name_to_url=video_name_to_url,
            camera_to_video=camera_to_video,
            all_camera_data={},  # Start empty, load lazily
            visible_keypoints={},  # Populated as cameras are loaded
            settings_open=True,
            **kwargs,
        )

    @traitlets.observe("selected_camera")
    def _on_camera_selected(self, change):
        """Load pose data lazily when a camera is selected."""
        camera_name = change["new"]
        if not camera_name or camera_name in self.all_camera_data:
            return  # Already loaded or no camera selected

        # Signal loading start
        self.loading = True

        try:
            # Load pose data for this camera
            camera_data = self._load_camera_pose_data(
                self._pose_estimation, camera_name, self._cmap, self._custom_colors
            )

            # Update all_camera_data (must create new dict for traitlets to detect change)
            self.all_camera_data = {**self.all_camera_data, camera_name: camera_data}

            # Add any new keypoints to visible_keypoints
            new_keypoints = {**self.visible_keypoints}
            for name in camera_data["keypoint_metadata"].keys():
                if name not in new_keypoints:
                    new_keypoints[name] = True
            if new_keypoints != self.visible_keypoints:
                self.visible_keypoints = new_keypoints
        finally:
            # Signal loading complete
            self.loading = False

    @staticmethod
    def _get_video_info(nwbfile: NWBFile) -> dict[str, dict]:
        """Get metadata for all video series."""
        video_series = discover_video_series(nwbfile)
        info = {}

        for name, series in video_series.items():
            timestamps = None
            if series.timestamps is not None:
                timestamps = series.timestamps[:]
            elif series.starting_time is not None and series.rate is not None:
                n_frames = series.data.shape[0] if hasattr(series.data, "shape") else 0
                timestamps = np.arange(n_frames) / series.rate + series.starting_time

            if timestamps is not None and len(timestamps) > 0:
                info[name] = {
                    "start": float(timestamps[0]),
                    "end": float(timestamps[-1]),
                    "frames": len(timestamps),
                }
            else:
                info[name] = {"start": 0, "end": 0, "frames": 0}

        return info

    @traitlets.observe("camera_to_video")
    def _on_camera_to_video_changed(self, change):
        """Update video URL when user changes camera-to-video mapping."""
        # The camera_to_video dict now stores video URLs directly
        # This observer can be used for any side effects needed
        pass

    @staticmethod
    def _get_video_urls_from_local(nwbfile: NWBFile) -> dict[str, str]:
        """Extract video file URLs from a local NWB file.

        Resolves external_file paths relative to the NWB file location and
        serves them via a local HTTP server for browser playback.
        """
        if nwbfile.read_io is None or not hasattr(nwbfile.read_io, "source"):
            raise ValueError(
                "NWB file must be loaded from disk to resolve video paths. "
                "The nwbfile.read_io attribute is None."
            )

        nwbfile_path = Path(nwbfile.read_io.source)
        base_dir = nwbfile_path.parent
        video_series = discover_video_series(nwbfile)
        video_urls = {}

        if not video_series:
            return video_urls

        # Collect all video directories and start servers
        video_dirs: set[Path] = set()
        for series in video_series.values():
            relative_path = series.external_file[0].lstrip("./")
            video_path = (base_dir / relative_path).resolve()
            video_dirs.add(video_path.parent)

        # Start servers for each unique directory
        dir_to_port: dict[Path, int] = {}
        for video_dir in video_dirs:
            port = start_video_server(video_dir)
            dir_to_port[video_dir] = port

        # Build URLs using the local HTTP server
        for name, series in video_series.items():
            relative_path = series.external_file[0].lstrip("./")
            video_path = (base_dir / relative_path).resolve()
            video_dir = video_path.parent
            port = dir_to_port[video_dir]
            video_urls[name] = f"http://127.0.0.1:{port}/{video_path.name}"

        return video_urls

    @staticmethod
    def _load_camera_pose_data(
        pose_estimation, camera_name: str, cmap, custom_colors: dict
    ) -> dict:
        """Load pose data for a single camera.

        Returns a dict with:
        - keypoint_metadata: {name: {color, label}}
        - pose_coordinates: {name: [[x, y], ...]} as JSON-serializable lists
        - timestamps: [t0, t1, ...] as JSON-serializable list
        """
        camera_pose = pose_estimation[camera_name]

        keypoint_names = list(camera_pose.pose_estimation_series.keys())
        n_kp = len(keypoint_names)

        metadata = {}
        coordinates = {}
        timestamps = None

        for index, (series_name, series) in enumerate(
            camera_pose.pose_estimation_series.items()
        ):
            short_name = series_name.replace("PoseEstimationSeries", "")

            # Get coordinates - iterate to build list without memory duplication
            data = series.data[:]
            coords_list = []
            for x, y in data:
                if np.isnan(x) or np.isnan(y):
                    coords_list.append(None)
                else:
                    coords_list.append([float(x), float(y)])
            coordinates[short_name] = coords_list

            if timestamps is None:
                timestamps = series.timestamps[:].tolist()

            # Assign color from custom dict or colormap
            if short_name in custom_colors:
                color = custom_colors[short_name]
            else:
                if hasattr(cmap, "N") and cmap.N < 256:
                    rgba = cmap(index % cmap.N)
                else:
                    rgba = cmap(index / max(n_kp - 1, 1))
                color = mcolors.to_hex(rgba)

            metadata[short_name] = {"color": color, "label": short_name}

        return {
            "keypoint_metadata": metadata,
            "pose_coordinates": coordinates,
            "timestamps": timestamps,
        }
