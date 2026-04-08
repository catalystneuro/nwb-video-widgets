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
