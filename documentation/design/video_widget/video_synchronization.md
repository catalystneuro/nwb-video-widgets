# Video Synchronization

## Problem

When playing multiple videos simultaneously in a browser, they naturally drift apart over time due to:

1. **Network latency differences**: Videos stream at different rates
2. **Buffering variations**: Each video buffers independently
3. **Decode timing**: Different codecs/resolutions decode at different speeds
4. **Browser scheduling**: Media pipeline handles each video independently

For scientific applications like multi-camera behavioral recordings, precise synchronization is critical.

## Solution

Master-slave synchronization where:
- First video in the grid is the "master"
- All other videos sync their playback position to the master
- A correction threshold prevents excessive seeking (which causes stuttering)

### Architecture

```
                    +------------------+
                    |   Master Video   |
                    |   (videos[0])    |
                    +--------+---------+
                             |
                             | currentTime
                             v
            +----------------+----------------+
            |                |                |
            v                v                v
    +-------+------+  +------+-------+  +-----+--------+
    | Slave Video  |  | Slave Video  |  | Slave Video  |
    | (videos[1])  |  | (videos[2])  |  | (videos[n])  |
    +-------+------+  +------+-------+  +-----+--------+
            |                |                |
            v                v                v
       if drift > 100ms, correct currentTime
```

## Implementation

### Sync Loop (`video_widget.js`)

Runs every animation frame (~60fps) using `requestAnimationFrame`:

```javascript
function syncVideos() {
    if (videos.length < 2 || !isPlaying) {
        return;
    }

    const masterTime = videos[0].currentTime;
    for (let i = 1; i < videos.length; i++) {
        const drift = videos[i].currentTime - masterTime;
        // Correct if drift exceeds 100ms
        if (Math.abs(drift) > 0.1) {
            videos[i].currentTime = masterTime;
        }
    }

    syncAnimationId = requestAnimationFrame(syncVideos);
}
```

### Drift Threshold

The 100ms threshold balances two concerns:

| Threshold | Effect |
|-----------|--------|
| Too small (10ms) | Constant seeking, causes stuttering |
| Too large (500ms) | Noticeable desynchronization |
| **100ms (chosen)** | Imperceptible to humans, stays aligned |

### Async Play Handling

The play button handler waits for all videos to start:

```javascript
playPauseBtn.addEventListener("click", async () => {
    if (isPlaying) {
        videos.forEach((v) => v.pause());
        cancelAnimationFrame(syncAnimationId);
        isPlaying = false;
    } else {
        // Play all videos and wait for them to start
        const playPromises = videos.map((v) =>
            v.play().catch((err) => {
                console.warn("Video play failed:", err);
            })
        );
        await Promise.all(playPromises);
        isPlaying = true;
        syncVideos();
    }
    updatePlayPauseButton(isPlaying);
});
```

Key aspects:
1. **Promise.all**: Waits for all videos to begin playback
2. **Error catching**: One failed video doesn't block others
3. **Sync starts after play**: Loop only runs during active playback

### Seeking

When user moves the seek bar, all videos jump together:

```javascript
seekBar.addEventListener("input", () => {
    const time = parseFloat(seekBar.value);
    videos.forEach((v) => (v.currentTime = time));
});
```

### Video Preloading

To minimize initial buffering:

```javascript
video.preload = "auto";  // Browser buffers video data
video.muted = true;       // Required for autoplay policies
```

### Session Time Display

Time displays relative to NWB session, not video file:

```javascript
function getSessionTimeOffset() {
    const timestamps = model.get("video_timestamps");
    return timestamps[videoName][0];  // First timestamp from NWB
}

// Display: sessionOffset + video.currentTime
const currentSessionTime = offset + videos[0].currentTime;
```

This allows correlation with other NWB data (neural recordings, events).

### Cleanup

When widget is destroyed:

```javascript
return () => {
    if (syncAnimationId) {
        cancelAnimationFrame(syncAnimationId);
    }
};
```

## Limitations

1. **Master determines pace**: If master video buffers, all videos pause
2. **No audio sync**: Videos are muted; audio sync not implemented
3. **Frame-level precision**: ~100ms, not frame-accurate
4. **Variable frame rates**: Different FPS videos may appear slightly off

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Web Audio API clock | Precise timing | Complex, videos muted anyway | Rejected |
| Server-side sync | Consistent | Playback in browser | Rejected |
| Frame-by-frame | Precise | Poor performance | Rejected |
| MediaSource Extensions | Low-level control | Complex implementation | Rejected |
| **requestAnimationFrame** | Simple, effective | ~100ms precision | **Chosen** |

## Future Improvements

1. **Adaptive threshold**: Adjust based on network conditions
2. **Buffer monitoring**: Pause all if any video buffering
3. **Frame-accurate sync**: Use video frame timestamps
4. **Configurable master**: User selects sync master
