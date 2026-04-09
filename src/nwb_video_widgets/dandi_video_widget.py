"""DANDI NWB video player widget."""

from __future__ import annotations

import pathlib
import warnings
from typing import TYPE_CHECKING, Optional

import anywidget
import traitlets

if TYPE_CHECKING:
    from dandi.dandiapi import RemoteAsset


class NWBDANDIVideoPlayer(anywidget.AnyWidget):
    """Display videos from a DANDI-hosted NWB file with synchronized playback.

    Python injects seed traitlets extracted from the asset. JavaScript fetches
    video metadata directly from DANDI via LINDI and the DANDI REST API,
    then populates ``video_urls`` and ``video_timing``.

    Both traitlets are bidirectional: once JavaScript fills them, the values
    are synced back to Python automatically.

    Parameters
    ----------
    asset : RemoteAsset
        DANDI asset object (from dandiset.get_asset_by_path() or similar).
        Seeds (NWB URL, asset ID, dandiset ID, etc.) are extracted from this.
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

    # Seed traitlets - set by Python, read by JavaScript.
    # Defaults are empty strings; always overwritten in __init__ with values from the asset.
    _nwb_url = traitlets.Unicode("").tag(sync=True)
    _nwb_asset_id = traitlets.Unicode("").tag(sync=True)
    _nwb_asset_path = traitlets.Unicode("").tag(sync=True)
    _dandiset_id = traitlets.Unicode("").tag(sync=True)
    _version_id = traitlets.Unicode("").tag(sync=True)
    _dandi_api_url = traitlets.Unicode("").tag(sync=True)
    _dandi_api_key = traitlets.Unicode("").tag(sync=True)

    # Bidirectional: empty at init, populated by JavaScript after LINDI/DANDI resolution.
    _video_urls = traitlets.Dict({}).tag(sync=True)  # {name: url_string}
    _video_timing = traitlets.Dict({}).tag(sync=True)  # {name: {start: float, end: float}}

    # Set to True by JavaScript when LINDI returns 404. Python observes this
    # and falls back to targeted h5py reads.
    _lindi_failed = traitlets.Bool(False).tag(sync=True)

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
        video_grid: Optional[list[list[str]]] = None,
        video_labels: Optional[dict[str, str]] = None,
        nwbfile=None,
        **kwargs,
    ):
        if nwbfile is not None:
            warnings.warn(
                "The 'nwbfile' parameter no longer has any effect. "
                "Video metadata is now fetched in JavaScript via LINDI. "
                "This parameter will be removed in v0.1.8.",
                DeprecationWarning,
                stacklevel=2,
            )

        auth_header = asset.client.session.headers.get("Authorization", "")
        api_key = auth_header[6:] if auth_header.startswith("token ") else ""

        super().__init__(
            _nwb_url=asset.get_content_url(follow_redirects=1, strip_query=False),
            _nwb_asset_id=asset.identifier,
            _nwb_asset_path=asset.path,
            _dandiset_id=asset.dandiset_id,
            _version_id=asset.version_id,
            _dandi_api_url=asset.client.api_url,
            _dandi_api_key=api_key,
            _video_urls={},
            _video_timing={},
            selected_videos=[],
            layout_mode="grid",
            settings_open=not bool(video_grid),
            grid_layout=list(video_grid) if video_grid else [],
            video_labels=video_labels or {},
            **kwargs,
        )

    @traitlets.observe("_lindi_failed")
    def _on_lindi_failed(self, change):
        """Fall back to targeted h5py reads when LINDI is unavailable."""
        if not change["new"]:
            return

        from nwb_video_widgets._utils import _resolve_video_from_dandi_hdf5

        video_urls, video_timing = _resolve_video_from_dandi_hdf5(
            nwb_s3_url=self._nwb_url,
            asset_path=self._nwb_asset_path,
            dandiset_id=self._dandiset_id,
            version_id=self._version_id,
            dandi_api_url=self._dandi_api_url,
            dandi_api_key=self._dandi_api_key,
        )
        self._video_urls = video_urls
        self._video_timing = video_timing

    @classmethod
    def from_url(cls, url: str, token: str = "", **kwargs) -> NWBDANDIVideoPlayer:
        """Create a widget from a DANDI URL.

        Parameters
        ----------
        url : str
            A DANDI API URL pointing to an NWB asset. Supported formats:
            ``https://api.dandiarchive.org/api/dandisets/{id}/versions/{version}/assets/?path={path}``
            or ``https://api.dandiarchive.org/api/assets/{uuid}/download/``.
        token : str, optional
            DANDI API token for embargoed dandisets.

        Returns
        -------
        NWBDANDIVideoPlayer
        """
        from dandi.dandiarchive import parse_dandi_url

        parsed = parse_dandi_url(url)
        client = parsed.get_client()
        if token:
            client.dandi_authenticate(token)
        assets = list(parsed.get_assets(client))
        if not assets:
            raise ValueError(f"No asset found at {url}")
        return cls(asset=assets[0], **kwargs)
