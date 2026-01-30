"""DANDI NWB video player widget."""

import pathlib
from pathlib import Path
from typing import Optional

import anywidget
import traitlets
from pynwb import NWBFile

from nwb_video_widgets._utils import discover_video_series, get_video_timestamps

DEFAULT_GRID_LAYOUT = [["VideoLeftCamera", "VideoBodyCamera", "VideoRightCamera"]]


class NWBDANDIVideoPlayer(anywidget.AnyWidget):
    """Display videos from a DANDI-hosted NWB file with synchronized playback.

    This widget discovers ImageSeries with external_file references in the NWB
    file and resolves their paths to S3 URLs via the DANDI API.

    Parameters
    ----------
    asset_path : str
        Path to the NWB asset within the dandiset
        (e.g., "sub-001/sub-001_ses-001_ecephys.nwb")
    dandiset_id : str
        DANDI archive dandiset ID (e.g., "000409")
    nwbfile : pynwb.NWBFile, optional
        Pre-loaded NWB file to avoid re-loading. If not provided, the widget
        will load the NWB file via streaming.
    version : str, optional
        Dandiset version. Default: "draft"
    grid_layout : list of list of str, optional
        Grid layout specifying which videos to display and how to arrange them.
        Each inner list represents a row, and each string is a video series name.
        Videos not found in the NWB file are silently skipped.
        Default: [["VideoLeftCamera", "VideoBodyCamera", "VideoRightCamera"]]

    Example
    -------
    >>> widget = NWBDANDIVideoPlayer(
    ...     asset_path="sub-NYU-39/sub-NYU-39_ses-2022-10-05_ecephys.nwb",
    ...     dandiset_id="000409",
    ... )
    >>> display(widget)

    With pre-loaded NWB file (avoids re-loading):

    >>> widget = NWBDANDIVideoPlayer(
    ...     asset_path="sub-NYU-39/sub-NYU-39_ses-2022-10-05_ecephys.nwb",
    ...     dandiset_id="000409",
    ...     nwbfile=already_loaded_nwbfile,
    ... )
    """

    video_urls = traitlets.Dict({}).tag(sync=True)
    grid_layout = traitlets.List([]).tag(sync=True)
    video_timestamps = traitlets.Dict({}).tag(sync=True)

    _esm = pathlib.Path(__file__).parent / "video_widget.js"
    _css = pathlib.Path(__file__).parent / "video_widget.css"

    def __init__(
        self,
        asset_path: str,
        dandiset_id: str,
        nwbfile: Optional[NWBFile] = None,
        version: str = "draft",
        grid_layout: Optional[list[list[str]]] = None,
        **kwargs,
    ):
        # Load NWB file if not provided
        if nwbfile is None:
            nwbfile = self._load_nwbfile_from_dandi(asset_path, dandiset_id, version)

        video_urls = self.get_video_urls_from_dandi(
            nwbfile, asset_path, dandiset_id, version
        )
        video_timestamps = get_video_timestamps(nwbfile)
        layout = grid_layout if grid_layout is not None else DEFAULT_GRID_LAYOUT

        super().__init__(
            video_urls=video_urls,
            grid_layout=layout,
            video_timestamps=video_timestamps,
            **kwargs,
        )

    @staticmethod
    def _load_nwbfile_from_dandi(
        asset_path: str, dandiset_id: str, version: str = "draft"
    ) -> NWBFile:
        """Load an NWB file from DANDI via streaming.

        Parameters
        ----------
        asset_path : str
            Path to the NWB asset within the dandiset
        dandiset_id : str
            DANDI archive dandiset ID
        version : str
            Dandiset version

        Returns
        -------
        NWBFile
            Loaded NWB file
        """
        import h5py
        import remfile
        from dandi.dandiapi import DandiAPIClient
        from pynwb import NWBHDF5IO

        client = DandiAPIClient()
        dandiset = client.get_dandiset(dandiset_id, version)
        asset = dandiset.get_asset_by_path(asset_path)
        s3_url = asset.get_content_url(follow_redirects=1, strip_query=True)

        remote_file = remfile.File(s3_url)
        h5_file = h5py.File(remote_file, "r")
        io = NWBHDF5IO(file=h5_file, load_namespaces=True)
        return io.read()

    @staticmethod
    def get_video_urls_from_dandi(
        nwbfile: NWBFile,
        asset_path: str,
        dandiset_id: str,
        version: str = "draft",
    ) -> dict[str, str]:
        """Extract video S3 URLs from NWB file using DANDI API.

        Videos in NWB files are stored as ImageSeries with external_file paths.
        This function finds all ImageSeries with external files and resolves
        their relative paths to full S3 URLs using the DANDI API.

        Parameters
        ----------
        nwbfile : pynwb.NWBFile
            NWB file containing video ImageSeries in acquisition
        asset_path : str
            Path to the NWB asset within the dandiset
        dandiset_id : str
            DANDI archive dandiset ID
        version : str
            Dandiset version

        Returns
        -------
        dict[str, str]
            Mapping of video names to S3 URLs
        """
        from dandi.dandiapi import DandiAPIClient

        client = DandiAPIClient()
        dandiset = client.get_dandiset(dandiset_id, version)

        nwb_parent = Path(asset_path).parent
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
