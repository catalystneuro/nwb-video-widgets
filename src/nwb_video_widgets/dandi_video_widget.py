"""DANDI NWB video player widget."""

from __future__ import annotations

import pathlib
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import anywidget
import traitlets
from pynwb import NWBFile

from nwb_video_widgets._utils import discover_video_series, get_video_info, get_video_timestamps

if TYPE_CHECKING:
    from dandi.dandiapi import RemoteAsset


class NWBDANDIVideoPlayer(anywidget.AnyWidget):
    """Display videos from a DANDI-hosted NWB file with synchronized playback.

    This widget discovers ImageSeries with external_file references in the NWB
    file and resolves their paths to S3 URLs via the DANDI API. An interactive
    settings panel allows users to select which videos to display and choose
    between Row, Column, or Grid layouts.

    Parameters
    ----------
    asset : RemoteAsset
        DANDI asset object (from dandiset.get_asset_by_path() or similar).
        The dandiset_id and asset path are extracted from this object.
    nwbfile : pynwb.NWBFile, optional
        Pre-loaded NWB file to avoid re-loading. If not provided, the widget
        will load the NWB file via streaming.
    video_grid : list[list[str]], optional
        A 2D grid layout specifying which videos to display and where.
        Each inner list represents a row of videos. When provided, bypasses
        the interactive settings panel and displays videos in the specified
        grid arrangement. Video names that don't exist are silently skipped.
    video_labels : dict[str, str], optional
        Mapping of video names to custom display labels. If a video name is
        not in the dictionary, the original video name is displayed.

    Example
    -------
    Interactive mode (default):

    >>> from dandi.dandiapi import DandiAPIClient
    >>> client = DandiAPIClient()
    >>> dandiset = client.get_dandiset("000409", "draft")
    >>> asset = dandiset.get_asset_by_path("sub-NYU-39/sub-NYU-39_ses-...nwb")
    >>> widget = NWBDANDIVideoPlayer(asset=asset)
    >>> display(widget)

    With pre-loaded NWB file (avoids re-loading):

    >>> widget = NWBDANDIVideoPlayer(
    ...     asset=asset,
    ...     nwbfile=already_loaded_nwbfile,
    ... )

    Fixed grid mode (single row):

    >>> widget = NWBDANDIVideoPlayer(
    ...     asset=asset,
    ...     video_grid=[["VideoLeftCamera", "VideoBodyCamera", "VideoRightCamera"]]
    ... )

    Fixed grid mode (2x2 grid):

    >>> widget = NWBDANDIVideoPlayer(
    ...     asset=asset,
    ...     video_grid=[
    ...         ["VideoLeftCamera", "VideoRightCamera"],
    ...         ["VideoBodyCamera"],
    ...     ]
    ... )
    """

    video_urls = traitlets.Dict({}).tag(sync=True)
    video_timestamps = traitlets.Dict({}).tag(sync=True)
    available_videos = traitlets.Dict({}).tag(sync=True)
    selected_videos = traitlets.List([]).tag(sync=True)
    layout_mode = traitlets.Unicode("row").tag(sync=True)
    settings_open = traitlets.Bool(False).tag(sync=True)
    grid_layout = traitlets.List([]).tag(sync=True)
    video_labels = traitlets.Dict({}).tag(sync=True)

    _esm = pathlib.Path(__file__).parent / "video_widget.js"
    _css = pathlib.Path(__file__).parent / "video_widget.css"

    def __init__(
        self,
        asset: RemoteAsset,
        nwbfile: Optional[NWBFile] = None,
        video_grid: Optional[list[list[str]]] = None,
        video_labels: Optional[dict[str, str]] = None,
        **kwargs,
    ):
        # Load NWB file if not provided
        if nwbfile is None:
            nwbfile = self._load_nwbfile_from_dandi(asset)

        video_urls = self.get_video_urls_from_dandi(nwbfile, asset)
        video_timestamps = get_video_timestamps(nwbfile)
        available_videos = get_video_info(nwbfile)
        video_labels = video_labels or {}

        if video_grid is not None and len(video_grid) > 0:
            # Fixed grid mode - bypass settings panel
            # Filter to only include videos that exist in video_urls
            filtered_grid = [
                [v for v in row if v in video_urls]
                for row in video_grid
            ]
            # Remove empty rows
            filtered_grid = [row for row in filtered_grid if row]
            # Flatten grid to get selected videos (preserving order)
            selected = [v for row in filtered_grid for v in row]
            super().__init__(
                video_urls=video_urls,
                video_timestamps=video_timestamps,
                available_videos=available_videos,
                selected_videos=selected,
                layout_mode="grid",
                settings_open=False,
                grid_layout=filtered_grid,
                video_labels=video_labels,
                **kwargs,
            )
        else:
            # Interactive mode (current behavior)
            super().__init__(
                video_urls=video_urls,
                video_timestamps=video_timestamps,
                available_videos=available_videos,
                selected_videos=[],
                layout_mode="grid",
                settings_open=True,
                grid_layout=[],
                video_labels=video_labels,
                **kwargs,
            )

    @staticmethod
    def _load_nwbfile_from_dandi(asset: RemoteAsset) -> NWBFile:
        """Load an NWB file from DANDI via streaming.

        Parameters
        ----------
        asset : RemoteAsset
            DANDI asset object

        Returns
        -------
        NWBFile
            Loaded NWB file
        """
        import h5py
        import remfile
        from pynwb import NWBHDF5IO

        s3_url = asset.get_content_url(follow_redirects=1, strip_query=True)

        remote_file = remfile.File(s3_url)
        h5_file = h5py.File(remote_file, "r")
        io = NWBHDF5IO(file=h5_file, load_namespaces=True)
        return io.read()

    @staticmethod
    def get_video_urls_from_dandi(
        nwbfile: NWBFile,
        asset: RemoteAsset,
    ) -> dict[str, str]:
        """Extract video S3 URLs from NWB file using DANDI API.

        Videos in NWB files are stored as ImageSeries with external_file paths.
        This function finds all ImageSeries with external files and resolves
        their relative paths to full S3 URLs using the DANDI API.

        Parameters
        ----------
        nwbfile : pynwb.NWBFile
            NWB file containing video ImageSeries in acquisition
        asset : RemoteAsset
            DANDI asset object for the NWB file

        Returns
        -------
        dict[str, str]
            Mapping of video names to S3 URLs
        """
        from dandi.dandiapi import DandiAPIClient

        client = DandiAPIClient()
        dandiset = client.get_dandiset(asset.dandiset_id, asset.version_id)

        nwb_parent = Path(asset.path).parent
        video_series = discover_video_series(nwbfile)
        video_urls = {}

        for name, series in video_series.items():
            relative_path = series.external_file[0].lstrip("./")
            full_path = str(nwb_parent / relative_path)

            video_asset = dandiset.get_asset_by_path(full_path)
            if video_asset is not None:
                video_urls[name] = video_asset.get_content_url(
                    follow_redirects=1, strip_query=True
                )

        return video_urls
