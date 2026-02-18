"""Shared utilities for NWB video widgets."""

import hashlib
import socket
import tempfile
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import av
from pynwb import NWBFile
from pynwb.image import ImageSeries

# Global registry for video file servers
_video_servers: dict[str, tuple[HTTPServer, int]] = {}

# Codecs natively supported by all major browsers
_BROWSER_COMPATIBLE_CODECS = {"h264", "vp8", "vp9", "av1"}


def get_video_codec(video_path: Path) -> str:
    """Return the codec name of the first video stream in a video file.

    Parameters
    ----------
    video_path : Path
        Path to the video file

    Returns
    -------
    str
        Codec name (e.g. ``"h264"``, ``"mpeg4"``, ``"vp9"``)
    """
    with av.open(str(video_path)) as container:
        return container.streams.video[0].codec_context.name


def _transcode_to_h264(source: str | Path, out_path: Path) -> None:
    """Transcode a video to H.264/MP4 using PyAV.

    Parameters
    ----------
    source : str or Path
        Path or URL of the input video
    out_path : Path
        Destination path for the H.264-encoded output
    """
    with av.open(str(source)) as inp:
        with av.open(str(out_path), "w", format="mp4") as out:
            in_stream = inp.streams.video[0]
            out_stream = out.add_stream("libx264", rate=in_stream.average_rate)
            out_stream.width = in_stream.width
            out_stream.height = in_stream.height
            out_stream.pix_fmt = "yuv420p"
            for packet in inp.demux(in_stream):
                for frame in packet.decode():
                    frame.pts = None
                    for out_packet in out_stream.encode(frame):
                        out.mux(out_packet)
            for out_packet in out_stream.encode():
                out.mux(out_packet)


def ensure_browser_compatible_video(video_path: Path) -> Path:
    """Return a path to a browser-compatible version of a video file.

    If the video is already encoded with a browser-compatible codec (H.264,
    VP8, VP9, or AV1) the original path is returned unchanged. Otherwise the
    video is transcoded to H.264 using PyAV and cached in a temporary
    directory so subsequent calls are instant.

    Parameters
    ----------
    video_path : Path
        Path to the original video file

    Returns
    -------
    Path
        Path to a browser-compatible video file (may be the same as input)
    """
    codec = get_video_codec(video_path)
    if codec in _BROWSER_COMPATIBLE_CODECS:
        return video_path

    # Build a stable cache path based on the resolved absolute path
    hash_val = hashlib.md5(str(video_path.resolve()).encode()).hexdigest()[:8]
    cache_dir = Path(tempfile.gettempdir()) / "nwb_video_widgets"
    cache_dir.mkdir(exist_ok=True)
    out_path = cache_dir / f"{video_path.stem}_{hash_val}_h264.mp4"

    if not out_path.exists():
        _transcode_to_h264(video_path, out_path)

    return out_path


def discover_video_series(nwbfile: NWBFile) -> dict[str, ImageSeries]:
    """Discover all ImageSeries with external video files in an NWB file.

    Parameters
    ----------
    nwbfile : NWBFile
        NWB file to search for video series

    Returns
    -------
    dict[str, ImageSeries]
        Mapping of series names to ImageSeries objects that have external_file
    """
    video_series = {}
    for name, obj in nwbfile.acquisition.items():
        if isinstance(obj, ImageSeries) and obj.external_file is not None:
            video_series[name] = obj
    return video_series


def get_video_timestamps(nwbfile: NWBFile) -> dict[str, list[float]]:
    """Extract video timestamps from all ImageSeries in an NWB file.

    Parameters
    ----------
    nwbfile : NWBFile
        NWB file containing video ImageSeries in acquisition

    Returns
    -------
    dict[str, list[float]]
        Mapping of video names to timestamp arrays
    """
    video_series = discover_video_series(nwbfile)
    timestamps = {}

    for name, series in video_series.items():
        if series.timestamps is not None:
            timestamps[name] = [float(t) for t in series.timestamps[:]]
        elif series.starting_time is not None:
            timestamps[name] = [float(series.starting_time)]
        else:
            timestamps[name] = [0.0]

    return timestamps


def get_video_info(nwbfile: NWBFile) -> dict[str, dict]:
    """Extract video time range information from all ImageSeries in an NWB file.

    Parameters
    ----------
    nwbfile : NWBFile
        NWB file containing video ImageSeries in acquisition

    Returns
    -------
    dict[str, dict]
        Mapping of video names to info dictionaries with keys:
        - start: float, start time in seconds
        - end: float, end time in seconds
        - frames: int, number of frames
    """
    video_series = discover_video_series(nwbfile)
    info = {}

    for name, series in video_series.items():
        if series.timestamps is not None:
            timestamps = series.timestamps[:]
            start = float(timestamps[0])
            end = float(timestamps[-1])
            frames = len(timestamps)
        elif series.starting_time is not None:
            start = float(series.starting_time)
            # Without timestamps, we can't determine end time accurately
            # Use starting_time as both start and end
            end = start
            frames = 1
        else:
            start = 0.0
            end = 0.0
            frames = 1

        info[name] = {
            "start": start,
            "end": end,
            "frames": frames,
        }

    return info


class _RangeRequestHandler(SimpleHTTPRequestHandler):
    """HTTP request handler with CORS headers and Range request support for video streaming."""

    def send_head(self):
        """Handle HEAD requests and Range requests for partial content."""
        path = self.translate_path(self.path)

        if not Path(path).is_file():
            return super().send_head()

        file_size = Path(path).stat().st_size
        range_header = self.headers.get("Range")

        if range_header:
            # Parse Range header (e.g., "bytes=0-1023")
            try:
                range_spec = range_header.replace("bytes=", "")
                start_str, end_str = range_spec.split("-")
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else file_size - 1
                end = min(end, file_size - 1)
                content_length = end - start + 1

                f = open(path, "rb")
                f.seek(start)

                self.send_response(206)  # Partial Content
                self.send_header("Content-Type", self.guess_type(path))
                self.send_header("Content-Length", str(content_length))
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS, HEAD")
                self.send_header("Access-Control-Allow-Headers", "Range")
                self.send_header("Access-Control-Expose-Headers", "Content-Range, Content-Length")
                self.end_headers()
                return f
            except (ValueError, IOError):
                pass

        # No Range header or invalid range - serve full file
        return super().send_head()

    def end_headers(self):
        """Add CORS headers to all responses."""
        # Only add if not already added (for non-range requests)
        if not self._headers_buffer or b"Access-Control-Allow-Origin" not in b"".join(self._headers_buffer):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS, HEAD")
            self.send_header("Access-Control-Allow-Headers", "Range")
            self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "Range")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def log_message(self, format, *args):
        """Suppress logging to avoid cluttering notebook output."""
        pass

    def handle(self):
        """Handle requests, suppressing connection reset errors."""
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            # Browser closed connection early - this is normal during video seeking
            pass


def _find_free_port() -> int:
    """Find a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def start_video_server(directory: Path) -> int:
    """Start an HTTP server to serve video files from a directory.

    If a server is already running for this directory, returns its port.

    Parameters
    ----------
    directory : Path
        Directory containing video files to serve

    Returns
    -------
    int
        Port number the server is listening on
    """
    dir_key = str(directory.resolve())

    # Return existing server port if already running
    if dir_key in _video_servers:
        _, port = _video_servers[dir_key]
        return port

    port = _find_free_port()
    handler = partial(_RangeRequestHandler, directory=str(directory))
    server = HTTPServer(("127.0.0.1", port), handler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    _video_servers[dir_key] = (server, port)
    return port


def discover_pose_estimation_cameras(nwbfile: NWBFile) -> dict:
    """Discover all PoseEstimation containers in an NWB file.

    Parameters
    ----------
    nwbfile : NWBFile
        NWB file to search for pose estimation data

    Returns
    -------
    dict
        Mapping of camera names to PoseEstimation objects from
        processing['pose_estimation'].
    """
    if "pose_estimation" not in nwbfile.processing:
        return {}

    pose_module = nwbfile.processing["pose_estimation"]

    # Get only PoseEstimation objects (not Skeletons or other types)
    cameras = {}
    for name, obj in pose_module.data_interfaces.items():
        if type(obj).__name__ == "PoseEstimation":
            cameras[name] = obj

    return cameras


def get_camera_to_video_mapping(nwbfile: NWBFile) -> dict[str, str]:
    """Auto-map pose estimation camera names to video series names.

    Uses the naming convention: camera name prefixed with "Video"
    - 'LeftCamera' -> 'VideoLeftCamera'
    - 'BodyCamera' -> 'VideoBodyCamera'

    Only returns mappings where both the camera and corresponding video exist.

    Parameters
    ----------
    nwbfile : NWBFile
        NWB file containing pose estimation and video data

    Returns
    -------
    dict[str, str]
        Mapping from camera names to video series names
    """
    cameras = discover_pose_estimation_cameras(nwbfile)
    video_series = discover_video_series(nwbfile)

    mapping = {}
    for camera_name in cameras:
        video_name = f"Video{camera_name}"
        if video_name in video_series:
            mapping[camera_name] = video_name

    return mapping


def get_pose_estimation_info(nwbfile: NWBFile) -> dict[str, dict]:
    """Extract pose estimation info for all cameras in an NWB file.

    Parameters
    ----------
    nwbfile : NWBFile
        NWB file containing pose estimation in processing['pose_estimation']

    Returns
    -------
    dict[str, dict]
        Mapping of camera names to info dictionaries with keys:
        - start: float, start time in seconds
        - end: float, end time in seconds
        - frames: int, number of frames
        - keypoints: list[str], names of keypoints
    """
    cameras = discover_pose_estimation_cameras(nwbfile)
    info = {}

    for camera_name, pose_estimation in cameras.items():
        # Get keypoint names (remove PoseEstimationSeries suffix)
        keypoint_names = [
            name.replace("PoseEstimationSeries", "") for name in pose_estimation.pose_estimation_series.keys()
        ]

        # Get timestamps from the first pose estimation series
        first_series = next(iter(pose_estimation.pose_estimation_series.values()), None)
        if first_series is not None and first_series.timestamps is not None:
            timestamps = first_series.timestamps[:]
            start = float(timestamps[0])
            end = float(timestamps[-1])
            frames = len(timestamps)
        else:
            start = 0.0
            end = 0.0
            frames = 0

        info[camera_name] = {
            "start": start,
            "end": end,
            "frames": frames,
            "keypoints": keypoint_names,
        }

    return info
