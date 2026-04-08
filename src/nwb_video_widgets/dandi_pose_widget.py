"""DANDI NWB pose estimation video overlay widget."""

from __future__ import annotations

import pathlib
import warnings
from typing import TYPE_CHECKING, Optional

import anywidget
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import traitlets
from pynwb import NWBFile

from nwb_video_widgets._utils import (
    discover_pose_estimation_cameras,
    get_pose_estimation_info,
)

if TYPE_CHECKING:
    from dandi.dandiapi import RemoteAsset


class NWBDANDIPoseEstimationWidget(anywidget.AnyWidget):
    """Video player with pose estimation overlay for DANDI-hosted NWB files.

    Overlays DeepLabCut keypoints on streaming video with support for
    camera selection via a settings panel.

    Python injects seed traitlets extracted from the asset objects. JavaScript
    fetches video metadata from DANDI via LINDI and the DANDI REST API,
    then populates ``video_urls`` and ``video_timing``.

    Both traitlets are bidirectional: once JavaScript fills them, the values
    are synced back to Python automatically.

    Supports two common NWB patterns:
    1. Single file: both videos and pose estimation in same NWB file
    2. Split files: videos in raw NWB file, pose estimation in processed file

    Parameters
    ----------
    asset : RemoteAsset
        DANDI asset object for the processed NWB file containing pose estimation.
        Seeds (NWB URL, asset ID, dandiset ID, etc.) are extracted from this.
    nwbfile : pynwb.NWBFile, optional
        Pre-loaded NWB file containing pose estimation. If not provided, the widget
        will load the NWB file via streaming from ``asset``.
    video_asset : RemoteAsset, optional
        DANDI asset object for the raw NWB file containing videos. If not provided,
        videos are assumed to be accessible relative to ``asset``.
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

    Raises
    ------
    ValueError
        If no cameras have both pose data and video.
    """

    selected_camera = traitlets.Unicode("").tag(sync=True)
    available_cameras = traitlets.List([]).tag(sync=True)
    available_cameras_info = traitlets.Dict({}).tag(sync=True)

    camera_to_video = traitlets.Dict({}).tag(sync=True)  # Camera -> video name mapping

    settings_open = traitlets.Bool(True).tag(sync=True)

    # Pose data for cameras - loaded lazily when selected
    all_camera_data = traitlets.Dict({}).tag(sync=True)

    # Loading state for progress indicator
    loading = traitlets.Bool(False).tag(sync=True)

    show_labels = traitlets.Bool(True).tag(sync=True)
    visible_keypoints = traitlets.Dict({}).tag(sync=True)

    # Seed traitlets for the pose/processed NWB file.
    # Defaults are empty strings; always overwritten in __init__ with values from the asset.
    _nwb_url = traitlets.Unicode("").tag(sync=True)
    _nwb_asset_id = traitlets.Unicode("").tag(sync=True)
    _nwb_asset_path = traitlets.Unicode("").tag(sync=True)
    _dandiset_id = traitlets.Unicode("").tag(sync=True)
    _version_id = traitlets.Unicode("").tag(sync=True)
    _dandi_api_url = traitlets.Unicode("").tag(sync=True)
    _dandi_api_key = traitlets.Unicode("").tag(sync=True)

    # Seed traitlets for the video/raw NWB file (split-file case).
    # If empty, JavaScript falls back to the main _nwb_* seeds.
    _video_nwb_url = traitlets.Unicode("").tag(sync=True)
    _video_nwb_asset_id = traitlets.Unicode("").tag(sync=True)
    _video_nwb_asset_path = traitlets.Unicode("").tag(sync=True)

    # Bidirectional: empty at init, populated by JavaScript after LINDI/DANDI resolution.
    _video_urls = traitlets.Dict({}).tag(sync=True)  # {name: url_string}
    _video_timing = traitlets.Dict({}).tag(sync=True)  # {name: {start: float, end: float}}

    # Set to True by JavaScript when LINDI returns 404. Python observes this
    # and falls back to targeted h5py reads.
    _lindi_failed = traitlets.Bool(False).tag(sync=True)

    _esm = pathlib.Path(__file__).parent / "pose_widget.js"
    _css = pathlib.Path(__file__).parent / "pose_widget.css"

    def __init__(
        self,
        asset: RemoteAsset,
        nwbfile: Optional[NWBFile] = None,
        video_asset: Optional[RemoteAsset] = None,
        keypoint_colors: str | dict[str, str] = "tab10",
        default_camera: Optional[str] = None,
        video_nwbfile=None,
        **kwargs,
    ):
        if video_nwbfile is not None:
            warnings.warn(
                "The 'video_nwbfile' parameter no longer has any effect. "
                "Video metadata is now fetched in JavaScript via LINDI. "
                "This parameter will be removed in v0.1.8.",
                DeprecationWarning,
                stacklevel=2,
            )

        # Load NWB file if not provided (still needed for pose coordinate data)
        if nwbfile is None:
            nwbfile = self._load_nwbfile_from_dandi(asset)

        # Extract API key from auth header (same key works for both assets)
        auth_header = asset.client.session.headers.get("Authorization", "")
        api_key = auth_header[6:] if auth_header.startswith("token ") else ""

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

        # Select default camera
        if default_camera and default_camera in available_cameras:
            selected_camera = default_camera
        else:
            selected_camera = ""

        # Store references for lazy loading (not synced to JS)
        self._pose_containers = pose_containers
        self._cmap = plt.get_cmap(colormap_name)
        self._custom_colors = custom_colors

        # Build video seed kwargs for split-file case
        video_seed_kwargs = {}
        if video_asset is not None:
            video_seed_kwargs = {
                "_video_nwb_url": video_asset.get_content_url(follow_redirects=1, strip_query=False),
                "_video_nwb_asset_id": video_asset.identifier,
                "_video_nwb_asset_path": video_asset.path,
            }

        super().__init__(
            selected_camera=selected_camera,
            available_cameras=available_cameras,
            available_cameras_info=available_cameras_info,
            camera_to_video={},
            all_camera_data={},
            visible_keypoints={},
            settings_open=True,
            _nwb_url=asset.get_content_url(follow_redirects=1, strip_query=False),
            _nwb_asset_id=asset.identifier,
            _nwb_asset_path=asset.path,
            _dandiset_id=asset.dandiset_id,
            _version_id=asset.version_id,
            _dandi_api_url=asset.client.api_url,
            _dandi_api_key=api_key,
            _video_urls={},
            _video_timing={},
            # _video_nwb_* defaults to "" (traitlet default); overridden by video_seed_kwargs
            # when video_asset is provided.
            **{"_video_nwb_url": "", "_video_nwb_asset_id": "", "_video_nwb_asset_path": "", **video_seed_kwargs},
            **kwargs,
        )

    @traitlets.observe("_lindi_failed")
    def _on_lindi_failed(self, change):
        """Fall back to targeted h5py reads when LINDI is unavailable."""
        if not change["new"]:
            return

        from nwb_video_widgets._utils import _resolve_video_from_dandi_hdf5

        # Use video asset seeds if available, otherwise main asset seeds
        nwb_s3_url = self._video_nwb_url or self._nwb_url
        asset_path = self._video_nwb_asset_path or self._nwb_asset_path

        video_urls, video_timing = _resolve_video_from_dandi_hdf5(
            nwb_s3_url=nwb_s3_url,
            asset_path=asset_path,
            dandiset_id=self._dandiset_id,
            version_id=self._version_id,
            dandi_api_url=self._dandi_api_url,
            dandi_api_key=self._dandi_api_key,
        )
        self._video_urls = video_urls
        self._video_timing = video_timing

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
                self._pose_containers, camera_name, self._cmap, self._custom_colors
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
    def _load_camera_pose_data(pose_containers: dict, camera_name: str, cmap, custom_colors: dict) -> dict:
        """Load pose data for a single camera.

        Returns a dict with:
        - keypoint_metadata: {name: {color, label}}
        - pose_coordinates: {name: [[x, y], ...]} as JSON-serializable lists
        - timestamps: [t0, t1, ...] as JSON-serializable list
        """
        camera_pose = pose_containers[camera_name]

        keypoint_names = list(camera_pose.pose_estimation_series.keys())
        n_kp = len(keypoint_names)

        metadata = {}
        coordinates = {}
        timestamps = None

        for index, (series_name, series) in enumerate(camera_pose.pose_estimation_series.items()):
            short_name = series_name.replace("PoseEstimationSeries", "")

            # Bulk C-level conversion via tolist(), then replace sparse NaN rows with None.
            data = series.data[:]
            nan_mask = np.isnan(data).any(axis=1)
            coords_list = data.tolist()
            for nan_index in np.flatnonzero(nan_mask):
                coords_list[nan_index] = None
            coordinates[short_name] = coords_list

            if timestamps is None:
                timestamps = series.get_timestamps()[:].tolist()

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
