"""DANDI NWB pose estimation video overlay widget."""

from __future__ import annotations

import pathlib
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Optional

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
)

if TYPE_CHECKING:
    from dandi.dandiapi import RemoteAsset


class NWBDANDIPoseEstimationWidget(anywidget.AnyWidget):
    """Video player with pose estimation overlay for DANDI-hosted NWB files.

    Overlays DeepLabCut keypoints on streaming video with support for
    camera selection via a settings panel.

    This widget discovers PoseEstimation containers anywhere in the NWB file
    and resolves video paths to S3 URLs via the DANDI API. An interactive
    settings panel allows users to select which camera to display.

    Supports two common NWB patterns:
    1. Single file: both videos and pose estimation in same NWB file
    2. Split files: videos in raw NWB file, pose estimation in processed file

    Parameters
    ----------
    asset : RemoteAsset
        DANDI asset object for the processed NWB file containing pose estimation.
        The dandiset_id and asset path are extracted from this object.
    nwbfile : pynwb.NWBFile, optional
        Pre-loaded NWB file containing pose estimation. If not provided, the widget
        will load the NWB file via streaming from `asset`.
    video_asset : RemoteAsset, optional
        DANDI asset object for the raw NWB file containing videos. If not provided,
        videos are assumed to be accessible relative to `asset`.
    video_nwbfile : pynwb.NWBFile, optional
        Pre-loaded NWB file containing video ImageSeries. If not provided but
        `video_asset` is provided, the widget will extract video URLs from `video_asset`.
        If neither is provided, videos are assumed to be in `nwbfile`.
    keypoint_colors : str or dict, default 'tab10'
        Either a matplotlib colormap name (e.g., 'tab10', 'Set1', 'Paired') for
        automatic color assignment, or a dict mapping keypoint names to hex colors
        (e.g., {'LeftPaw': '#FF0000', 'RightPaw': '#00FF00'}).
    default_camera : str, optional
        Camera to display initially. Falls back to first available if not found.

    Example
    -------
    Single file (videos + pose in same file):

    >>> from dandi.dandiapi import DandiAPIClient
    >>> client = DandiAPIClient()
    >>> dandiset = client.get_dandiset("000409", "draft")
    >>> asset = dandiset.get_asset_by_path("sub-.../sub-..._combined.nwb")
    >>> widget = NWBDANDIPoseEstimationWidget(asset=asset)
    >>> display(widget)

    Split files (videos in raw, pose in processed):

    >>> raw_asset = dandiset.get_asset_by_path("sub-.../sub-..._desc-raw.nwb")
    >>> processed_asset = dandiset.get_asset_by_path("sub-.../sub-..._desc-processed.nwb")
    >>> widget = NWBDANDIPoseEstimationWidget(
    ...     asset=processed_asset,
    ...     video_asset=raw_asset,
    ... )
    >>> display(widget)

    With pre-loaded NWB files (avoids re-loading):

    >>> widget = NWBDANDIPoseEstimationWidget(
    ...     asset=processed_asset,
    ...     nwbfile=nwbfile_processed,
    ...     video_asset=raw_asset,
    ...     video_nwbfile=nwbfile_raw,
    ... )

    Raises
    ------
    ValueError
        If no cameras have both pose data and video.
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

    # Per-frame lazy loading: JS → Python request, Python → JS response
    request_time = traitlets.Float(-1.0).tag(sync=True)
    frame_keypoints = traitlets.Dict({}).tag(sync=True)
    current_frame_time = traitlets.Float(-1.0).tag(sync=True)

    show_labels = traitlets.Bool(True).tag(sync=True)
    visible_keypoints = traitlets.Dict({}).tag(sync=True)

    _esm = pathlib.Path(__file__).parent / "pose_widget.js"
    _css = pathlib.Path(__file__).parent / "pose_widget.css"

    def __init__(
        self,
        asset: RemoteAsset,
        nwbfile: Optional[NWBFile] = None,
        video_asset: Optional[RemoteAsset] = None,
        video_nwbfile: Optional[NWBFile] = None,
        keypoint_colors: str | dict[str, str] = "tab10",
        default_camera: Optional[str] = None,
        **kwargs,
    ):
        # Load NWB file if not provided (for pose estimation)
        if nwbfile is None:
            nwbfile = self._load_nwbfile_from_dandi(asset)

        # Determine video source
        # Priority: video_nwbfile > video_asset > nwbfile
        if video_nwbfile is not None:
            video_source_nwbfile = video_nwbfile
        elif video_asset is not None:
            video_source_nwbfile = self._load_nwbfile_from_dandi(video_asset)
        else:
            video_source_nwbfile = nwbfile

        # Determine which asset to use for video URLs
        video_source_asset = video_asset if video_asset is not None else asset

        # Compute video URLs from DANDI
        video_urls = self._get_video_urls_from_dandi(video_source_nwbfile, video_source_asset)

        # Parse keypoint_colors
        if isinstance(keypoint_colors, str):
            colormap_name = keypoint_colors
            custom_colors = {}
        else:
            colormap_name = "tab10"
            custom_colors = keypoint_colors

        # Get all PoseEstimation containers (location-agnostic)
        pose_containers = discover_pose_estimation_cameras(nwbfile)
        if not pose_containers:
            raise ValueError("NWB file does not contain any PoseEstimation objects")
        available_cameras = list(pose_containers.keys())

        # Get camera info for settings panel display
        available_cameras_info = get_pose_estimation_info(nwbfile)

        # Get ALL available videos (sorted alphabetically)
        available_videos = sorted(video_urls.keys())
        available_videos_info = self._get_video_info(video_source_nwbfile)

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
        self._pose_containers = pose_containers
        self._cmap = plt.get_cmap(colormap_name)
        self._custom_colors = custom_colors
        self._current_series_map = {}
        self._current_timestamps = None

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
            request_time=-1.0,
            frame_keypoints={},
            current_frame_time=-1.0,
            **kwargs,
        )

    @traitlets.observe("selected_camera")
    def _on_camera_selected(self, change):
        """Load pose metadata lazily when a camera is selected."""
        camera_name = change["new"]
        if not camera_name or camera_name in self.all_camera_data:
            return  # Already loaded or no camera selected

        # Signal loading start
        self.loading = True

        try:
            # Store HDF5 series references for per-frame access
            camera_pose = self._pose_containers[camera_name]
            self._current_series_map = {
                name.replace("PoseEstimationSeries", ""): series
                for name, series in camera_pose.pose_estimation_series.items()
            }
            self._current_timestamps = None

            # Load metadata only (no coordinate data)
            camera_data = self._load_camera_metadata(camera_name)

            # Reset stale per-frame state
            self.frame_keypoints = {}
            self.request_time = -1.0
            self.current_frame_time = -1.0

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

    @traitlets.observe("request_time")
    def _on_frame_requested(self, change):
        """Fetch keypoints for a single frame when JS requests a video time."""
        video_time = change["new"]
        if video_time < 0 or self._current_timestamps is None:
            return

        nwb_time = self._current_timestamps[0] + video_time
        frame_idx = int(np.searchsorted(self._current_timestamps, nwb_time))
        frame_idx = min(frame_idx, len(self._current_timestamps) - 1)

        keypoints = {}
        for name, series in self._current_series_map.items():
            try:
                xy = series.data[frame_idx]
                if not np.isnan(xy[0]) and not np.isnan(xy[1]):
                    keypoints[name] = [float(xy[0]), float(xy[1])]
                else:
                    keypoints[name] = None
            except Exception:
                keypoints[name] = None

        self.frame_keypoints = keypoints
        self.current_frame_time = float(self._current_timestamps[frame_idx])

    @staticmethod
    def _load_nwbfile_from_dandi(asset: RemoteAsset) -> NWBFile:
        """Load an NWB file from DANDI via streaming."""
        import h5py
        import remfile
        from pynwb import NWBHDF5IO

        s3_url = asset.get_content_url(follow_redirects=1, strip_query=False)

        remote_file = remfile.File(s3_url)
        h5_file = h5py.File(remote_file, "r")
        io = NWBHDF5IO(file=h5_file, load_namespaces=True)
        return io.read()

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

    @staticmethod
    def _get_video_urls_from_dandi(
        nwbfile: NWBFile,
        asset: RemoteAsset,
    ) -> dict[str, str]:
        """Extract video S3 URLs from NWB file using DANDI API."""
        dandiset = asset.client.get_dandiset(asset.dandiset_id, asset.version_id)

        # Use PurePosixPath because DANDI paths always use forward slashes
        nwb_parent = PurePosixPath(asset.path).parent
        video_series = discover_video_series(nwbfile)
        video_urls = {}

        for name, series in video_series.items():
            relative_path = series.external_file[0].lstrip("./")
            full_path = str(nwb_parent / relative_path)

            video_asset = dandiset.get_asset_by_path(full_path)
            if video_asset is not None:
                video_urls[name] = video_asset.get_content_url(follow_redirects=1, strip_query=False)

        return video_urls

    def _load_camera_metadata(self, camera_name: str) -> dict:
        """Load keypoint metadata for a single camera (no coordinate data).

        Stores timestamps in ``self._current_timestamps`` for per-frame lookup.

        Returns a dict with:
        - keypoint_metadata: {name: {color, label}}
        - n_frames: total number of frames
        - start_time: first timestamp in seconds
        - end_time: last timestamp in seconds
        """
        camera_pose = self._pose_containers[camera_name]

        keypoint_names = list(camera_pose.pose_estimation_series.keys())
        n_kp = len(keypoint_names)

        metadata = {}

        for index, (series_name, series) in enumerate(camera_pose.pose_estimation_series.items()):
            short_name = series_name.replace("PoseEstimationSeries", "")

            if self._current_timestamps is None:
                self._current_timestamps = series.get_timestamps()[:]

            if short_name in self._custom_colors:
                color = self._custom_colors[short_name]
            else:
                if hasattr(self._cmap, "N") and self._cmap.N < 256:
                    rgba = self._cmap(index % self._cmap.N)
                else:
                    rgba = self._cmap(index / max(n_kp - 1, 1))
                color = mcolors.to_hex(rgba)

            metadata[short_name] = {"color": color, "label": short_name}

        timestamps = self._current_timestamps
        return {
            "keypoint_metadata": metadata,
            "n_frames": int(len(timestamps)),
            "start_time": float(timestamps[0]),
            "end_time": float(timestamps[-1]),
        }
