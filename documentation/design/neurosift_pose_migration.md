# Neurosift Pattern Migration: Pose Estimation Data

## Context

The video widget already follows the Neurosift pattern: Python injects seed traitlets, JavaScript
reads video metadata directly from LINDI via byte-range requests (see
`neurosift_pattern_migration.md`). The pose estimation widget adopted the same pattern for
video resolution, but pose coordinate data still flows through the old path: Python loads all
coordinates and timestamps from HDF5, converts numpy arrays to Python lists, JSON-serializes the
full payload, and sends it to the browser through the Jupyter websocket.

For large datasets this is the dominant bottleneck. A recording with 143,948 frames and 14
keypoints produces ~50 MB of JSON text that must be serialized in Python, transferred over the
websocket, and parsed in the browser. The binary representation of the same data is ~2.2 MB per
keypoint (~32 MB total), and JS can read it directly from S3 without involving Python at all.

This document describes moving pose coordinate loading to JavaScript, following the same
LINDI-first pattern used for video metadata.

## Current Architecture (DANDI pose widget)

```
User selects camera
    |
    v
Python: _on_camera_selected()
    |-- series.data[:] for each keypoint over HTTP (remfile)
    |-- numpy -> Python list conversion (NaN -> None)
    |-- series.get_timestamps()[:].tolist()
    |
    v
Traitlets: JSON serialize ~50 MB, send via websocket
    |
    v
JavaScript: receives all_camera_data, renders keypoints
```

Python opens the NWB file at init time via remfile/h5py/pynwb just for pose data. This is the
last remaining reason the DANDI pose widget loads an NWB file in Python.

## Proposed Architecture

```
Widget init:
    Python: extract seeds from asset (instant, no NWB loading)
    Python: send keypoint metadata (colors, labels) via traitlets (~tiny)

Camera selection:
    JavaScript: read LINDI refs for selected camera's PoseEstimationSeries
    JavaScript: fetch coordinate arrays via byte-range requests (binary float64)
    JavaScript: fetch timestamps array via byte-range requests
    JavaScript: store in memory, render keypoints
```

### What moves to JavaScript

1. **Pose series discovery.** JS scans the LINDI refs for PoseEstimationSeries under
   `processing/*/data_interfaces/*/pose_estimation_series/*`. It reads `.zattrs` to identify
   series by `neurodata_type` and groups them by camera (the parent PoseEstimation container).

2. **Coordinate array reading.** Each keypoint's data is a `(n_frames, 2)` float64 dataset.
   JS reads the `.zarray` metadata (shape, chunks, dtype, compressor) and fetches the raw bytes
   via HTTP Range requests. For uncompressed, single-chunk data this is one fetch per keypoint.
   For multi-chunk datasets, JS fetches each chunk and concatenates the results.

3. **Timestamp array reading.** One `(n_frames,)` float64 array per camera (shared across
   keypoints). Same byte-range reading pattern. The existing `readLindiTimestamps` function
   already handles start/end reads; this extends it to read the full array.

4. **NaN handling.** JS checks for NaN directly in the Float64Array. This replaces the
   Python-side `nan_mask` + loop pattern.

### What stays in Python

1. **Keypoint metadata (colors, labels).** Computed using matplotlib colormaps and user-provided
   custom colors. This is a tiny dict (~1 KB) that stays in traitlets. Python sends it once per
   camera selection.

2. **Container discovery metadata.** Python still needs to know which cameras exist and which
   keypoints belong to each camera so it can compute colors and build the camera selection panel.
   Two options:

   - (a) Python does a lightweight discovery pass (read container names and keypoint names from
     LINDI or h5py, no coordinate data) and sends the camera list + color assignments. JS uses
     these paths to read coordinate data on camera selection.
   - (b) JS discovers everything from LINDI and sends camera/keypoint names back to Python via
     a traitlet, then Python computes colors and sends metadata back.

   Option (a) is simpler because Python already has the pynwb objects during init. But the goal
   is to eliminate NWB loading in Python entirely for the DANDI widget. Option (b) achieves that
   at the cost of a round-trip: JS discovers, syncs names to Python, Python computes colors,
   syncs back. This is the same pattern used for video URLs (JS resolves, Python observes).

3. **Local file fallback.** The local pose widget (`NWBLocalPoseEstimationWidget`) keeps the
   current Python-based loading. LINDI is only available for DANDI-hosted files.

## LINDI Refs Structure for Pose Data

A PoseEstimation container in LINDI looks like:

```
processing/{module}/data_interfaces/{container}/.zattrs
    -> neurodata_type: "PoseEstimation"
    -> pose_estimation_series: ["NoseTip", "LeftEar", ...]

processing/{module}/data_interfaces/{container}/pose_estimation_series/{name}/data/.zarray
    -> shape: [143948, 2], dtype: "<f8", chunks: [143948, 2]

processing/{module}/data_interfaces/{container}/pose_estimation_series/{name}/data/0
    -> [url, byteOffset, byteLength]  (range reference into S3)
    OR base64 string (inline for small datasets)

processing/{module}/data_interfaces/{container}/pose_estimation_series/{name}/timestamps/.zarray
    -> shape: [143948], dtype: "<f8"

processing/{module}/data_interfaces/{container}/pose_estimation_series/{name}/timestamps/0
    -> [url, byteOffset, byteLength]
```

### Reading 2D coordinate arrays

The existing LINDI readers handle 1D arrays (timestamps) and scalars. Coordinate data is 2D
`(n_frames, 2)`. The reading logic is similar but needs to account for:

- **Row-major layout.** Float64 values are stored as `[x0, y0, x1, y1, x2, y2, ...]` in
  row-major (C) order. JS reads the flat byte buffer and interprets pairs of consecutive
  float64 values as `(x, y)` coordinates.
- **Multi-chunk 2D datasets.** If the data is chunked along the frame axis (e.g.,
  `chunks: [10000, 2]`), JS reads each chunk separately and concatenates. The chunk key in
  LINDI is `"0.0"`, `"1.0"`, etc. (dot-separated multi-dimensional chunk indices).
- **Compressed chunks.** If `compressor` is non-null (e.g., zstd, blosc), JS cannot do targeted
  byte-range reads into the middle of a chunk. It must fetch the entire chunk and decompress.
  For the initial implementation, compressed data falls back to Python. Decompression support
  can be added later if needed.

### Handling compressed or missing LINDI data

Not all datasets will have uncompressed LINDI refs. The fallback strategy mirrors the video
widget:

1. JS attempts LINDI-based reading.
2. If LINDI is unavailable (404) or data is compressed, JS signals failure via a traitlet
   (e.g., `_pose_lindi_failed`).
3. Python observes the failure and falls back to the current h5py/remfile path for that camera.

## Data Format in JavaScript

Once JS reads the binary data, it holds:

```javascript
cameraData[cameraName] = {
  timestamps: Float64Array,          // (n_frames,) raw binary
  coordinates: {
    "NoseTip": Float64Array,         // (n_frames * 2,) flat, pairs of [x, y]
    "LeftEar": Float64Array,
    // ...
  },
  nFrames: number,
};
```

For rendering, frame `i` of keypoint `name`:
```javascript
const offset = frameIdx * 2;
const x = coordinates[name][offset];
const y = coordinates[name][offset + 1];
if (isNaN(x) || isNaN(y)) { /* skip */ }
```

This is more memory-efficient than the current JSON-parsed object arrays. Float64Array uses
contiguous memory with no per-element object overhead.

## Traitlet Changes (DANDI pose widget)

Removed from the data path:
- `all_camera_data` no longer carries coordinates or timestamps for DANDI widgets. It becomes
  metadata-only (keypoint colors and labels) or is replaced by a dedicated `keypoint_metadata`
  traitlet.

Added:
- `_pose_lindi_failed = Bool(False)` for fallback signaling (per-camera or global).
- `pose_container_paths = Dict({})` from Python, mapping camera names to their LINDI ref
  paths so JS knows where to read. Alternatively, JS discovers these from LINDI directly.

The `selected_camera` traitlet remains the trigger. When JS observes a camera selection, it
reads the corresponding data from LINDI instead of waiting for Python to populate
`all_camera_data`.

## Performance Comparison

For 143,948 frames, 14 keypoints:

| Metric | Current (Python) | Proposed (JS LINDI) |
|--------|-----------------|---------------------|
| Data over network | ~32 MB (HDF5 via remfile) + ~50 MB (JSON via websocket) | ~32 MB (S3 range requests) |
| Python processing | numpy conversion + JSON serialization | None (just metadata) |
| Websocket transfer | ~50 MB JSON text | ~1 KB metadata |
| Browser memory | JS objects with per-element overhead | Typed arrays, contiguous |
| Parallel fetches | Sequential (single remfile stream) | Parallel (one fetch per keypoint) |

The biggest win is eliminating the websocket bottleneck entirely. Binary data goes directly
from S3 to the browser.

## Scope

This migration applies only to the DANDI pose widget. The local pose widget continues using the
Python path because local files do not have LINDI indexes or S3 URLs.

## Related

- [neurosift_pattern_migration.md](neurosift_pattern_migration.md): Video widget migration
- [video_widget/dandi_video_resolution.md](video_widget/dandi_video_resolution.md): LINDI reading strategy
- [Issue #29](https://github.com/catalystneuro/nwb-video-widgets/issues/29): Widget hangs on large datasets
