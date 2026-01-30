"""Local NWB video player widget."""

import pathlib
from pathlib import Path
from typing import Optional

import anywidget
import traitlets
from pynwb import NWBFile

from nwb_video_widgets._utils import discover_video_series, get_video_timestamps

DEFAULT_GRID_LAYOUT = [["VideoLeftCamera", "VideoBodyCamera", "VideoRightCamera"]]


class NWBLocalVideoPlayer(anywidget.AnyWidget):
    """Display local videos from an NWB file with synchronized playback.

    This widget discovers ImageSeries with external_file references in the NWB
    file and resolves their paths relative to the NWB file location.

    Parameters
    ----------
    nwbfile : pynwb.NWBFile
        NWB file containing video ImageSeries in acquisition. Must have been
        loaded from disk (i.e., nwbfile.read_io must not be None).
    grid_layout : list of list of str, optional
        Grid layout specifying which videos to display and how to arrange them.
        Each inner list represents a row, and each string is a video series name.
        Videos not found in the NWB file are silently skipped.
        Default: [["VideoLeftCamera", "VideoBodyCamera", "VideoRightCamera"]]

    Example
    -------
    >>> from pynwb import NWBHDF5IO
    >>> with NWBHDF5IO("experiment.nwb", "r") as io:
    ...     nwbfile = io.read()
    ...     widget = NWBLocalVideoPlayer(nwbfile)
    ...     display(widget)

    Custom layout:

    >>> widget = NWBLocalVideoPlayer(
    ...     nwbfile,
    ...     grid_layout=[["VideoLeftCamera", "VideoRightCamera"]]
    ... )

    Raises
    ------
    ValueError
        If the NWB file was not loaded from disk (read_io is None)
    """

    video_urls = traitlets.Dict({}).tag(sync=True)
    grid_layout = traitlets.List([]).tag(sync=True)
    video_timestamps = traitlets.Dict({}).tag(sync=True)

    _esm = pathlib.Path(__file__).parent / "video_widget.js"
    _css = pathlib.Path(__file__).parent / "video_widget.css"

    def __init__(
        self,
        nwbfile: NWBFile,
        grid_layout: Optional[list[list[str]]] = None,
        **kwargs,
    ):
        video_urls = self.get_video_urls_from_local(nwbfile)
        video_timestamps = get_video_timestamps(nwbfile)
        layout = grid_layout if grid_layout is not None else DEFAULT_GRID_LAYOUT

        super().__init__(
            video_urls=video_urls,
            grid_layout=layout,
            video_timestamps=video_timestamps,
            **kwargs,
        )

    @staticmethod
    def get_video_urls_from_local(nwbfile: NWBFile) -> dict[str, str]:
        """Extract video file URLs from a local NWB file.

        Resolves external_file paths relative to the NWB file location and
        converts them to file:// URLs for browser playback.

        Parameters
        ----------
        nwbfile : pynwb.NWBFile
            NWB file containing video ImageSeries in acquisition

        Returns
        -------
        dict[str, str]
            Mapping of video names to file:// URLs

        Raises
        ------
        ValueError
            If the NWB file was not loaded from disk
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

        for name, series in video_series.items():
            relative_path = series.external_file[0].lstrip("./")
            absolute_path = (base_dir / relative_path).resolve()
            video_urls[name] = f"file://{absolute_path}"

        return video_urls
