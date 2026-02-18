"""Synthetic video generation for testing."""

import subprocess
from pathlib import Path

import numpy as np


def create_synthetic_video(
    output_path: Path,
    num_frames: int = 30,
    width: int = 160,
    height: int = 120,
    fps: float = 30.0,
) -> Path:
    """Create a synthetic H.264-encoded video file for testing.

    Writes frames using mp4v, then re-encodes to H.264 via ffmpeg.
    ffmpeg is pre-installed on GitHub Actions (Ubuntu and Windows runners).

    Parameters
    ----------
    output_path : Path
        Where to save the video
    num_frames : int
        Number of frames to generate
    width, height : int
        Video dimensions
    fps : float
        Frames per second

    Returns
    -------
    Path
        Path to created video file
    """
    import cv2

    output_path = Path(output_path)
    tmp_path = output_path.with_suffix(".tmp.mp4")

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(tmp_path), fourcc, fps, (width, height))

    for frame_index in range(num_frames):
        # Create gradient background with frame number indicator
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :, 0] = int(255 * frame_index / num_frames)  # Blue gradient
        frame[:, :, 1] = 128  # Constant green
        frame[:, :, 2] = int(255 * (1 - frame_index / num_frames))  # Red gradient

        # Add moving circle for visual tracking
        cx = int(width * (0.2 + 0.6 * frame_index / num_frames))
        cy = height // 2
        cv2.circle(frame, (cx, cy), 10, (255, 255, 255), -1)

        out.write(frame)

    out.release()

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(tmp_path),
            "-vcodec",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )

    tmp_path.unlink()

    return output_path
