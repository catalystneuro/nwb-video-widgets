# nwb-video-widgets

[![PyPI version](https://badge.fury.io/py/nwb-video-widgets.svg)](https://badge.fury.io/py/nwb-video-widgets)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Interactive Jupyter widgets for NWB video and pose estimation visualization. Built with [anywidget](https://anywidget.dev/) for compatibility across JupyterLab, Jupyter Notebook, VS Code, and Google Colab.

## Table of Contents

- [Installation](#installation)
- [Widgets](#widgets)
  - [NWBPoseEstimationWidget](#nwbposeestimationwidget)
  - [NWBFileVideoPlayer](#nwbfilevideoplayer)
- [Development](#development)
- [License](#license)

## Installation

```bash
pip install nwb-video-widgets
```

For DANDI integration (required for `NWBFileVideoPlayer` with DANDI assets):

```bash
pip install nwb-video-widgets[dandi]
```

## Widgets

### NWBPoseEstimationWidget

Overlays DeepLabCut pose estimation keypoints on streaming video with support for multiple cameras.

![Pose Estimation Widget Demo](assets/pose_estimation_preprocessed.gif)

**Features:**

- Multi-camera support with instant camera switching
- Keypoint visibility toggles (All/None/individual)
- Label display toggle
- Session time display (NWB timestamps)
- Custom keypoint colors via colormap or explicit hex values

**Basic Usage:**

```python
from nwb_video_widgets import NWBPoseEstimationWidget

widget = NWBPoseEstimationWidget(
    nwbfile=nwbfile_processed,
    video_urls=video_s3_urls,
    camera_to_video_key={
        "LeftCamera": "VideoLeftCamera",
        "BodyCamera": "VideoBodyCamera",
        "RightCamera": "VideoRightCamera",
    },
    keypoint_colors="tab10",  # or {"LeftPaw": "#FF0000", ...}
)
widget
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `nwbfile` | `NWBFile` | NWB file containing pose estimation data |
| `video_urls` | `dict[str, str]` | Mapping of video keys to URLs |
| `camera_to_video_key` | `dict[str, str]` | Maps camera names to video keys |
| `keypoint_colors` | `str` or `dict` | Matplotlib colormap name or explicit color mapping |

---

### NWBFileVideoPlayer

Multi-camera synchronized video player with configurable grid layout.

![Video Widget Demo](assets/video_widget_preprocessed.gif)

**Features:**

- Configurable grid layout for multiple cameras
- Synchronized playback across all videos
- Session time display with NWB timestamps
- Automatic DANDI S3 URL resolution

**Basic Usage:**

```python
from nwb_video_widgets import NWBFileVideoPlayer

widget = NWBFileVideoPlayer(
    nwbfile_raw=nwbfile_raw,
    dandi_asset=dandi_asset,
    grid_layout=[
        ["VideoLeftCamera", "VideoRightCamera"],
        ["VideoBodyCamera"],
    ],
)
widget
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `nwbfile_raw` | `NWBFile` | NWB file containing video references |
| `dandi_asset` | `DandiAsset` | DANDI asset for S3 URL resolution |
| `grid_layout` | `list[list[str]]` | 2D layout of video keys |

## Development

```bash
git clone https://github.com/catalystneuro/nwb-video-widgets.git
cd nwb-video-widgets
uv pip install -e ".[dandi]"
uv sync --group dev
```

Run tests:

```bash
pytest
```

## License

MIT
