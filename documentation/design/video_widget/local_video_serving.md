# Local Video Serving

## Problem

Browsers enforce strict security policies that prevent web content from accessing local files via `file://` URLs. When the `NWBLocalVideoPlayer` widget runs in a Jupyter notebook, the JavaScript code executes in the browser context and cannot load videos using `file://` paths.

Attempting to use `file://` URLs results in videos that never load, with the browser silently blocking the requests.

## Solution

Serve local video files through a lightweight HTTP server running on localhost.

### Architecture

```
+-------------------+       HTTP Request        +------------------+
|   Browser/Widget  |  ---------------------->  |  Local HTTP      |
|   (JavaScript)    |  http://127.0.0.1:PORT/   |  Server (Python) |
|                   |  <----------------------  |                  |
+-------------------+       Video Data          +------------------+
                                                        |
                                                        v
                                                +------------------+
                                                |  Video Files     |
                                                |  (on disk)       |
                                                +------------------+
```

## Implementation

### Server Setup (`_utils.py`)

1. **Port Selection**: Find a free port dynamically using `socket.bind(("", 0))`

2. **Server Registry**: Global dictionary `_video_servers` to:
   - Avoid duplicate servers for the same directory
   - Return existing port if server already running

3. **Daemon Thread**: Server runs in background thread so it:
   - Doesn't block the notebook
   - Terminates when Python exits

```python
def start_video_server(directory: Path) -> int:
    dir_key = str(directory.resolve())

    # Reuse existing server
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
```

### Range Request Support

Video streaming requires HTTP Range requests (RFC 7233). Without this, browsers cannot:
- Seek within videos
- Buffer efficiently
- Display video duration

The `_RangeRequestHandler` class:

1. **Parses Range header**: Extract byte range from `Range: bytes=START-END`
2. **Returns partial content**: HTTP 206 with `Content-Range` header
3. **Supports seeking**: Random access within video files

```python
def send_head(self):
    range_header = self.headers.get("Range")

    if range_header:
        # Parse "bytes=0-1023"
        start, end = parse_range(range_header)

        self.send_response(206)  # Partial Content
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        # ... serve partial file
```

### CORS Headers

Cross-Origin Resource Sharing headers allow browser access:

```python
self.send_header("Access-Control-Allow-Origin", "*")
self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS, HEAD")
self.send_header("Access-Control-Allow-Headers", "Range")
self.send_header("Access-Control-Expose-Headers", "Content-Range, Content-Length")
```

### Error Handling

The `handle()` method catches connection errors silently:

```python
def handle(self):
    try:
        super().handle()
    except (ConnectionResetError, BrokenPipeError):
        pass  # Normal during video seeking
```

These errors occur when:
- Browser cancels a request during seeking
- Browser closes connection after receiving enough data
- User navigates away

### URL Generation

`get_video_urls_from_local()` method:

1. Reads NWB file location from `nwbfile.read_io.source`
2. Resolves external video paths relative to NWB file
3. Groups videos by directory
4. Starts one server per unique directory
5. Returns HTTP URLs: `http://127.0.0.1:{port}/{filename}`

```python
# Example output
{
    "VideoLeftCamera": "http://127.0.0.1:45123/video_left.mp4",
    "VideoBodyCamera": "http://127.0.0.1:45123/video_body.mp4",
    "VideoRightCamera": "http://127.0.0.1:45123/video_right.mp4"
}
```

## Limitations

1. **Localhost only**: Server binds to `127.0.0.1`, not accessible from other machines
2. **No authentication**: Anyone on localhost can access videos while server runs
3. **Daemon lifetime**: Server stops when Python process exits

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Base64 encoding | Simple, no server | Memory issues with large videos | Rejected |
| Jupyter file server | Built-in | Files must be in Jupyter root | Rejected |
| Symbolic links | No server needed | Cross-platform issues | Rejected |
| **HTTP server** | Range support, CORS | Port management | **Chosen** |
