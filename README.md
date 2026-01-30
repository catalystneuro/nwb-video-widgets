# nwb-video-widgets

Interactive Jupyter widgets for NWB video and pose estimation visualization.

Built with [anywidget](https://anywidget.dev/) for compatibility across JupyterLab, Jupyter Notebook, VS Code, and Google Colab.

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

**Features:**
- Multi-camera support with instant camera switching
- Keypoint visibility toggles (All/None/individual)
- Label display toggle
- Session time display (NWB timestamps)
- Custom keypoint colors via colormap or explicit hex values

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

### NWBFileVideoPlayer

Multi-camera synchronized video player with configurable grid layout.

**Features:**
- Configurable grid layout
- Synchronized playback across all videos
- Session time display
- DANDI S3 URL resolution

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

## Requirements

- Python >= 3.10
- anywidget >= 0.9.0
- pynwb
- numpy
- matplotlib

Optional:
- dandi >= 0.60.0 (for DANDI integration)

## Development

```bash
git clone https://github.com/catalystneuro/nwb-video-widgets.git
cd nwb-video-widgets
uv pip install -e ".[dandi]"
uv sync --group dev
```

## License

MIT
