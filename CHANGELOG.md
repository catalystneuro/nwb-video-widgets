# v0.1.7 (Upcoming)

## Removals, Deprecations and changes

* DANDI widgets no longer load NWB files in Python for video metadata. Video metadata (URLs and session-time ranges) is now fetched in JavaScript via LINDI and the DANDI REST API, with a Python fallback using targeted h5py reads when LINDI is unavailable. The `nwbfile` parameter on `NWBDANDIVideoPlayer` and the `video_nwbfile` parameter on `NWBDANDIPoseEstimationWidget` are deprecated and no longer have any effect. They will be removed in v0.1.8. [PR #35](https://github.com/catalystneuro/nwb-video-widgets/pull/35)
* Removed private helpers `_get_video_urls_from_dandi` and `_get_dandi_video_info` from `_utils.py`. [PR #35](https://github.com/catalystneuro/nwb-video-widgets/pull/35)
* Unified internal traitlet interface across all widget types. Local and DANDI widgets now use the same internal traitlets for video URLs and timing. [PR #35](https://github.com/catalystneuro/nwb-video-widgets/pull/35)

## Bug Fixes

* Fixed `get_dandi_video_info()` returning empty results for NWB files created on Windows. The `external_file` paths in these files use backslashes (e.g. dandiset 001771), which failed to match DANDI's forward-slash asset paths. [PR #38](https://github.com/catalystneuro/nwb-video-widgets/pull/38)

## Features

* Added `get_dandi_video_info(asset)` public function that returns video URLs and session-time ranges for a DANDI NWB asset. No widget or display required. [PR #36](https://github.com/catalystneuro/nwb-video-widgets/pull/36)
* Added `from_url()` classmethod to `NWBDANDIVideoPlayer` and `NWBDANDIPoseEstimationWidget` for creating widgets from a DANDI URL string. Also added `url` parameter to `get_dandi_video_info()`. [PR #39](https://github.com/catalystneuro/nwb-video-widgets/pull/39)

## Improvements

* DANDI pose widget now loads keypoint coordinates and timestamps directly from S3 via LINDI byte-range requests in JavaScript, bypassing the Python-to-browser JSON serialization path. For large recordings this eliminates ~50 MB of websocket transfer per camera switch. Falls back to the Python path when LINDI data is compressed or unavailable.

# v0.1.6 (2026-04-06)

## Removals, Deprecations and changes

## Bug Fixes

* Fixed embargoed dandiset support by using `asset.client` instead of creating a new unauthenticated `DandiAPIClient()`, and by preserving pre-signed S3 query parameters (`strip_query=False`). [PR #18](https://github.com/catalystneuro/nwb-video-widgets/pull/18)

## Features

* Added local_example_notebook.ipynb and appropriate mock nwb file functions to demonstrate usage of the widgets in a local Jupyter environment without requiring DANDI access. [PR #21](https://github.com/catalystneuro/nwb-video-widgets/pull/21)
* Added codec validation for local video and pose widgets. Videos using codecs not supported by browsers (e.g. MJPEG, mp4v, FFV1) now raise a clear `ValueError` with the detected codec and an ffmpeg command to re-encode to H.264. Detection is pure Python with no new dependencies. [PR #24](https://github.com/catalystneuro/nwb-video-widgets/pull/24)

## Improvements

* Replaced OpenCV-generated synthetic test videos with committed stub videos from DANDI (H.264, MJPEG, mp4v) at 160x120 resolution. [PR #24](https://github.com/catalystneuro/nwb-video-widgets/pull/24)
* Added comprehensive unit tests for PoseEstimation widgets covering discovery, widget creation, lazy loading, keypoint colors, error handling, and video mapping. [PR #16](https://github.com/catalystneuro/nwb-video-widgets/pull/16)
* Added support for Pose Estimation Objects anywhere in the NWB file [PR #17](https://github.com/catalystneuro/nwb-video-widgets/pull/17)
* Updated readme to describe supported video codecs [PR #25](https://github.com/catalystneuro/nwb-video-widgets/pull/25)
* Added support for starting time and rate [PR #27](https://github.com/catalystneuro/nwb-video-widgets/pull/27)
* Optimized init-time metadata loading to use indexed timestamp access instead of loading full arrays, improving widget creation speed for DANDI streaming with large datasets [PR #32](https://github.com/catalystneuro/nwb-video-widgets/pull/32)
* Vectorized pose coordinate conversion from row-by-row Python loop to numpy bulk operations, reducing processing time for large datasets [PR #32](https://github.com/catalystneuro/nwb-video-widgets/pull/32)

# v0.1.5 (2026-02-03)

## Removals, Deprecations and Changes

## Bug Fixes

* Fixed pose widget seek bar not spanning full video duration. The seek bar max value was not updated when camera data loaded asynchronously, limiting seeking to only the first 100 frames instead of all frames. [PR #8](https://github.com/catalystneuro/nwb-video-widgets/pull/8)
* Fixed keypoint visibility toggles not updating the pose overlay display. [PR #8](https://github.com/catalystneuro/nwb-video-widgets/pull/8)

## Features

## Improvements

* Updated CI infrastructure: added pre-commit, ruff formatting (line-length 120), reusable workflows, changelog detection, and file change assessment. [PR #3](https://github.com/catalystneuro/nwb-video-widgets/pull/3)
* Add support for python 3.14 in CI. [PR #6](https://github.com/catalystneuro/nwb-video-widgets/pull/6)

# v0.1.3 (2026-02-02)

## Removals, Deprecations and Changes

## Bug Fixes

* Fixed DANDI widget path construction on Windows. On Windows, `pathlib.Path` produces backslashes when converting to string, but DANDI asset paths always use forward slashes. Switched to `PurePosixPath` for DANDI path construction. [PR #2](https://github.com/catalystneuro/nwb-video-widgets/pull/2)

## Features

## Improvements
