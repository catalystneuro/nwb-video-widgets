"""Synthetic NWB file generation for testing."""

from pathlib import Path

import numpy as np
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
