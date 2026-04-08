# Neurosift Pattern Migration

## Context

Currently both DANDI widgets (`NWBDANDIVideoPlayer`, `NWBDANDIPoseEstimationWidget`) resolve video
metadata entirely in Python at widget init time: they load the NWB file via remfile/h5py, read
timestamps from it, and call the Python DANDI API to resolve video paths to S3 URLs. All of this
is sent to JavaScript via traitlets.

The goal is to move this to the Neurosift pattern: Python becomes a thin seed injector, JavaScript
fetches everything itself using HTTP range requests against the NWB file and direct calls to the
DANDI REST API.

This serves two purposes:

1. Aligns the widget architecture with Neurosift, making an eventual migration straightforward.
2. As a side-bonus, exposes `video_info` as a bidirectional traitlet so Python users can access
   resolved video URLs and session-time ranges programmatically after the widget renders.

---

## PR 1: Move to Neurosift Pattern

### What Python does after this PR

`__init__` no longer loads NWB files or calls the DANDI API. It only extracts seeds from the
asset object the user already passed:

```python
nwb_url        = asset.get_content_url(follow_redirects=1, strip_query=False)
nwb_asset_id   = asset.identifier        # UUID, needed for LINDI
nwb_asset_path = asset.path              # needed to resolve relative video paths
dandiset_id    = asset.dandiset_id
version_id     = asset.version_id
dandi_api_url  = asset.client.dandi_instance.api  # supports sandbox/staging
dandi_api_key  # extracted from asset.client session headers
```

For the pose widget split-file case (videos in a separate raw asset), the same seeds are added
prefixed with `video_`.

### Traitlet changes

Removed:
- `video_urls`
- `available_videos`
- `video_timestamps`
- `video_name_to_url` (pose widget)
- `available_videos_info` (pose widget)

Added (seeds):
- `nwb_url`
- `nwb_asset_id`
- `nwb_asset_path`
- `dandiset_id`
- `version_id`
- `dandi_api_url`
- `dandi_api_key`
- `video_nwb_url` (pose widget, split-file case)
- `video_nwb_asset_id` (pose widget, split-file case)
- `video_nwb_asset_path` (pose widget, split-file case)

Added (bidirectional, independent):
- `video_urls = {}` — starts empty, JavaScript fills with `{name: url_string}`
- `video_timing = {}` — starts empty, JavaScript fills with `{name: {start, end}}`

### Pose widget special case

The pose widget still needs to load the pose NWB file in Python because `_on_camera_selected`
reads live pynwb objects to extract pose coordinates. Only the video resolution path moves to
JavaScript. The `asset` parameter shifts to seed extraction only; the NWB file for pose data is
still loaded in Python.

### What JavaScript does

On widget mount:

1. Read seeds from model.
2. Fetch LINDI index:
   `https://lindi.neurosift.org/dandi/dandisets/{dandiset_id}/assets/{asset_id}/nwb.lindi.json`
3. Find all ImageSeries with `external_file` in the acquisition group. For each, read:
   - `external_file[0]` (relative path to the video file)
   - `timestamps[0]` and `timestamps[-1]`, or `starting_time` and `rate`
4. Construct the full dandiset path for each video:
   `parent(nwb_asset_path) / relative_path`
5. Call DANDI REST API to resolve each path to a download URL:
   `GET {dandi_api_url}/dandisets/{dandiset_id}/versions/{version_id}/assets/?path={full_path}`
   with `Authorization: token {dandi_api_key}` header if key is present.
6. Populate `video_info`:
   ```javascript
   model.set("video_info", { name: { url, start, end } });
   model.save_changes();
   ```

Raw HDF5 fallback (for when LINDI is unavailable) is deferred to a follow-up. First pass is
LINDI-only with a clear error state in the UI.

### `_utils.py` changes

Removed:
- `_get_video_urls_from_dandi`
- `_get_dandi_video_info`

The local widget utilities (`get_video_info`, `get_video_timestamps`, `discover_video_series`)
are unaffected — they are still used by the local (non-DANDI) widgets.

### Breaking changes

The `nwbfile` and `video_nwbfile` parameters are removed (or accepted with a deprecation warning
and silently ignored). Under the new pattern there is no NWB loading in Python for the video
widget, so pre-loading an NWBFile has no effect.

### Implementation notes (resolved during PR 1)

- `asset.identifier` is the correct UUID for LINDI.
- DANDI REST API `GET /assets/?path={path}` returns `{results: [{asset_id, path, size}]}`.
  The download URL is `{dandi_api_url}/assets/{asset_id}/download/` which redirects to S3.
- anywidget does fire `change:video_info` when JavaScript sets the value. A `videoInfoResolved`
  boolean guard prevents re-entry.
- `asset.client.api_url` gives the API base URL (e.g. `https://api.dandiarchive.org/api`).
- The `nwbfile` and `video_nwbfile` parameters are deprecated (accepted but ignored) with a
  `DeprecationWarning` pointing to removal in v0.1.8.

### Traitlet design: separate `video_urls` and `video_timing`

Video metadata is split into two independent traitlets rather than a single combined dict:

- `video_urls = {}` for resolved S3 URLs (`{name: url_string}`)
- `video_timing = {}` for session-time ranges (`{name: {start, end}}`)

URLs come from the DANDI REST API, timing comes from LINDI NWB metadata. They are independent
data with no inherent reason to couple them. Keeping them separate means each syncs
independently, Python methods can compose them however they want, and a future
`video_timestamps` traitlet (full per-frame arrays, PR 3) fits naturally as a third
independent piece.

Full per-frame timestamp arrays are deliberately excluded from both traitlets. For a long
recording (100K+ frames), the timestamps array alone is ~800 KB of float64 values. Serializing
that back to Python on every sync would be expensive and unnecessary: Python only needs
start/end for the public API, and JavaScript already has the timestamps in memory from LINDI
for its own seeking logic. If a Python user needs the full array (for alignment with neural
data, for example), that will be a separate on-demand traitlet in PR 3, synced back only when
explicitly requested.

Both traitlets are bidirectional by necessity. JavaScript must write them (Python cannot, since
Python no longer fetches the data). Python must read them (for the public API in PR 2). The
`videoInfoResolved` boolean guard in JavaScript prevents re-triggering resolution when values
sync back from Python's acknowledgment.

---

## PR 2: Expose Video Metadata to Python Users

Because `video_urls` and `video_timing` are bidirectional traitlets, once JavaScript populates
them the values are synced back to the Python kernel automatically. `widget.video_urls` and
`widget.video_timing` become available without any additional Python fetching.

The only problem is timing: the user must display the widget and wait for JavaScript to finish
before reading the values. This PR adds a coroutine method to handle that:

```python
widget = NWBDANDIPoseEstimationWidget(asset=processed_asset, video_asset=raw_asset)
display(widget)
info = await widget.wait_for_video_urls(timeout=30)
# {'VideoBodyCamera': 'https://...s3...'}
```

### Implementation

```python
async def wait_for_video_urls(self, timeout: float = 30.0) -> dict:
    if self.video_urls:
        return self.video_urls

    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def on_change(change):
        if change["new"] and not future.done():
            future.set_result(change["new"])

    self.observe(on_change, names=["video_urls"])
    try:
        return await asyncio.wait_for(future, timeout=timeout)
    finally:
        self.unobserve(on_change, names=["video_urls"])
```

Added to both `NWBDANDIVideoPlayer` and `NWBDANDIPoseEstimationWidget`.

### Traitlet schemas (stable public API from this PR)

`video_urls`:
```
{"<ImageSeries name>": str}  # pre-signed S3 URL
```

`video_timing`:
```
{
  "<ImageSeries name>": {
    "start": float,  # session start time in seconds
    "end":   float   # session end time in seconds, or equal to start if unknown
  }
}
```

Keys are ImageSeries names as they appear in `nwbfile.acquisition`. These schemas are
considered stable from PR 2 onwards.

### Relation to GitHub issue #33

This addresses the request for a public API to retrieve video URLs and session-time ranges
without duplicating the logic in downstream code. The data comes from JavaScript (Neurosift
pattern), not from a separate Python fetching layer.
