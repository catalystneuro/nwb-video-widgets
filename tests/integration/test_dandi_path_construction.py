"""Integration test for DANDI path construction on Windows.

Regression test for: https://github.com/CodyCBakerPhD/dandi-open-data-tutorial/pull/5

On Windows, pathlib.Path produces backslashes when converting to string,
but DANDI asset paths always use forward slashes. This test verifies that
video asset paths are constructed correctly on all platforms.
"""

import pytest

from nwb_video_widgets import NWBDANDIPoseEstimationWidget


@pytest.mark.integration
def test_dandi_video_path_construction():
    """Test that DANDI video paths are constructed with forward slashes on any OS."""
    from dandi.dandiapi import DandiAPIClient

    client = DandiAPIClient()
    dandiset = client.get_dandiset("000409", "draft")

    session_eid = "64e3fb86-928c-4079-865c-b364205b502e"
    session_assets = [asset for asset in dandiset.get_assets() if session_eid in asset.path]
    raw_asset = next((asset for asset in session_assets if "desc-raw" in asset.path), None)
    processed_asset = next((asset for asset in session_assets if "desc-processed" in asset.path), None)

    # This would fail on Windows before the fix with:
    # NotFoundError: No asset at path 'sub-NYU-46\\sub-NYU-46_ses-...\\video.mp4'
    widget = NWBDANDIPoseEstimationWidget(
        client=client,
        asset=processed_asset,
        video_asset=raw_asset,
    )

    # Verify video URLs were resolved (paths constructed correctly)
    assert len(widget.video_name_to_url) > 0
    for url in widget.video_name_to_url.values():
        assert url.startswith("https://")
