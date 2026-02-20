"""Shared utilities for NWB video widgets."""

import socket
import struct
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from pynwb import NWBFile
from pynwb.image import ImageSeries

# Global registry for video file servers
_video_servers: dict[str, tuple[HTTPServer, int]] = {}

# Codecs natively supported by all major browsers via HTML5 <video>
BROWSER_COMPATIBLE_CODECS = {"h264", "H264", "avc1", "vp8", "vp9", "VP8", "VP9", "vp09", "av01", "AV01"}

_HEADER_READ_SIZE = 32 * 1024  # 32 KB is enough for codec detection


def _detect_avi_codec(data: bytes) -> str | None:
    """Extract the video codec FourCC from AVI (RIFF) header bytes.

    Walks the RIFF chunk structure to find the ``strh`` chunk with
    ``fccType == b'vids'`` and returns the ``fccHandler`` field.
    """
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"AVI ":
        return None

    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        if len(data) < pos + 8:
            break
        chunk_size = struct.unpack_from("<I", data, pos + 4)[0]

        if chunk_id == b"LIST":
            pos += 12  # enter LIST, skip list type
            continue

        if chunk_id == b"strh" and chunk_size >= 8:
            fcc_type = data[pos + 8 : pos + 12]
            fcc_handler = data[pos + 12 : pos + 16]
            if fcc_type == b"vids":
                codec = fcc_handler.decode("ascii", errors="replace").strip("\x00")
                return codec if codec else None

        pos += 8 + chunk_size + (chunk_size % 2)

    return None


def _find_mp4_box(data: bytes, start: int, end: int, target: bytes) -> tuple[int, int] | None:
    """Find an ISO BMFF box by type within a byte range.

    Returns ``(payload_start, payload_end)`` or ``None``.
    """
    pos = start
    while pos + 8 <= end:
        box_size = struct.unpack_from(">I", data, pos)[0]
        box_type = data[pos + 4 : pos + 8]

        if box_size == 1 and pos + 16 <= end:
            box_size = struct.unpack_from(">Q", data, pos + 8)[0]
            payload_start = pos + 16
        elif box_size < 8:
            break
        else:
            payload_start = pos + 8

        if box_type == target:
            return payload_start, min(pos + box_size, end)

        pos += box_size

    return None


def _detect_mp4_codec(data: bytes) -> str | None:
    """Extract the video codec FourCC from MP4/MOV header bytes.

    Navigates ``moov > trak > mdia > minf > stbl > stsd`` and reads the
    codec identifier from the first sample entry.  If the ``moov`` box
    is not found at a top-level box boundary (e.g. when parsing the tail
    of a file), falls back to scanning for the ``moov`` signature.
    """
    end = len(data)
    inner_path = [b"trak", b"mdia", b"minf", b"stbl", b"stsd"]

    # Try structured traversal first
    moov = _find_mp4_box(data, 0, end, b"moov")

    # Fallback: scan for moov signature (useful for tail-of-file reads)
    if moov is None:
        search_pos = 0
        while True:
            found = data.find(b"moov", search_pos)
            if found == -1 or found < 4:
                return None
            box_size = struct.unpack_from(">I", data, found - 4)[0]
            if 16 < box_size <= end - (found - 4):
                moov = (found + 4, found - 4 + box_size)
                break
            search_pos = found + 4

    start, end = moov
    for box_type in inner_path:
        result = _find_mp4_box(data, start, end, box_type)
        if result is None:
            return None
        start, end = result

    # stsd FullBox: version(1) + flags(3) + entry_count(4) = 8 bytes
    # then SampleEntry: size(4) + codec_fourcc(4)
    entry_offset = start + 8
    if entry_offset + 8 > end:
        return None

    codec_fourcc = data[entry_offset + 4 : entry_offset + 8]
    return codec_fourcc.decode("ascii", errors="replace").strip("\x00") or None


def detect_video_codec(video_path: Path) -> str | None:
    """Detect the video codec of a file by reading its header bytes.

    Supports AVI (RIFF) and MP4/MOV (ISO BMFF) containers. Returns the
    codec identifier string (e.g. ``"avc1"``, ``"MJPG"``, ``"mp4v"``)
    or ``None`` if the format is not recognized.

    For MP4 files where the ``moov`` box is at the end of the file (common
    when not encoded with ``faststart``), the tail of the file is also read.

    Parameters
    ----------
    video_path : Path
        Path to a video file.

    Returns
    -------
    str or None
        Codec identifier, or None if unrecognized.
    """
    file_size = video_path.stat().st_size
    with open(video_path, "rb") as f:
        data = f.read(_HEADER_READ_SIZE)

    if len(data) < 12:
        return None

    # AVI: RIFF....AVI
    if data[:4] == b"RIFF" and data[8:12] == b"AVI ":
        return _detect_avi_codec(data)

    # MP4/MOV: ftyp box at start
    if data[4:8] == b"ftyp" or data[4:8] == b"moov":
        codec = _detect_mp4_codec(data)
        if codec is not None:
            return codec

        # moov may be at the end of the file (no faststart)
        if file_size > _HEADER_READ_SIZE:
            tail_size = min(file_size, _HEADER_READ_SIZE * 8)  # up to 256KB
            with open(video_path, "rb") as f:
                f.seek(file_size - tail_size)
                tail_data = f.read(tail_size)
            return _detect_mp4_codec(tail_data)

    return None


def validate_video_codec(video_path: Path) -> None:
    """Raise ``ValueError`` if the video uses a non-browser-compatible codec.

    Parameters
    ----------
    video_path : Path
        Path to a video file.

    Raises
    ------
    ValueError
        If the detected codec is not in ``BROWSER_COMPATIBLE_CODECS``.
    """
    codec = detect_video_codec(video_path)
    if codec is None:
        return  # unrecognized format, don't block

    if codec not in BROWSER_COMPATIBLE_CODECS:
        stem = video_path.stem
        raise ValueError(
            f"Video '{video_path.name}' uses the '{codec}' codec which cannot be played in the browser. "
            f"Re-encode with: ffmpeg -i {video_path.name} -c:v libx264 -crf 18 -pix_fmt yuv420p {stem}_h264.mp4"
        )


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
