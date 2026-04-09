"""Integration test for DANDI seed extraction.

Regression test for: https://github.com/CodyCBakerPhD/dandi-open-data-tutorial/pull/5

On Windows, pathlib.Path produces backslashes when converting to string,
but DANDI asset paths always use forward slashes. This test verifies that
video asset paths are constructed correctly on all platforms.
"""

import pytest

from nwb_video_widgets import NWBDANDIPoseEstimationWidget


@pytest.mark.integration
def test_dandi_seed_extraction():
    """Test that DANDI seed traitlets are populated from asset objects."""
    from dandi.dandiapi import DandiAPIClient

    client = DandiAPIClient()
    dandiset = client.get_dandiset("000409", "draft")

    session_eid = "64e3fb86-928c-4079-865c-b364205b502e"
    session_assets = [asset for asset in dandiset.get_assets() if session_eid in asset.path]
    raw_asset = next((asset for asset in session_assets if "desc-raw" in asset.path), None)
    processed_asset = next((asset for asset in session_assets if "desc-processed" in asset.path), None)

    widget = NWBDANDIPoseEstimationWidget(
        asset=processed_asset,
        video_asset=raw_asset,
    )

    # Verify main asset seeds are populated
    assert widget._dandiset_id == "000409"
    assert widget._nwb_asset_id  # non-empty UUID
    assert "sub-NYU-46" in widget._nwb_asset_path
    assert widget._dandi_api_url == "https://api.dandiarchive.org/api"
    assert widget._nwb_url.startswith("https://")

    # Verify video asset seeds are populated (split-file case)
    assert widget._video_nwb_asset_id  # non-empty UUID
    assert "sub-NYU-46" in widget._video_nwb_asset_path
    assert widget._video_nwb_url.startswith("https://")

    # _video_urls/_video_timing start empty - JavaScript hasn't run yet
    assert widget._video_urls == {}
    assert widget._video_timing == {}


@pytest.mark.integration
def test_hdf5_fallback_resolves_videos():
    """Test that the h5py fallback resolves video URLs from a real DANDI asset.

    Regression test for: paths containing '+' (e.g. ecephys+image) must be
    URL-encoded when querying the DANDI REST API.
    """
    from dandi.dandiapi import DandiAPIClient

    from nwb_video_widgets._utils import _resolve_video_from_dandi_hdf5

    client = DandiAPIClient()
    dandiset = client.get_dandiset("000409", "draft")

    session_eid = "64e3fb86-928c-4079-865c-b364205b502e"
    session_assets = [asset for asset in dandiset.get_assets() if session_eid in asset.path]
    raw_asset = next((asset for asset in session_assets if "desc-raw" in asset.path), None)

    s3_url = raw_asset.get_content_url(follow_redirects=1, strip_query=False)

    video_urls, video_timing = _resolve_video_from_dandi_hdf5(
        nwb_s3_url=s3_url,
        asset_path=raw_asset.path,
        dandiset_id=raw_asset.dandiset_id,
        version_id=raw_asset.version_id,
        dandi_api_url=raw_asset.client.api_url,
    )

    assert len(video_urls) == 3
    for name in ["VideoBodyCamera", "VideoLeftCamera", "VideoRightCamera"]:
        assert name in video_urls
        assert video_urls[name].startswith("https://")
        assert name in video_timing
        assert video_timing[name]["start"] > 0
        assert video_timing[name]["end"] > video_timing[name]["start"]


@pytest.mark.integration
def test_get_dandi_video_info():
    """Test the public get_dandi_video_info() function against real DANDI data."""
    from dandi.dandiapi import DandiAPIClient

    from nwb_video_widgets import get_dandi_video_info

    client = DandiAPIClient()
    dandiset = client.get_dandiset("000409", "0.260309.1324")

    session_eid = "64e3fb86-928c-4079-865c-b364205b502e"
    session_assets = [asset for asset in dandiset.get_assets() if session_eid in asset.path]
    raw_asset = next((asset for asset in session_assets if "desc-raw" in asset.path), None)

    info = get_dandi_video_info(raw_asset)

    # URLs contain pre-signed S3 query parameters that change on every request,
    # so we only compare timing.
    timing_only = {name: {"start": v["start"], "end": v["end"]} for name, v in info.items()}
    expected_timing = {
        "VideoBodyCamera": {"start": 6.577342200006577, "end": 4030.4229174040306},
        "VideoLeftCamera": {"start": 6.532580010006533, "end": 4030.4061524140307},
        "VideoRightCamera": {"start": 6.5000832600065, "end": 4030.4301166840305},
    }
    assert timing_only == expected_timing


@pytest.mark.integration
def test_get_dandi_video_info_from_url():
    """Test get_dandi_video_info() with a DANDI URL instead of an asset object."""
    from nwb_video_widgets import get_dandi_video_info

    url = (
        "https://api.dandiarchive.org/api/dandisets/000409/versions/0.260309.1324/assets/"
        "?path=sub-NYU-46/sub-NYU-46_ses-64e3fb86-928c-4079-865c-b364205b502e_desc-raw_ecephys.nwb"
    )
    info = get_dandi_video_info(url=url)

    expected_timing = {
        "VideoBodyCamera": {"start": 6.577342200006577, "end": 4030.4229174040306},
        "VideoLeftCamera": {"start": 6.532580010006533, "end": 4030.4061524140307},
        "VideoRightCamera": {"start": 6.5000832600065, "end": 4030.4301166840305},
    }
    timing_only = {name: {"start": v["start"], "end": v["end"]} for name, v in info.items()}
    assert timing_only == expected_timing


@pytest.mark.integration
def test_get_dandi_video_info_windows_backslash_paths():
    """Regression: NWB files created on Windows have backslashes in external_file paths.

    Dandiset 001771 was authored on Windows, so external_file entries contain
    backslashes (e.g. "ses-1_image\\abc123.mp4"). These must be normalized to
    forward slashes when querying the DANDI API.
    """
    from dandi.dandiapi import DandiAPIClient

    from nwb_video_widgets import get_dandi_video_info

    client = DandiAPIClient()
    dandiset = client.get_dandiset("001771", "draft")

    session_eid = "2026-02-12-1"
    video_asset = next(a for a in dandiset.get_assets() if session_eid in a.path and a.path.endswith("_image.nwb"))

    info = get_dandi_video_info(video_asset)

    assert len(info) == 6
    for name, entry in info.items():
        assert entry["url"].startswith("https://")
        assert entry["start"] >= 0
        assert entry["end"] > entry["start"]
