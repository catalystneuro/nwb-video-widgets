"""Interactive Jupyter widgets for NWB video and pose visualization."""

from nwb_video_widgets.dandi_pose_widget import NWBDANDIPoseEstimationWidget
from nwb_video_widgets.dandi_video_widget import NWBDANDIVideoPlayer
from nwb_video_widgets.local_pose_widget import NWBLocalPoseEstimationWidget
from nwb_video_widgets.local_video_widget import NWBLocalVideoPlayer
from nwb_video_widgets.video_widget import NWBFileVideoPlayer

__all__ = [
    "NWBLocalVideoPlayer",
    "NWBDANDIVideoPlayer",
    "NWBFileVideoPlayer",
    "NWBLocalPoseEstimationWidget",
    "NWBDANDIPoseEstimationWidget",
]
__version__ = "0.1.0"
