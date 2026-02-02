# Design Documentation

This directory contains technical design documentation for the NWB Video Widgets project. These documents explain architecture decisions, performance trade-offs, and implementation details for developers working on or extending the codebase.

## Widget Overview

| Widget | Description | Documentation |
|--------|-------------|---------------|
| **Video Widget** | Multi-camera video playback with synchronized controls | [video_widget/](./video_widget/) |
| **Pose Estimation Widget** | Keypoint overlay on video with interactive visibility controls | [pose_estimation_widget/](./pose_estimation_widget/) |

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                     Jupyter Notebook                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐          ┌─────────────────────────┐  │
│  │  Python Widget  │◄────────►│  JavaScript Frontend    │  │
│  │  (anywidget)    │ traitlet │  (vanilla JS + Canvas)  │  │
│  │                 │   sync   │                         │  │
│  └────────┬────────┘          └────────────┬────────────┘  │
│           │                                 │               │
│           ▼                                 ▼               │
│  ┌─────────────────┐          ┌─────────────────────────┐  │
│  │   NWB File      │          │   HTML5 Video + Canvas  │  │
│  │   (pynwb)       │          │   (browser-native)      │  │
│  └────────┬────────┘          └─────────────────────────┘  │
│           │                                                 │
│           ▼                                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Data Source                             │   │
│  │  ┌──────────────┐    ┌───────────────────────────┐  │   │
│  │  │ Local Files  │    │ DANDI Archive (S3)        │  │   │
│  │  │ (HTTP Server)│    │ (remfile streaming)       │  │   │
│  │  └──────────────┘    └───────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

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

The `_utils.py` module provides common functionality:

| Function | Purpose |
|----------|---------|
| `discover_video_series()` | Find ImageSeries with external video files |
| `discover_pose_estimation_cameras()` | Find PoseEstimation containers |
| `start_video_server()` | HTTP server with Range request support |
| `get_camera_to_video_mapping()` | Auto-map camera names to video names |

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

