# Design Documentation

This directory contains technical design documentation for the NWB Video Widgets project. These documents explain architecture decisions, performance trade-offs, and implementation details for developers working on or extending the codebase.

## Widget Overview

| Widget | Description | Documentation |
|--------|-------------|---------------|
| **Video Widget** | Multi-camera video playback with synchronized controls | [video_widget/](./video_widget/) |
| **Pose Estimation Widget** | Keypoint overlay on video with interactive visibility controls | [pose_estimation_widget/](./pose_estimation_widget/) |

## Architecture Summary

There are two data paths depending on whether the source is local or DANDI. Both paths
resolve to the same two internal traitlets (`_video_urls` and `_video_timing`), so
JavaScript has a single code path for rendering regardless of the data source.

**Local widgets** load NWB files and serve videos through Python. Python sets
`_video_urls` and `_video_timing` synchronously in `__init__`.

**DANDI widgets** use the Neurosift pattern: Python only extracts seed identifiers from the
DANDI asset object. JavaScript fetches video metadata via LINDI and the DANDI REST API, then
writes back to `_video_urls` and `_video_timing`. If LINDI is unavailable, Python falls back
to targeted h5py reads.

The pose widget (both local and DANDI) still loads the NWB file in Python for pose coordinate
data.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Jupyter Notebook                              │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌───────────────────┐            ┌────────────────────────────────┐ │
│  │  Python Widget    │◄──────────►│  JavaScript Frontend           │ │
│  │  (anywidget)      │  _video_   │  (vanilla JS + Canvas)         │ │
│  │                   │  urls +    │                                │ │
│  │                   │  _video_   │  Reads _video_urls for <video> │ │
│  │                   │  timing    │  Reads _video_timing for UI    │ │
│  └──────┬────────────┘            └───────────┬────────────────────┘ │
│         │                                     │                      │
│    Local path                            DANDI path                  │
│    (Python fills traitlets               (JS fills traitlets         │
│     at init time)                         async, or Python           │
│         │                                 fallback on 404)           │
│         ▼                                     ▼                      │
│  ┌───────────────────┐            ┌────────────────────────────────┐ │
│  │  NWB File         │            │  LINDI (lindi.neurosift.org)   │ │
│  │  (pynwb)          │            │  + DANDI REST API              │ │
│  └──────┬────────────┘            │  fallback: h5py + remfile      │ │
│         │                         └───────────┬────────────────────┘ │
│         ▼                                     ▼                      │
│  ┌───────────────────┐            ┌────────────────────────────────┐ │
│  │  Local Files      │            │  DANDI Archive (S3)            │ │
│  │  (HTTP Server)    │            │  (direct video streaming)      │ │
│  └───────────────────┘            └────────────────────────────────┘ │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Why not unify the resolution mechanism?

Both paths produce the same output (`_video_urls` + `_video_timing`), but the resolution
mechanism is deliberately different. We considered using LINDI for local files too (the
`lindi` library supports local paths), which would have given a single resolution path. We
chose against it because:

- For local files, Python already has the NWB file open. Reading `external_file[0]`,
  `timestamps[0]`, and `timestamps[-1]` from an in-memory pynwb object is essentially free.
- Generating a LINDI index scans every dataset in the HDF5 file, including large
  electrophysiology arrays. For a typical IBL file this takes ~8 seconds, turning an instant
  operation into a noticeable delay.
- The unification that matters is at the traitlet interface (JavaScript has one code path),
  not at the resolution mechanism (Python vs JS, sync vs async).

See `video_widget/dandi_video_resolution.md` for details on the DANDI path and why we avoid
a full HDF5-in-JavaScript implementation.

## Key Design Decisions

### 1. anywidget Framework

**Choice**: Use anywidget instead of ipywidgets for frontend components.

**Rationale**:
- Single-file widget definition (Python + JS/CSS)
- Works across JupyterLab, Notebook, VS Code, Colab
- Hot-reload during development
- Smaller bundle size

### 2. Local HTTP Server for Videos

**Choice**: Serve local videos via HTTP instead of file:// URLs.

**Rationale**:
- HTTP Range requests enable efficient seeking
- CORS headers allow cross-origin access
- Works consistently across browsers

### 3. Lazy Loading for Pose Data

**Choice**: Load pose data on-demand when camera selected.

**Rationale**:
- Fast initial widget render
- Memory scales with viewed cameras, not total cameras
- Acceptable 1-2s delay on first selection

### 4. Canvas Overlay for Keypoints

**Choice**: Render keypoints on Canvas layer above video.

**Rationale**:
- Full control over styling (colors, labels, sizes)
- Efficient per-frame updates
- Transparency support for overlay effect

### 5. Traitlet Synchronization

**Choice**: Sync full pose data arrays to JavaScript.

**Rationale**:
- Instant scrubbing to any frame
- Simple implementation (no streaming protocol)
- Acceptable memory for typical pose data sizes (~16MB/camera)

## Performance Characteristics

| Operation | Complexity | Typical Time |
|-----------|------------|--------------|
| Widget initialization | O(1) | <100ms |
| Camera selection (uncached) | O(n_frames) | 1-2s |
| Camera selection (cached) | O(1) | <50ms |
| Frame render | O(n_keypoints) | <1ms |
| Frame lookup | O(log n_frames) | <0.1ms |
| Video seek (local) | HTTP Range | <100ms |
| Video seek (S3) | HTTP Range | 100-500ms |

## Shared Utilities

The `_utils.py` module provides common functionality used by the local widgets:

| Function | Purpose |
|----------|---------|
| `discover_video_series()` | Find ImageSeries with external video files |
| `discover_pose_estimation_cameras()` | Find PoseEstimation containers |
| `get_video_info()` | Extract start/end session times per video series |
| `get_video_timestamps()` | Extract full timestamp arrays per video series |
| `start_video_server()` | HTTP server with Range request support |
| `get_camera_to_video_mapping()` | Auto-map camera names to video names |

DANDI widgets do not use these utilities for video metadata. They use JavaScript-side
resolution via LINDI instead (see `neurosift_pattern_migration.md`).

## Testing Strategy

| Level | Coverage |
|-------|----------|
| Unit tests | Utility functions, data extraction |
| Integration tests | Widget rendering, traitlet sync |
| Manual testing | Browser compatibility, video playback |

## Browser Compatibility

Tested and supported:
- Chrome/Chromium 90+
- Firefox 88+
- Safari 14+
- Edge 90+
