# Video Widget Design Documentation

## Overview

The video widget provides interactive video playback for NWB (Neurodata Without Borders) files within Jupyter notebooks. It supports both local files and DANDI-hosted remote files, with synchronized multi-camera playback.

## Architecture

### File Structure

```
src/nwb_video_widgets/
├── video_widget.py       # Base widget for pre-configured video URLs
├── local_video_widget.py # Local NWB file support with HTTP server
├── dandi_video_widget.py # DANDI-hosted NWB streaming
├── video_widget.js       # Frontend rendering and controls
├── video_widget.css      # Styling
└── _utils.py             # Shared utilities (server, discovery)
```

### Widget Classes

| Class | Purpose | Data Source |
|-------|---------|-------------|
| `NWBFileVideoPlayer` | Base class with grid layout | Pre-computed S3 URLs |
| `NWBLocalVideoPlayer` | Local file playback | Local filesystem via HTTP |
| `NWBDANDIVideoPlayer` | Remote streaming | DANDI archive via S3 |

### Technology Stack

- **Framework**: anywidget (Jupyter widget protocol)
- **Video Rendering**: HTML5 `<video>` elements
- **HTTP Server**: Python `http.server` with Range support
- **Remote Access**: remfile for S3 streaming
- **NWB I/O**: pynwb with h5py

## Data Flow

### Local Files

```
NWB File (disk)
    │
    ▼
discover_video_series()
    │ Extracts ImageSeries with external_file references
    ▼
Resolve paths relative to NWB location
    │
    ▼
start_video_server()
    │ HTTP server per unique directory
    │ Supports Range requests for seeking
    ▼
JavaScript receives localhost URLs
    │ e.g., http://127.0.0.1:8000/video.mp4
    ▼
HTML5 <video> streams from localhost
```

### DANDI/S3 Files

```
DANDI API Client
    │
    ▼
Fetch dandiset from asset.dandiset_id
    │
    ▼
discover_video_series()
    │ Extracts paths from ImageSeries
    ▼
dandiset.get_asset_by_path()
    │ Returns video asset metadata
    ▼
asset.get_content_url()
    │ Returns S3 URL with redirect support
    ▼
JavaScript receives S3 URLs
    │
    ▼
HTML5 <video> streams directly from S3
```

### Timestamp Mapping

NWB files store session-relative timestamps, not video-relative time:

```
ImageSeries.timestamps or (starting_time + rate)
    │
    ▼
extract_video_timestamps()
    │ Reads full timestamp array per video
    ▼
Passed to JS as {video_name: [t0, t1, ...]}
    │
    ▼
Session time = NWB_timestamp[0] + video.currentTime
    │
    ▼
Display: "MM:SS.ms" format
```

## Performance Considerations

### HTTP Server (Local Files)

The `_RangeRequestHandler` class provides efficient video seeking:

```python
class _RangeRequestHandler(SimpleHTTPRequestHandler):
    """
    - Parses Range header (e.g., "bytes=0-1023")
    - Returns 206 Partial Content with Content-Range
    - Enables browser seeking without full download
    - CORS headers for cross-origin access
    """
```

**Key optimizations:**
- Single server instance per directory (cached in `_video_servers` dict)
- Daemon threads avoid blocking notebook
- Connection reuse via HTTP/1.1 keep-alive

### Multi-Video Synchronization

The JavaScript uses a master-slave model for synchronized playback:

```javascript
function syncVideos() {
    // Master video (first in list) controls timing
    const masterTime = masterVideo.currentTime;

    // Correct slave drift > 100ms
    for (const slave of slaveVideos) {
        if (Math.abs(slave.currentTime - masterTime) > 0.1) {
            slave.currentTime = masterTime;
        }
    }

    requestAnimationFrame(syncVideos);
}
```

**Trade-offs:**
- Simple implementation, works for 2-4 cameras
- 100ms threshold prevents jitter from minor drift
- Seeking disabled during sync to prevent feedback loops

### Memory Usage

| Resource | Strategy |
|----------|----------|
| Video frames | Browser-managed (HTML5 video) |
| Timestamps | Loaded once at init, ~8 bytes/frame |
| Video URLs | String references only |

**Estimated overhead:** ~1MB for 100K frames across all cameras

## UI/UX Design

### Grid Layout System

Three layout modes computed dynamically:

```javascript
function calculateGridLayout(n, mode) {
    switch (mode) {
        case 'row':    return { cols: n, rows: 1 };
        case 'column': return { cols: 1, rows: n };
        case 'grid':   return { cols: Math.ceil(Math.sqrt(n)),
                                rows: Math.ceil(n / cols) };
    }
}
```

### Settings Panel

Collapsible panel containing:
1. **Video Selection** - Checkboxes with time range display
2. **Layout Mode** - Radio buttons (row/column/grid)
3. **Compatibility Warnings** - Highlights mismatched time ranges

### Controls Bar

```
[Play/Pause] [Settings] [═══════Seekbar═══════] [0:00.0 / 1:23.4]
```

- Play/Pause: Toggle with icon swap
- Settings: Opens configuration panel
- Seekbar: Frame-accurate seeking
- Time: Session timestamps (not video-relative)

## Assumptions

1. **Video format**: Browser-compatible codecs (H.264, WebM)
2. **NWB structure**: Videos stored as `ImageSeries` with `external_file`
3. **Timestamp alignment**: All cameras have aligned session timestamps
4. **Network access**: For DANDI, requires internet connectivity
5. **File permissions**: Local files must be readable by Python process

## Trade-offs

### Lazy vs Eager Loading

**Decision**: Lazy loading (videos not pre-buffered)

| Approach | Pros | Cons |
|----------|------|------|
| **Lazy (chosen)** | Fast initial load, low memory | First play has buffering delay |
| Eager | Instant playback | Slow init, high memory |

**Rationale**: Most users select 1-2 videos; pre-buffering all wastes resources.

### Local HTTP Server vs File URLs

**Decision**: Local HTTP server

| Approach | Pros | Cons |
|----------|------|------|
| **HTTP (chosen)** | Range seeking, CORS support | Port management complexity |
| file:// URLs | Simple | No Range support, CORS blocked |

**Rationale**: HTTP Range requests are essential for seeking in large videos.

### Synchronized vs Independent Playback

**Decision**: Synchronized by default

| Approach | Pros | Cons |
|----------|------|------|
| **Synced (chosen)** | Consistent multi-camera view | Limited to similar-length videos |
| Independent | Flexible | Confusing for aligned data |

**Rationale**: NWB sessions typically have synchronized recordings.

## Error Handling

| Scenario | Handling |
|----------|----------|
| Missing video file | Silently skipped, warning in selection |
| Invalid NWB | ValueError with descriptive message |
| Network timeout (DANDI) | Browser retry mechanism |
| Server port conflict | Auto-increment to find free port |
| Browser closes connection | Catch `BrokenPipeError`, log and continue |

## Extensibility

### Adding New Video Sources

1. Subclass `NWBFileVideoPlayer`
2. Override `get_video_urls()` to return URL dict
3. Override `get_video_timestamps()` if timestamp format differs

### Custom Layout Modes

Modify `calculateGridLayout()` in `video_widget.js` to add new arrangements.

### Additional Controls

Add new HTML elements to controls bar and wire up event listeners in `render()`.

## Known Limitations

1. **Maximum videos**: Practical limit ~6 (browser memory/bandwidth)
2. **Codec support**: Depends on browser capabilities
3. **Sync precision**: ~100ms accuracy (browser limitation)
4. **Seek performance**: Large files may have initial delay
5. **Mobile support**: Not optimized for touch interfaces
