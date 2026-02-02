# Pose Estimation Widget Design Documentation

## Overview

The pose estimation widget overlays DeepLabCut/SLEAP keypoints on streaming video within Jupyter notebooks. It supports both local and DANDI-hosted NWB files, with lazy-loaded pose data and interactive keypoint visibility controls.

## Architecture

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
Map cameras to videos
    │ Convention: "LeftCamera" → "VideoLeftCamera"
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
    └─ Update debug info
```

## Performance Considerations

### Lazy Loading Strategy

**Why lazy loading?**

| Metric | Eager (all cameras) | Lazy (per camera) |
|--------|---------------------|-------------------|
| Init time | O(n_cameras * n_frames) | O(1) |
| Memory at start | High | Minimal |
| First camera delay | None | ~1-2s |
| Switch camera delay | None | ~1-2s (if not cached) |

**Decision**: Lazy loading chosen because:
- Most sessions have 1-3 cameras
- Users typically view one camera at a time
- Cached cameras have instant switching

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

**Why not linear search?**
- 60fps video, 1 hour = 216,000 frames
- Linear: O(216K) per frame render
- Binary: O(17) per frame render

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

## Data Format

### Python → JavaScript (via Traitlets)

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

## UI/UX Design

### Settings Panel Layout

```
┌─────────────────────────────────────────────────────┐
│ Settings                                      Close │
├─────────────────────────────────────────────────────┤
│ Camera Selection                                    │
│ Select a camera to display pose estimation overlay. │
│                                                     │
│ ○ BodyCamera      0:03.6 - 60:32.5    1 keypoints  │
│ ● LeftCamera      0:03.5 - 60:32.5   11 keypoints  │
│ ○ RightCamera     0:03.5 - 60:32.5   11 keypoints  │
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

### Keypoint Toggle States

```css
/* Inactive: gray background, colored border */
.pose-widget__keypoint-toggle {
    background: #f5f5f5;
    border: 2px solid ${keypoint.color};
    color: #718096;
}

/* Active: colored background, white text */
.pose-widget__keypoint-toggle--active {
    background: ${keypoint.color};
    color: white;
}
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

## Assumptions

1. **NWB structure**: Pose data in `processing["behavior"]["PoseEstimation"]`
2. **Naming convention**: Camera "X" maps to video "VideoX" (see limitation below)
3. **Coordinate system**: Pixel coordinates matching video dimensions
4. **Frame alignment**: Pose timestamps align with video frames
5. **Missing data**: Represented as NaN in NWB, null in JSON
6. **Keypoint names**: Format "CameraName_KeypointName" in NWB

## Pose-to-Video Mapping

### Implementation (Explicit User Selection)

The widget provides **explicit user control** over pose-to-video mapping via dropdown menus. No assumptions are made about naming conventions - users explicitly select which video to overlay each pose estimation on.

#### Data Flow

```
Python sends to JS:
├── available_cameras: ["BodyCamera", "LeftCamera", "RightCamera"]
├── available_videos: ["VideoBodyCamera", "VideoLeftCamera", ...]  # Sorted alphabetically
├── video_name_to_url: {"VideoBodyCamera": "http://...", ...}
└── camera_to_video: {}  # Empty - user selects

JS renders:
├── Pose estimation list with video dropdown for each
├── Dropdowns start with "-- Select video --"
└── User explicitly selects video for each pose estimation

User interaction:
├── Select video from dropdown for each pose estimation
├── Radio button enabled only when video selected
└── Changes sync back to Python via camera_to_video trait
```

#### UI Design

Each pose estimation item shows:
```
┌─────────────────────────────────────────────────────────────┐
│ ○ LeftCamera                    0:03.5 - 60:32.5 | 11 kp    │
│   Video: [-- Select video -- ▼]                             │
└─────────────────────────────────────────────────────────────┘
```

- Radio button disabled until video selected
- Dropdown shows all available videos (alphabetically sorted) with time ranges
- No pre-selection - user must explicitly choose
- User can select "-- Select video --" to unmap

#### Benefits

1. **No assumptions**: No naming convention requirements
2. **Explicit control**: User always knows what's mapped
3. **Discoverability**: All pose estimations and videos visible
4. **Flexibility**: Works with any file structure

## Trade-offs

### Lazy Loading vs Eager Loading

**Decision**: Lazy loading per camera

| Approach | Pros | Cons |
|----------|------|------|
| **Lazy (chosen)** | Fast init, scales to many cameras | Delay on first selection |
| Eager | Instant switching | Slow init, high memory |

**Rationale**: Acceptable delay (1-2s) for significant memory/time savings.

### Full Data Sync vs Streaming

**Decision**: Load entire camera dataset to JS

| Approach | Pros | Cons |
|----------|------|------|
| **Full sync (chosen)** | Instant scrubbing, simple code | Memory scales with length |
| Streaming | Low memory | Complex, latency on seek |

**Rationale**: Pose data is sparse (~16MB/camera); memory is acceptable.

### Canvas Overlay vs Video Filter

**Decision**: Canvas overlay on video element

| Approach | Pros | Cons |
|----------|------|------|
| **Canvas (chosen)** | Full control, transparency, labels | Two-layer rendering |
| WebGL shader | GPU-accelerated | Complex, limited text support |
| SVG overlay | DOM-based debugging | Poor performance with many points |

**Rationale**: Canvas provides best balance of control and performance.

### Frame-based vs Time-based Coordinates

**Decision**: Time-based with binary search

| Approach | Pros | Cons |
|----------|------|------|
| **Time-based (chosen)** | Handles variable frame rates | Binary search overhead |
| Frame-based | Direct array index | Assumes constant frame rate |

**Rationale**: NWB timestamps may have irregular intervals; time-based is robust.

### Color Assignment Strategy

**Decision**: Matplotlib colormaps with override option

```python
# Default: automatic from colormap
widget = NWBLocalPoseEstimationWidget(nwbfile, cmap="tab10")

# Override: explicit hex colors
widget = NWBLocalPoseEstimationWidget(
    nwbfile,
    custom_colors={"NoseTip": "#ff0000", "LeftEar": "#00ff00"}
)
```

**Rationale**: Sensible defaults for quick visualization; customizable for publication.

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

## Error Handling

| Scenario | Handling |
|----------|----------|
| No pose data in NWB | Widget shows empty camera list |
| Camera without video | Camera excluded from selection |
| Missing keypoint frame | Rendered as `null`, skipped in canvas |
| Invalid color format | Falls back to gray (#999) |
| Network error (DANDI) | Loading state persists, browser retry |

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

## Known Limitations

1. **Skeleton lines**: Not yet implemented (data available in NWB)
2. **Confidence scores**: Not visualized (data available)
3. **3D pose**: Only 2D coordinates supported
4. **Frame interpolation**: Missing frames shown as gaps
5. **Multi-animal**: Single animal per camera assumed
6. **Playback speed**: Fixed 1x speed (no slow-mo)
7. **Export**: Cannot save annotated frames as images
