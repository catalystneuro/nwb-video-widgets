# v0.1.6 (Upcoming)

## Removals, Deprecations and changes

## Bug Fixes

* Fixed embargoed dandiset support by using `asset.client` instead of creating a new unauthenticated `DandiAPIClient()`, and by preserving pre-signed S3 query parameters (`strip_query=False`). [PR #18](https://github.com/catalystneuro/nwb-video-widgets/pull/18)

## Features

## Improvements

# v0.1.5 (2026-02-03)

## Removals, Deprecations and Changes

## Bug Fixes

* Fixed pose widget seek bar not spanning full video duration. The seek bar max value was not updated when camera data loaded asynchronously, limiting seeking to only the first 100 frames instead of all frames. [PR #8](https://github.com/catalystneuro/nwb-video-widgets/pull/8)
* Fixed keypoint visibility toggles not updating the pose overlay display. [PR #8](https://github.com/catalystneuro/nwb-video-widgets/pull/8)

## Features

## Improvements

* Updated CI infrastructure: added pre-commit, ruff formatting (line-length 120), reusable workflows, changelog detection, and file change assessment. [PR #3](https://github.com/catalystneuro/nwb-video-widgets/pull/3)

# v0.1.3 (2026-02-02)

## Removals, Deprecations and Changes

## Bug Fixes

* Fixed DANDI widget path construction on Windows. On Windows, `pathlib.Path` produces backslashes when converting to string, but DANDI asset paths always use forward slashes. Switched to `PurePosixPath` for DANDI path construction. [PR #2](https://github.com/catalystneuro/nwb-video-widgets/pull/2)

## Features

## Improvements
