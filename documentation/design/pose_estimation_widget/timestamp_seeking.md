# Timestamp Seeking in the Pose Estimation Widget

The pose estimation widget uses a **frame-based seek bar** that maps directly to pose data frames via timestamps. This document explains the implementation model for future developers.

## Core Concepts

The widget must synchronize three things:
1. **Seek bar position** (frame index: 0 to n_frames-1)
2. **Video playback position** (video.currentTime: 0 to duration in seconds)
3. **Time label display** (session timestamp from NWB)

The pose data uses NWB session timestamps (e.g., 847.3 seconds into the recording session), while the video element uses file-relative time (0 to duration). The widget translates between these coordinate systems.

## Data Flow

```
SEEKING (user drags seek bar):
  seekBar.value (frame index)
       |
       v
  timestamps[frameIdx] - timestamps[0]  -->  video.currentTime
       |
       v
  Video seeks, triggers "seeked" event
       |
       v
  drawPose() called  -->  getFrameIndex()  -->  updateTimeLabel()

PLAYBACK (video playing):
  video "timeupdate" event fires
       |
       v
  drawPose() called
       |
       v
  getFrameIndex(): findFrameIndex(timestamps, timestamps[0] + video.currentTime)
       |
       v
  Draw pose at frameIdx, updateTimeLabel(frameIdx)
```

## Key Functions

**Frame to video time** (for seeking):
```javascript
video.currentTime = timestamps[frameIdx] - timestamps[0];
```

**Video time to frame** (for playback):
```javascript
function getFrameIndex() {
  const timestamps = getCurrentCameraData()?.timestamps;
  if (!timestamps || timestamps.length === 0) return 0;
  return findFrameIndex(timestamps, timestamps[0] + video.currentTime);
}
```

The `findFrameIndex` function uses binary search to find the frame whose timestamp is closest to the target time.

## Event-Driven Updates

The widget relies on video element events to trigger UI updates:

```javascript
video.addEventListener("loadedmetadata", drawPose);  // Initial render
video.addEventListener("seeked", drawPose);          // After seek completes
video.addEventListener("timeupdate", drawPose);      // During playback
```

The `drawPose()` function handles all rendering: it computes the current frame index, draws keypoints on the canvas, and updates the time label.

Model changes from Python (via traitlets) also trigger updates:

```javascript
model.on("change:all_camera_data", () => {
  // Camera data loaded - update seek bar max and redraw
  const data = getCurrentCameraData();
  if (data?.timestamps?.length) {
    seekBar.max = data.timestamps.length - 1;
  }
  drawPose();
});

model.on("change:visible_keypoints", () => {
  visibleKeypoints = { ...model.get("visible_keypoints") };
  updateToggleStyles();
  drawPose();
});
```

## Asynchronous Data Loading

Camera pose data is loaded lazily when a camera is selected. The Python backend sets `loading=True`, fetches the data, updates `all_camera_data`, then sets `loading=False`.

UI elements that depend on the data (like `seekBar.max`) must be updated in the `change:all_camera_data` handler, not in response to `change:selected_camera`, because the data hasn't arrived yet when the camera selection changes.

## Comparison with Video Widget

| Aspect | Video Widget | Pose Widget |
|--------|--------------|-------------|
| Seek bar units | Video seconds (0 to duration) | Frame index (0 to n_frames-1) |
| Time display | `timestamps[0] + video.currentTime` | `timestamps[frameIdx]` (actual) |
| Seeking | `video.currentTime = seekBar.value` | `video.currentTime = timestamps[frameIdx] - timestamps[0]` |

The pose widget uses frame-based seeking because pose data is indexed by frame, and frames must align exactly with the video for the overlay to be accurate.
