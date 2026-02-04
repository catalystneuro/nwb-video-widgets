# Timestamp-Based Seeking

## Overview

This document describes how the video widget handles seeking and timestamp display, when the current approach works correctly, and edge cases where it may produce incorrect results.

## Current Implementation

### How Seeking Works Now

The seek bar operates in **video-relative time** (0 to `video.duration`). The displayed session time is calculated by adding an offset from NWB timestamps:

```
Seek bar range:  0 ─────────────────────► video.duration (e.g., 120.5 seconds)
Seek action:     video.currentTime = seekBar.value
Time display:    timestamps[0] + video.currentTime (translated to session time)
```

### Code Flow

1. **Seek bar initialization** (`video_widget.js:511-512`):
   ```javascript
   videos[0].addEventListener("loadedmetadata", () => {
     seekBar.max = videos[0].duration;  // Uses video duration, not timestamps
   });
   ```

2. **User seeks** (`video_widget.js:564-567`):
   ```javascript
   seekBar.addEventListener("input", () => {
     const time = parseFloat(seekBar.value);  // Video-relative time
     videos.forEach((v) => (v.currentTime = time));
   });
   ```

3. **Time display update** (`video_widget.js:518-528`):
   ```javascript
   videos[0].addEventListener("timeupdate", () => {
     const offset = getSessionTimeOffset();  // timestamps[0]
     const currentSessionTime = offset + videos[0].currentTime;
     timeLabel.textContent = formatTime(currentSessionTime) + " / " + formatTime(displayEnd);
   });
   ```

### Timestamp Usage

Currently, only two values from the timestamps array are used:

| Value | Location | Purpose |
|-------|----------|---------|
| `timestamps[0]` | `getSessionTimeOffset()` | Add offset to display session time |
| `timestamps[length-1]` | `getSessionEndTime()` | Display total duration |

The full per-frame timestamp array is transferred to JavaScript but not utilized for seeking or display.

### Visual Representation

```
NWB Timestamps:     [847.3, 847.33, 847.36, ..., 967.8]
                       │                           │
                       │ Only these two used       │
                       ▼                           ▼
                    offset                      end time

Video element:      0.0 ──────────────────────► 120.5 (duration)
                     │                            │
Seek bar:           0 ════════════════════════► 120.5
                     │                            │
Display:          847.3 ────────────────────► 967.8 (offset + currentTime)
```

## When This Works Correctly

### Uniform Timestamps (Constant Frame Rate)

For videos recorded at a constant frame rate, timestamps are uniformly spaced:

```
Frame:       0      1      2      3      ...  3600
Timestamp:   847.3  847.33 847.36 847.40 ...  967.8
Video time:  0.0    0.033  0.066  0.10   ...  120.5
```

The relationship is linear: `timestamp[N] = timestamp[0] + N / frameRate`

In this case, the current approach is **correct**:

```
User seeks to video time 30.0
  → Video shows frame 900 (at 30fps)
  → Display shows: 847.3 + 30.0 = 877.3
  → Actual timestamp[900] = 847.3 + 900/30 = 877.3 ✓
```

The displayed session time matches the actual NWB timestamp for that frame.

## Edge Case: Non-Uniform Timestamps

### When Timestamps Are Not Uniformly Spaced

Non-uniform timestamps can occur due to:
- Variable frame rate cameras
- Dropped frames during recording
- Gaps in recording (camera paused/resumed)
- Hardware timing jitter

Example with a gap in recording:

```
Frame:       0      1      2      3      4      5      ...
Timestamp:   847.3  847.33 847.36 850.0  850.03 850.06 ...
                                  ↑
                              Gap of ~2.6 seconds (frames dropped or paused)

Video time:  0.0    0.033  0.066  0.10   0.133  0.166  ...
                                  ↑
                              No gap in video playback
```

### How the Current Implementation Fails

With non-uniform timestamps, the linear offset calculation produces incorrect session times:

```
User seeks to video time 0.10 (frame 3)
  → Video shows frame 3
  → Display shows: 847.3 + 0.10 = 847.4  ✗ INCORRECT
  → Actual timestamp[3] = 850.0          ✓ CORRECT
```

The display shows 847.4, but the actual NWB timestamp for frame 3 is 850.0.

### Visual Representation of the Problem

```
Actual timestamps:  [847.3, 847.33, 847.36, 850.0, 850.03, ...]
                     ├─────────────────────┤
                            2.7 second gap

Video playback:     [0.0,   0.033,  0.066,  0.10,  0.133, ...]
                     ├─────────────────────┤
                         Continuous (no gap)

Current display:    offset + video_time = 847.3 + 0.10 = 847.4
Should display:     timestamp[frame_number] = 850.0
```

### Impact

| Scenario | Impact |
|----------|--------|
| Aligning video with neural data | Incorrect alignment if using displayed time |
| Seeking to specific session time | Cannot accurately navigate to a known timestamp |
| Correlating events across recordings | Times may be off by the cumulative gap duration |

## Additional Considerations

### Multi-Video Timestamp Mismatch

Different videos may have different timestamp ranges:

```
VideoLeft:   [847.3 ─────────────────── 967.8]
VideoRight:  [848.0 ────────────────── 965.2]
VideoBody:   [847.5 ──────────────────────── 970.1]
```

The current implementation uses only the first selected video's timestamps for display. If videos have different offsets, the displayed time is only accurate for the first video.

### Data Transfer

The full timestamp array is sent to JavaScript (potentially 100K+ floats for long recordings) but only the first and last values are used. This is overhead that could be leveraged for accurate timestamp display.

## Potential Future Improvement: Frame-Accurate Timestamp Display

To correctly display session time for non-uniform timestamps, the widget would need to look up the actual timestamp for the current frame rather than computing it with a linear offset.

### Approach: Use Per-Frame Timestamp Lookup

Instead of `display = timestamps[0] + video.currentTime`, use the actual timestamp for the current frame:

```javascript
// Current (linear approximation)
const sessionTime = timestamps[0] + video.currentTime;

// Accurate (frame lookup)
const frameNumber = Math.round(video.currentTime * frameRate);
const sessionTime = timestamps[frameNumber];
```

### Challenge: Frame Rate Is Not Exposed

The HTML5 `<video>` element does not expose frame rate. Options to obtain it:

1. **Store in NWB metadata**: Extract from ImageSeries and pass to JavaScript
2. **Calculate from timestamps**: `frameRate = (timestamps.length - 1) / (timestamps[last] - timestamps[0])`
3. **Use `requestVideoFrameCallback`**: Modern API that provides frame metadata (limited browser support)

### Challenge: Seek Bar Representation

For non-uniform timestamps, the seek bar could either:

**Option A: Keep linear seek bar, fix display only**
- Seek bar stays as video time (0 to duration)
- Display uses frame lookup for accurate timestamp
- Simple change, fixes display accuracy

**Option B: Session-time seek bar**
- Seek bar range is `timestamps[0]` to `timestamps[last]`
- Requires translation when seeking: `videoTime = sessionTime - timestamps[0]`
- More complex, but seek bar position matches display

### Multi-Video Considerations

When multiple videos have different timestamp ranges:

```
VideoLeft:   [847.3 ─────────────────── 967.8]
VideoRight:  [848.0 ────────────────── 965.2]
VideoBody:   [847.5 ──────────────────────── 970.1]
```

Possible strategies:
- **Intersection**: Only allow seeking in overlapping range (848.0 to 965.2)
- **Primary video**: Use first video's range, others clamp to their valid range
- **Union**: Full range, videos pause at their boundaries

### Implementation Complexity

| Change | Complexity | Benefit |
|--------|------------|---------|
| Frame lookup for display | Medium | Accurate timestamps for non-uniform data |
| Session-time seek bar | Medium | Intuitive seeking to session time |
| Multi-video handling | High | Correct behavior with mismatched ranges |

### When to Implement

This improvement should be prioritized if:
- Users report incorrect timestamps when viewing variable frame rate videos
- Scientific workflows require precise alignment with neural data
- Videos with gaps or dropped frames are common in the target datasets

For constant frame rate videos (the common case), the current implementation is correct and sufficient.

## Summary

| Scenario | Current Behavior | Accuracy |
|----------|------------------|----------|
| Uniform timestamps (constant FPS) | Correct | Exact |
| Non-uniform timestamps (variable FPS) | Linear approximation | May be incorrect |
| Gaps in recording | Ignores gaps | Incorrect after gap |
| Multiple videos, same offset | Correct | Exact |
| Multiple videos, different offsets | Uses first video's offset | Incorrect for other videos |

The current implementation prioritizes simplicity and works correctly for the common case of constant frame rate recordings. The full timestamp array is available in JavaScript for future improvements if accurate handling of non-uniform timestamps becomes necessary.
