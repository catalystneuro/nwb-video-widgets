# v0.1.4 (Upcoming)

## Removals, Deprecations and Changes

## Bug Fixes

## Features

## Improvements

* Updated CI infrastructure: added pre-commit, ruff formatting (line-length 120), reusable workflows, changelog detection, and file change assessment. [PR #3](https://github.com/catalystneuro/nwb-video-widgets/pull/3)

# v0.1.3 (2025-02-2)

## Removals, Deprecations and Changes

## Bug Fixes

* Fixed DANDI widget path construction on Windows. On Windows, `pathlib.Path` produces backslashes when converting to string, but DANDI asset paths always use forward slashes. Switched to `PurePosixPath` for DANDI path construction. [PR #2](https://github.com/catalystneuro/nwb-video-widgets/pull/2)

## Features

## Improvements
