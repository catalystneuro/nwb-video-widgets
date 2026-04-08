"""Unit tests for DANDI widget seed extraction."""

from unittest.mock import MagicMock


def make_mock_asset(
    dandiset_id="000409",
    version_id="draft",
    identifier="abc123-uuid",
    path="sub-NYU-39/sub-NYU-39_ses-20191001_behavior+ecephys.nwb",
    api_url="https://api.dandiarchive.org/api",
    nwb_url="https://s3.amazonaws.com/dandiarchive/blobs/abc/file.nwb",
    auth_header="token mytoken123",
):
    asset = MagicMock()
    asset.dandiset_id = dandiset_id
    asset.version_id = version_id
    asset.identifier = identifier
    asset.path = path
    asset.client.api_url = api_url
    asset.client.session.headers.get.return_value = auth_header
    asset.get_content_url.return_value = nwb_url
    return asset


class TestNWBDANDIVideoPlayerSeeds:
    """Test that NWBDANDIVideoPlayer extracts seeds correctly from asset."""

    def test_seed_extraction(self):
        from nwb_video_widgets import NWBDANDIVideoPlayer

        asset = make_mock_asset()
        widget = NWBDANDIVideoPlayer(asset=asset)

        assert widget._dandiset_id == "000409"
        assert widget._version_id == "draft"
        assert widget._nwb_asset_id == "abc123-uuid"
        assert widget._nwb_asset_path == "sub-NYU-39/sub-NYU-39_ses-20191001_behavior+ecephys.nwb"
        assert widget._dandi_api_url == "https://api.dandiarchive.org/api"
        assert widget._nwb_url == "https://s3.amazonaws.com/dandiarchive/blobs/abc/file.nwb"
        assert widget._dandi_api_key == "mytoken123"
        assert widget._video_urls == {}
        assert widget._video_timing == {}
        assert widget._lindi_failed is False

    def test_no_auth_key_when_no_token(self):
        from nwb_video_widgets import NWBDANDIVideoPlayer

        asset = make_mock_asset(auth_header="")
        widget = NWBDANDIVideoPlayer(asset=asset)
        assert widget._dandi_api_key == ""

    def test_settings_open_without_grid(self):
        from nwb_video_widgets import NWBDANDIVideoPlayer

        asset = make_mock_asset()
        widget = NWBDANDIVideoPlayer(asset=asset)
        assert widget.settings_open is True
        assert widget.grid_layout == []

    def test_settings_closed_with_grid(self):
        from nwb_video_widgets import NWBDANDIVideoPlayer

        asset = make_mock_asset()
        grid = [["VideoBodyCamera"]]
        widget = NWBDANDIVideoPlayer(asset=asset, video_grid=grid)
        assert widget.settings_open is False
        assert widget.grid_layout == grid

    def test_video_labels_default_empty(self):
        from nwb_video_widgets import NWBDANDIVideoPlayer

        asset = make_mock_asset()
        widget = NWBDANDIVideoPlayer(asset=asset)
        assert widget.video_labels == {}

    def test_video_labels_passed_through(self):
        from nwb_video_widgets import NWBDANDIVideoPlayer

        asset = make_mock_asset()
        labels = {"VideoBodyCamera": "Body"}
        widget = NWBDANDIVideoPlayer(asset=asset, video_labels=labels)
        assert widget.video_labels == labels

    def test_lindi_fallback_calls_resolve(self):
        from unittest.mock import patch

        from nwb_video_widgets import NWBDANDIVideoPlayer

        asset = make_mock_asset()
        widget = NWBDANDIVideoPlayer(asset=asset)

        mock_urls = {"VideoBodyCamera": "https://s3.amazonaws.com/video.mp4"}
        mock_timing = {"VideoBodyCamera": {"start": 6.57, "end": 4030.42}}

        with patch(
            "nwb_video_widgets._utils._resolve_video_from_dandi_hdf5",
            return_value=(mock_urls, mock_timing),
        ) as mock_resolve:
            widget._lindi_failed = True

        mock_resolve.assert_called_once()
        assert widget._video_urls == mock_urls
        assert widget._video_timing == mock_timing


class TestNWBDANDIPoseEstimationWidgetSeeds:
    """Test that NWBDANDIPoseEstimationWidget extracts seeds correctly from asset."""

    def _make_mock_nwbfile(self):
        """Create a minimal mock NWBFile with one PoseEstimation container."""
        from unittest.mock import MagicMock

        nwbfile = MagicMock()
        nwbfile.objects = {}  # No PoseEstimation found -> will raise ValueError

        pose = MagicMock()
        pose.neurodata_type = "PoseEstimation"
        pose.name = "BodyCamera"

        series = MagicMock()
        series.timestamps = MagicMock()
        series.timestamps.__getitem__ = lambda s, k: 0.0 if k == 0 else 100.0
        series.timestamps.__len__ = lambda s: 1000
        pose.pose_estimation_series = {"NosePoseEstimationSeries": series}

        obj_mock = MagicMock()
        obj_mock.neurodata_type = "PoseEstimation"
        obj_mock.name = "BodyCamera"
        nwbfile.objects = {"key1": obj_mock}

        return nwbfile, pose

    def test_seed_extraction_single_file(self):
        """Test seeds for single-file case (no video_asset)."""
        from nwb_video_widgets import NWBDANDIPoseEstimationWidget

        asset = make_mock_asset()

        with (
            __import__("unittest.mock", fromlist=["patch"]).patch(
                "nwb_video_widgets.dandi_pose_widget.NWBDANDIPoseEstimationWidget._load_nwbfile_from_dandi"
            ) as mock_load,
            __import__("unittest.mock", fromlist=["patch"]).patch(
                "nwb_video_widgets.dandi_pose_widget.discover_pose_estimation_cameras"
            ) as mock_cameras,
            __import__("unittest.mock", fromlist=["patch"]).patch(
                "nwb_video_widgets.dandi_pose_widget.get_pose_estimation_info"
            ) as mock_info,
        ):
            mock_nwbfile = MagicMock()
            mock_load.return_value = mock_nwbfile
            mock_cameras.return_value = {"BodyCamera": MagicMock()}
            mock_info.return_value = {"BodyCamera": {"start": 0.0, "end": 100.0, "keypoints": ["Nose"]}}

            widget = NWBDANDIPoseEstimationWidget(asset=asset)

        assert widget._dandiset_id == "000409"
        assert widget._nwb_asset_id == "abc123-uuid"
        assert widget._dandi_api_url == "https://api.dandiarchive.org/api"
        assert widget._dandi_api_key == "mytoken123"
        # No video_asset: split-file seeds should be empty
        assert widget._video_nwb_asset_id == ""
        assert widget._video_nwb_asset_path == ""
        assert widget._video_nwb_url == ""
        assert widget._video_urls == {}
        assert widget._video_timing == {}

    def test_seed_extraction_split_file(self):
        """Test seeds for split-file case (separate video_asset)."""
        from nwb_video_widgets import NWBDANDIPoseEstimationWidget

        asset = make_mock_asset(
            identifier="pose-uuid",
            path="sub-NYU-39/sub-NYU-39_desc-processed.nwb",
        )
        video_asset = make_mock_asset(
            identifier="video-uuid",
            path="sub-NYU-39/sub-NYU-39_desc-raw.nwb",
            nwb_url="https://s3.amazonaws.com/dandiarchive/blobs/vid/file.nwb",
        )

        with (
            __import__("unittest.mock", fromlist=["patch"]).patch(
                "nwb_video_widgets.dandi_pose_widget.NWBDANDIPoseEstimationWidget._load_nwbfile_from_dandi"
            ) as mock_load,
            __import__("unittest.mock", fromlist=["patch"]).patch(
                "nwb_video_widgets.dandi_pose_widget.discover_pose_estimation_cameras"
            ) as mock_cameras,
            __import__("unittest.mock", fromlist=["patch"]).patch(
                "nwb_video_widgets.dandi_pose_widget.get_pose_estimation_info"
            ) as mock_info,
        ):
            mock_nwbfile = MagicMock()
            mock_load.return_value = mock_nwbfile
            mock_cameras.return_value = {"BodyCamera": MagicMock()}
            mock_info.return_value = {"BodyCamera": {"start": 0.0, "end": 100.0, "keypoints": ["Nose"]}}

            widget = NWBDANDIPoseEstimationWidget(asset=asset, video_asset=video_asset)

        # Main asset seeds
        assert widget._nwb_asset_id == "pose-uuid"
        assert widget._nwb_asset_path == "sub-NYU-39/sub-NYU-39_desc-processed.nwb"

        # Video asset seeds
        assert widget._video_nwb_asset_id == "video-uuid"
        assert widget._video_nwb_asset_path == "sub-NYU-39/sub-NYU-39_desc-raw.nwb"
        assert widget._video_nwb_url == "https://s3.amazonaws.com/dandiarchive/blobs/vid/file.nwb"
        assert widget._video_urls == {}
        assert widget._video_timing == {}
