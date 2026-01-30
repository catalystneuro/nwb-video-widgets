"""Local NWB video player widget."""

import pathlib
from pathlib import Path

import anywidget
import traitlets
from pynwb import NWBFile

from nwb_video_widgets._utils import (
    discover_video_series,
    get_video_info,
    get_video_timestamps,
    start_video_server,
)


class NWBLocalVideoPlayer(anywidget.AnyWidget):
    """Display local videos from an NWB file with synchronized playback.

    This widget discovers ImageSeries with external_file references in the NWB
    file and resolves their paths relative to the NWB file location. An interactive
    settings panel allows users to select which videos to display and choose
    between Row, Column, or Grid layouts.

    Parameters
    ----------
    nwbfile : pynwb.NWBFile
        NWB file containing video ImageSeries in acquisition. Must have been
        loaded from disk (i.e., nwbfile.read_io must not be None).

    Example
    -------
    >>> from pynwb import NWBHDF5IO
    >>> with NWBHDF5IO("experiment.nwb", "r") as io:
    ...     nwbfile = io.read()
    ...     widget = NWBLocalVideoPlayer(nwbfile)
    ...     display(widget)

    Raises
    ------
    ValueError
        If the NWB file was not loaded from disk (read_io is None)
    """

    video_urls = traitlets.Dict({}).tag(sync=True)
    video_timestamps = traitlets.Dict({}).tag(sync=True)
    available_videos = traitlets.Dict({}).tag(sync=True)
    selected_videos = traitlets.List([]).tag(sync=True)
    layout_mode = traitlets.Unicode("row").tag(sync=True)
    settings_open = traitlets.Bool(False).tag(sync=True)

    _esm = pathlib.Path(__file__).parent / "video_widget.js"
    _css = pathlib.Path(__file__).parent / "video_widget.css"

    def __init__(
        self,
        nwbfile: NWBFile,
        **kwargs,
    ):
        video_urls = self.get_video_urls_from_local(nwbfile)
        video_timestamps = get_video_timestamps(nwbfile)
        available_videos = get_video_info(nwbfile)

        # Start with no videos selected to avoid initial buffering
        super().__init__(
            video_urls=video_urls,
            video_timestamps=video_timestamps,
            available_videos=available_videos,
            selected_videos=[],
            layout_mode="grid",
            settings_open=True,
            **kwargs,
        )

    @staticmethod
    def get_video_urls_from_local(nwbfile: NWBFile) -> dict[str, str]:
        """Extract video file URLs from a local NWB file.

        Resolves external_file paths relative to the NWB file location and
        serves them via a local HTTP server for browser playback.

        Parameters
        ----------
        nwbfile : pynwb.NWBFile
            NWB file containing video ImageSeries in acquisition

        Returns
        -------
        dict[str, str]
            Mapping of video names to HTTP URLs served locally

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
