"""Shared utilities for NWB video widgets."""

from __future__ import annotations

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

    Uses indexed access (timestamps[0], timestamps[-1]) instead of loading
    the full timestamps array, which is important for DANDI streaming where
    each slice triggers HTTP range requests.

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
    """
    video_series = discover_video_series(nwbfile)
    info = {}

    for name, series in video_series.items():
        if series.timestamps is not None and len(series.timestamps) > 0:
            start = float(series.timestamps[0])
            end = float(series.timestamps[-1])
        elif series.starting_time is not None:
            start = float(series.starting_time)
            end = start
        else:
            start = 0.0
            end = 0.0

        info[name] = {
            "start": start,
            "end": end,
        }

    return info


def _resolve_video_from_dandi_hdf5(
    nwb_s3_url: str,
    asset_path: str,
    dandiset_id: str,
    version_id: str,
    dandi_api_url: str,
    dandi_api_key: str = "",
) -> tuple[dict[str, str], dict[str, dict]]:
    """Resolve video URLs and timing from a DANDI NWB file using targeted h5py reads.

    This is the fallback path when LINDI is unavailable. It opens the HDF5 file
    via remfile (HTTP range requests) and reads only the specific datasets needed,
    skipping pynwb's expensive namespace loading and object graph construction.

    Parameters
    ----------
    nwb_s3_url : str
        Pre-signed S3 URL for the NWB file.
    asset_path : str
        DANDI asset path (e.g. "sub-X/sub-X_ses-Y.nwb"), used to resolve
        relative video paths within the dandiset.
    dandiset_id : str
        DANDI dandiset ID (e.g. "000409").
    version_id : str
        DANDI version (e.g. "draft").
    dandi_api_url : str
        DANDI API base URL (e.g. "https://api.dandiarchive.org/api").
    dandi_api_key : str
        Optional DANDI API key for embargoed dandisets.

    Returns
    -------
    tuple[dict[str, str], dict[str, dict]]
        (video_urls, video_timing) where video_urls maps series names to S3 URLs
        and video_timing maps series names to {start, end} dicts.
    """
    from posixpath import dirname as posix_dirname
    from posixpath import join as posix_join
    from urllib.parse import quote

    import h5py
    import remfile
    import requests

    rf = remfile.File(nwb_s3_url)
    h5f = h5py.File(rf, "r")

    nwb_parent = posix_dirname(asset_path)
    headers = {"Authorization": f"token {dandi_api_key}"} if dandi_api_key else {}

    video_urls = {}
    video_timing = {}

    try:
        for name in h5f["acquisition"]:
            obj = h5f["acquisition"][name]
            if obj.attrs.get("neurodata_type") != "ImageSeries":
                continue
            if "external_file" not in obj:
                continue

            raw_path = obj["external_file"][0]
            ext_file = raw_path.decode("utf-8") if isinstance(raw_path, bytes) else raw_path
            clean_relative = ext_file.lstrip("./")
            full_path = posix_join(nwb_parent, clean_relative) if nwb_parent else clean_relative

            # Read timing
            if "timestamps" in obj and len(obj["timestamps"]) > 0:
                start = float(obj["timestamps"][0])
                end = float(obj["timestamps"][-1])
            elif "starting_time" in obj:
                start = float(obj["starting_time"][()])
                end = start
            else:
                start, end = 0.0, 0.0

            # Resolve DANDI URL via REST API.
            # URL-encode the path (e.g. "+" in "ecephys+image" must become "%2B").
            encoded_path = quote(full_path, safe="/")
            search_url = f"{dandi_api_url}/dandisets/{dandiset_id}/versions/{version_id}/assets/?path={encoded_path}"
            resp = requests.get(search_url, headers=headers)
            if resp.status_code != 200:
                continue
            results = resp.json().get("results", [])
            if not results:
                continue

            video_asset_id = results[0]["asset_id"]
            download_url = f"{dandi_api_url}/assets/{video_asset_id}/download/"

            # Follow redirect to get S3 URL
            redirect_resp = requests.head(download_url, headers=headers, allow_redirects=True)
            s3_url = redirect_resp.url if redirect_resp.url else download_url

            video_urls[name] = s3_url
            video_timing[name] = {"start": start, "end": end}
    finally:
        h5f.close()

    return video_urls, video_timing


def get_dandi_video_info(asset=None, url=None, token="") -> dict[str, dict]:
    """Return video URLs and session-time ranges for a DANDI NWB asset.

    Accepts either a ``RemoteAsset`` object or a DANDI URL string. Opens the
    NWB file via HTTP range requests (no pynwb), finds all ImageSeries with
    external video files, reads their timing, and resolves the video paths to
    S3 URLs via the DANDI REST API.

    Parameters
    ----------
    asset : dandi.dandiapi.RemoteAsset, optional
        DANDI asset object for the NWB file containing video ImageSeries.
    url : str, optional
        A DANDI API URL pointing to the NWB asset. Supported formats:
        ``https://api.dandiarchive.org/api/dandisets/{id}/versions/{version}/assets/?path={path}``
        or ``https://api.dandiarchive.org/api/assets/{uuid}/download/``.
    token : str, optional
        DANDI API token for embargoed dandisets (only used with ``url``).

    Returns
    -------
    dict[str, dict]
        Mapping of video series names to dicts with keys:
        - url: str, S3 URL for the video file
        - start: float, session start time in seconds
        - end: float, session end time in seconds

    Example
    -------
    >>> from nwb_video_widgets import get_dandi_video_info
    >>> info = get_dandi_video_info(url="https://api.dandiarchive.org/api/dandisets/000409/versions/draft/assets/?path=sub-NYU-46/...nwb")
    >>> info["VideoBodyCamera"]
    {'url': 'https://dandiarchive.s3.amazonaws.com/...', 'start': 6.57, 'end': 4030.42}
    """
    if asset is None and url is None:
        raise ValueError("Either asset or url must be provided")

    if asset is None:
        from dandi.dandiarchive import parse_dandi_url

        parsed = parse_dandi_url(url)
        client = parsed.get_client()
        if token:
            client.dandi_authenticate(token)
        assets = list(parsed.get_assets(client))
        if not assets:
            raise ValueError(f"No asset found at {url}")
        asset = assets[0]

    auth_header = asset.client.session.headers.get("Authorization", "")
    api_key = auth_header[6:] if auth_header.startswith("token ") else ""

    s3_url = asset.get_content_url(follow_redirects=1, strip_query=False)
    video_urls, video_timing = _resolve_video_from_dandi_hdf5(
        nwb_s3_url=s3_url,
        asset_path=asset.path,
        dandiset_id=asset.dandiset_id,
        version_id=asset.version_id,
        dandi_api_url=asset.client.api_url,
        dandi_api_key=api_key,
    )
    return {name: {"url": video_urls[name], **video_timing[name]} for name in video_urls}


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

    Searches all objects in the file regardless of where they are stored,
    so PoseEstimation data in any processing module (e.g. 'pose_estimation',
    'behavior') is found.

    Parameters
    ----------
    nwbfile : NWBFile
        NWB file to search for pose estimation data

    Returns
    -------
    dict
        Mapping of camera names to PoseEstimation objects.
    """
    cameras = {}
    for obj in nwbfile.objects.values():
        if obj.neurodata_type == "PoseEstimation":
            assert obj.name not in cameras, f"Duplicate PoseEstimation name found: {obj.name}"
            cameras[obj.name] = obj
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
        - keypoints: list[str], names of keypoints
    """
    cameras = discover_pose_estimation_cameras(nwbfile)
    info = {}

    for camera_name, pose_estimation in cameras.items():
        # Get keypoint names (remove PoseEstimationSeries suffix)
        keypoint_names = [
            name.replace("PoseEstimationSeries", "") for name in pose_estimation.pose_estimation_series.keys()
        ]

        # Get start/end times from the first pose estimation series using indexed
        # access to avoid loading the full timestamps array into memory. This is
        # important for DANDI streaming where each slice triggers HTTP range requests.
        first_series = next(iter(pose_estimation.pose_estimation_series.values()), None)
        if first_series is not None and first_series.timestamps is not None:
            start = float(first_series.timestamps[0])
            end = float(first_series.timestamps[-1])
        else:
            start = 0.0
            end = 0.0

        info[camera_name] = {
            "start": start,
            "end": end,
            "keypoints": keypoint_names,
        }

    return info
