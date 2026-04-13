# Duplicate container names across processing modules

## Problem

`discover_pose_estimation_cameras()` searches `nwbfile.objects.values()`, which spans all processing modules. When two modules contain a PoseEstimation container with the same name, the keys collide. Dandiset 001425 (BraiDyn-BC) triggers this:

```
processing/behavior/body_video_keypoints      (PoseEstimation)
processing/behavior/eye_video_keypoints       (PoseEstimation)
processing/behavior/face_video_keypoints      (PoseEstimation)
processing/downsampled/body_video_keypoints   (PoseEstimation)
processing/downsampled/eye_video_keypoints    (PoseEstimation)
processing/downsampled/face_video_keypoints   (PoseEstimation)
```

## Solution

Both `discover_pose_estimation_cameras()` and `discover_video_series()` use the same two-pass approach:

1. First pass iterates `nwbfile.objects.values()`, groups matching objects by `obj.name`, and records which names appear more than once.
2. Second pass builds the result dict. Duplicated names are prefixed with their parent container name (`behavior/body_video_keypoints`, `downsampled/body_video_keypoints`). Unique names keep their short key, so datasets without duplicates are unaffected.

Downstream consumers iterate over whatever keys the discovery functions return, so they required no changes.

## Videos

`discover_video_series()` previously searched only within `nwbfile.acquisition`, which is a single NWB namespace where item names are unique by construction. A survey of DANDI conducted in April 2026 confirmed that every `ImageSeries.external_file` found across dandisets was in `/acquisition`. There is no real-world case of duplicate video names today.

We expanded the search to `nwbfile.objects` with the same disambiguation logic anyway. The cost is negligible (two dict passes), and it ensures videos stored outside acquisition (e.g. in processing modules) are discovered correctly if that pattern ever appears in the wild.

## Test dataset

```python
from dandi.dandiapi import DandiAPIClient
client = DandiAPIClient()
ds = client.get_dandiset("001425")
asset = ds.get_asset_by_path(
    "sub-VG1-GC#51/sub-VG1-GC#51_ses-2023-06-29-task-day11_widefield+behavior.nwb"
)
```
