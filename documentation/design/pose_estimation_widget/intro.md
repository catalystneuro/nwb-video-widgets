# Pose Estimation Widget Design Documentation

## Overview

The pose estimation widget overlays DeepLabCut/SLEAP keypoints on streaming video within Jupyter notebooks. It supports both local and DANDI-hosted NWB files, with lazy-loaded pose data and interactive keypoint visibility controls.

### File Structure

```
src/nwb_video_widgets/
├── local_pose_widget.py  # Local NWB file support
├── dandi_pose_widget.py  # DANDI-hosted NWB streaming
├── pose_widget.js        # Frontend rendering and overlay
├── pose_widget.css       # Styling with BEM naming
└── _utils.py             # Shared utilities
```

### Widget Classes

| Class | Purpose | Data Source |
|-------|---------|-------------|
| `NWBLocalPoseEstimationWidget` | Local file playback | Local filesystem |
| `NWBDANDIPoseEstimationWidget` | Remote streaming | DANDI archive |

### Technology Stack

- **Framework**: anywidget (Jupyter widget protocol)
- **Video Rendering**: HTML5 `<video>` element
- **Pose Overlay**: Canvas 2D API
- **Color Mapping**: matplotlib colormaps
- **NWB I/O**: pynwb with ndx-pose extension

---

## Core Concepts

Before diving into implementation details, understanding these five mental models will help you work effectively with the widget.

### 1. Traitlets as the Contract

The widget uses **traitlets** (Python) with `.tag(sync=True)` to synchronize state between Python and JavaScript. This is the fundamental communication mechanism.

```python
# Python side (local_pose_widget.py)
class NWBLocalPoseEstimationWidget(anywidget.AnyWidget):
    selected_camera = traitlets.Unicode("").tag(sync=True)
    all_camera_data = traitlets.Dict({}).tag(sync=True)
    loading = traitlets.Bool(False).tag(sync=True)
```

```javascript
// JavaScript side (pose_widget.js)
const camera = model.get("selected_camera");
model.set("selected_camera", "LeftCamera");
model.save_changes();

// React to Python changes
model.on("change:all_camera_data", () => { ... });
```

**Key insight**: All mutable state flows through the model. UI updates are reactions to model changes, not direct user action handlers. This keeps Python and JavaScript synchronized.

### 2. Frame-Based vs Time-Based Thinking

This is the core coordination problem: **video plays in time, but pose data is frame-indexed**.

```
Video element:    video.currentTime = 3.5 seconds
Pose data:        coordinates[frameIndex] = [x, y]
Timestamps:       [0.0, 0.033, 0.066, 0.1, ...]  (NWB session time)
```

The widget bridges this gap with binary search:

```javascript
function getFrameIndex() {
    const timestamps = data.timestamps;
    const targetTime = timestamps[0] + video.currentTime;  // Convert to session time
    return findFrameIndex(timestamps, targetTime);  // O(log n) lookup
}
```

**Why binary search?** For 60fps 1-hour video (216K frames), binary search is O(17) operations vs linear search O(216K) per frame render.

**Why not assume uniform spacing?** NWB timestamps may have irregular intervals (dropped frames, variable frame rates). Time-based lookup is robust.

### 3. Canvas Overlay Pattern

The widget uses two-layer rendering: a `<video>` element with a transparent `<canvas>` positioned directly on top.

```
┌─────────────────────────┐
│       <canvas>          │  ← Pose keypoints drawn here
│  (pointer-events: none) │
├─────────────────────────┤
│       <video>           │  ← Video frames rendered here
│                         │
└─────────────────────────┘
```

**Why canvas over video?**
- Full control over drawing (circles, labels, colors)
- Transparency for overlay effect
- No interference with video controls (pointer-events: none)

**Alternatives considered:**
- WebGL shader: GPU-accelerated but complex, limited text support
- SVG overlay: DOM-based debugging but poor performance with many points

### 4. Lazy Loading Pattern

Pose data is loaded on-demand when the user selects a camera, not at widget initialization.

```
Initialization:                     On Camera Selection:
┌────────────────────────┐         ┌────────────────────────┐
│ Discover cameras       │         │ Set loading = True     │
│ Extract metadata only  │         │ Read series.data[:]    │
│ all_camera_data = {}   │  ───►   │ Convert NaN → null     │
│ Render UI immediately  │         │ Cache in all_camera_data│
└────────────────────────┘         │ Set loading = False    │
        O(1)                       └────────────────────────┘
                                           O(n_frames)
```

| Metric | Eager (all cameras) | Lazy (per camera) |
|--------|---------------------|-------------------|
| Init time | O(n_cameras * n_frames) | O(1) |
| Memory at start | High | Minimal |
| First camera delay | None | ~1-2s |

**Decision**: Lazy loading chosen because most sessions have 1-3 cameras, users view one at a time, and cached cameras switch instantly.

### 5. Explicit User Control for Pose-to-Video Mapping

The widget makes **no assumptions** about naming conventions. Users explicitly select which video to overlay each pose estimation on via dropdown menus.

```
Python sends to JS:
├── available_cameras: ["BodyCamera", "LeftCamera"]
├── available_videos: ["VideoBodyCamera", "VideoLeftCamera", ...]
├── video_name_to_url: {"VideoBodyCamera": "http://...", ...}
└── camera_to_video: {}  ← Empty at init, user fills in
```

**Why explicit selection?**
- Works with any NWB file structure
- User always knows what's mapped
- No hidden assumptions to debug

---

## Data Flow

### Initialization (Fast Path)

```
NWB File
    │
    ▼
discover_pose_estimation_cameras()
    │ Finds PoseEstimation containers
    │ Extracts camera names and metadata
    ▼
Initialize widget with empty pose data
    │ available_cameras: ["LeftCamera", "RightCamera", ...]
    │ all_camera_data: {}  (empty - loaded lazily)
    ▼
Render settings panel immediately
```

### Lazy Loading (On Camera Selection)

```
User selects camera
    │
    ▼
JS: model.set("selected_camera", "LeftCamera")
    │
    ▼
Python: @observe("selected_camera") triggers
    │
    ├─ Set loading = True
    │
    ▼
_load_camera_pose_data()
    │
    ├─ Extract keypoint metadata (names, colors)
    ├─ Read pose coordinates: series.data[:]
    ├─ Convert NaN → null for missing frames
    ├─ Read timestamps: series.timestamps[:]
    │
    ▼
Update all_camera_data[camera]
    │
    ├─ Set loading = False
    │
    ▼
JS: model.on("change:all_camera_data")
    │
    ├─ Hide loading overlay
    ├─ Create keypoint toggle buttons
    ├─ Start video playback
    └─ Begin rendering pose overlay
```

### Frame Rendering (Real-time)

```
video.timeupdate event
    │
    ▼
getFrameIndex()
    │ Binary search: O(log n)
    │ Maps video.currentTime → frame index
    ▼
drawPose()
    │
    ├─ Clear canvas
    ├─ For each visible keypoint:
    │   ├─ Get coordinates[frameIndex]
    │   ├─ Skip if null (missing data)
    │   ├─ Scale to display dimensions
    │   ├─ Draw colored circle
    │   └─ Draw label (if enabled)
    └─ Update time display
```

---

## Data Format

### Python to JavaScript (via Traitlets)

```python
all_camera_data = {
    "LeftCamera": {
        "keypoint_metadata": {
            "NoseTip": {"color": "#e41a1c", "label": "NoseTip"},
            "LeftEar": {"color": "#377eb8", "label": "LeftEar"},
            ...
        },
        "pose_coordinates": {
            "NoseTip": [[123.4, 456.7], null, [124.1, 455.2], ...],
            "LeftEar": [[200.0, 300.0], [201.1, 299.8], null, ...],
            ...
        },
        "timestamps": [0.0, 0.0333, 0.0666, ...]  # Session time
    }
}
```

**Key insight**: Coordinates are indexed by frame: `coordinates[keypoint_name][frame_index] = [x, y]` or `null` for missing data.

### NWB Source Structure

```
nwbfile.processing["behavior"].data_interfaces["PoseEstimation"]
├── pose_estimation_series["LeftCamera_NoseTip"]
│   ├── data: (n_frames, 2) float array
│   ├── timestamps: (n_frames,) float array
│   └── confidence: (n_frames,) float array (unused currently)
├── pose_estimation_series["LeftCamera_LeftEar"]
│   └── ...
└── skeleton_links (for future skeleton visualization)
```

---

## Performance Considerations

### Binary Search for Frame Lookup

```javascript
function findFrameIndex(timestamps, targetTime) {
    // O(log n) binary search
    let left = 0, right = timestamps.length - 1;
    while (left < right) {
        const mid = Math.floor((left + right) / 2);
        if (timestamps[mid] < targetTime) left = mid + 1;
        else right = mid;
    }
    return left;
}
```

### Canvas Rendering Optimization

```javascript
function drawPose() {
    ctx.clearRect(0, 0, width, height);  // Single clear

    for (const [name, coords] of Object.entries(coordinates)) {
        if (visibleKeypoints[name] === false) continue;  // Skip hidden
        const coord = coords[frameIdx];
        if (!coord) continue;  // Skip missing data

        // Render single keypoint
        ctx.arc(x, y, 5, 0, 2 * Math.PI);
        ctx.fill();
    }
}
```

**Optimizations applied:**
- Single `clearRect()` per frame
- Early exit for hidden keypoints
- Early exit for null coordinates
- Pre-computed scale factors
- No DOM manipulation during render

### Memory Efficiency

| Data | Storage Format | Size Estimate |
|------|----------------|---------------|
| Coordinates | `[[x,y], null, [x,y], ...]` | ~16 bytes/frame/keypoint |
| Timestamps | `[t0, t1, ...]` | ~8 bytes/frame |
| Metadata | `{name: {color, label}}` | ~100 bytes/keypoint |

**Example**: 10 keypoints, 100K frames = ~16MB per camera

**Memory strategy:**
- Data converted to JSON-serializable lists (not numpy)
- NaN values stored as `null` (compact)
- Only loaded cameras consume memory

---

## UI/UX Design

### Settings Panel Layout

```
┌─────────────────────────────────────────────────────┐
│ Settings                                      Close │
├─────────────────────────────────────────────────────┤
│ Pose Estimation Selection                           │
│ Select a pose estimation to display.                │
│                                                     │
│ ○ BodyCamera      0:03.6 - 60:32.5    1 keypoints  │
│ ● LeftCamera      0:03.5 - 60:32.5   11 keypoints  │
│ ○ RightCamera     0:03.5 - 60:32.5   11 keypoints  │
│   Video: [VideoLeftCamera ▼]                        │
├─────────────────────────────────────────────────────┤
│ Keypoint Visibility                                 │
│                                                     │
│ [All] [None]                                        │
│ [NoseTip] [LeftEar] [RightEar] [Spine1] [Spine2]   │
│ [Spine3] [LeftPaw] [RightPaw] [TailBase] [TailTip] │
├─────────────────────────────────────────────────────┤
│ Display Options                                     │
│ ☑ Show keypoint labels                             │
└─────────────────────────────────────────────────────┘
```

### Loading Overlay

```
┌────────────────────────────────┐
│                                │
│         ◠ (spinner)            │
│    Loading pose data...        │
│                                │
└────────────────────────────────┘
```

Shown when:
- `loading === true` (Python loading data)
- `selected_camera && !all_camera_data[camera]` (waiting for sync)

---

## Coordinate System

```
Video Frame (original)          Canvas (display)
┌─────────────────────┐         ┌─────────────────────┐
│ (0,0)               │         │ (0,0)               │
│   ●─────────────────│  scale  │   ●─────────────────│
│   │                 │ ──────► │   │                 │
│   │  video.videoWidth         │   │  DISPLAY_WIDTH  │
│   │  video.videoHeight        │   │  DISPLAY_HEIGHT │
└───┴─────────────────┘         └───┴─────────────────┘

Scale factors:
  scaleX = DISPLAY_WIDTH / video.videoWidth
  scaleY = DISPLAY_HEIGHT / video.videoHeight

Transformed coordinate:
  canvas_x = pose_x * scaleX
  canvas_y = pose_y * scaleY
```

---

## Split File Support

The widget supports two NWB file patterns:

### Pattern 1: Single File

Videos and pose estimation in same NWB:

```python
widget = NWBLocalPoseEstimationWidget(nwbfile=nwbfile)
```

### Pattern 2: Split Files

Raw file (videos) + processed file (pose):

```python
widget = NWBLocalPoseEstimationWidget(
    nwbfile=nwbfile_processed,      # Contains pose data
    video_nwbfile=nwbfile_raw,      # Contains video references
)
```

**Implementation**: Widget checks `video_nwbfile` parameter; if provided, uses it for video discovery while using `nwbfile` for pose data.

---

## Error Handling

| Scenario | Handling |
|----------|----------|
| No pose data in NWB | Widget shows empty camera list |
| Missing keypoint frame | Rendered as `null`, skipped in canvas |
| Invalid color format | Falls back to gray (#999) |
| Network error (DANDI) | Loading state persists, browser retry |

---

## Assumptions

1. **NWB structure**: Pose data in `processing["behavior"]["PoseEstimation"]`
2. **Coordinate system**: Pixel coordinates matching video dimensions
3. **Frame alignment**: Pose timestamps align with video frames
4. **Missing data**: Represented as NaN in NWB, null in JSON
5. **Keypoint names**: Format "CameraName_KeypointName" in NWB

---

## Extensibility

### Adding Skeleton Visualization

NWB PoseEstimation includes `skeleton_links` for connecting keypoints:

```python
# Future implementation
skeleton_links = pose_estimation.skeleton_links  # [(kp1, kp2), ...]
# Draw lines between connected keypoints
```

### Adding Confidence Visualization

PoseEstimationSeries includes confidence scores:

```python
confidence = series.confidence[:]  # (n_frames,) array
# Could map to opacity or point size
```

### Adding Interpolation

Fill missing frames with interpolated positions:

```javascript
function interpolateCoordinates(coords, frameIdx) {
    if (coords[frameIdx]) return coords[frameIdx];
    // Find nearest non-null frames
    // Linear interpolate position
}
```

---

## Known Limitations

1. **Skeleton lines**: Not yet implemented (data available in NWB)
2. **Confidence scores**: Not visualized (data available)
3. **3D pose**: Only 2D coordinates supported
4. **Frame interpolation**: Missing frames shown as gaps
5. **Multi-animal**: Single animal per camera assumed
6. **Playback speed**: Fixed 1x speed (no slow-mo)
7. **Export**: Cannot save annotated frames as images
