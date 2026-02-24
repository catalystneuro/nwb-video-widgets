"""Unit tests for NWBLocalPoseEstimationWidget."""

import pytest

from nwb_video_widgets import NWBLocalPoseEstimationWidget
from nwb_video_widgets._utils import (
    discover_pose_estimation_cameras,
    get_pose_estimation_info,
)


class TestPoseEstimationDiscovery:
    """Tests for discovering pose estimation data from NWB files."""

    def test_discover_single_camera(self, nwbfile_with_single_camera_pose):
        """Test discovering pose estimation from a single camera."""
        cameras = discover_pose_estimation_cameras(nwbfile_with_single_camera_pose)

        assert len(cameras) == 1
        assert "LeftCamera" in cameras

        # Check that the camera has pose estimation series
        camera_pose = cameras["LeftCamera"]
        assert len(camera_pose.pose_estimation_series) == 3  # Nose, LeftEar, RightEar

    def test_discover_multiple_cameras(self, nwbfile_with_multiple_cameras_pose):
        """Test discovering pose estimation from multiple cameras."""
        cameras = discover_pose_estimation_cameras(nwbfile_with_multiple_cameras_pose)

        assert len(cameras) == 3
        assert "LeftCamera" in cameras
        assert "RightCamera" in cameras
        assert "BodyCamera" in cameras

        # Check that each camera has the correct number of keypoints
        for camera_name, camera_pose in cameras.items():
            assert len(camera_pose.pose_estimation_series) == 5  # 5 keypoints

    def test_discover_cameras_with_videos(self, nwbfile_with_videos_and_pose):
        """Test discovering pose estimation when videos are also present."""
        cameras = discover_pose_estimation_cameras(nwbfile_with_videos_and_pose)

        assert len(cameras) == 3
        assert "LeftCamera" in cameras
        assert "RightCamera" in cameras
        assert "BodyCamera" in cameras


class TestCameraInfoExtraction:
    """Tests for extracting camera metadata."""

    def test_camera_info_single(self, nwbfile_with_single_camera_pose):
        """Test extracting info for a single camera."""
        info = get_pose_estimation_info(nwbfile_with_single_camera_pose)

        assert len(info) == 1
        assert "LeftCamera" in info

        camera_info = info["LeftCamera"]
        assert "start" in camera_info
        assert "end" in camera_info
        assert "frames" in camera_info
        assert "keypoints" in camera_info

        assert camera_info["frames"] == 30
        assert len(camera_info["keypoints"]) == 3
        assert "Nose" in camera_info["keypoints"]
        assert "LeftEar" in camera_info["keypoints"]
        assert "RightEar" in camera_info["keypoints"]

    def test_camera_info_multiple(self, nwbfile_with_multiple_cameras_pose):
        """Test extracting info for multiple cameras."""
        info = get_pose_estimation_info(nwbfile_with_multiple_cameras_pose)

        assert len(info) == 3

        for camera_name in ["LeftCamera", "RightCamera", "BodyCamera"]:
            assert camera_name in info
            camera_info = info[camera_name]
            assert camera_info["frames"] == 30
            assert len(camera_info["keypoints"]) == 5


class TestWidgetCreation:
    """Tests for widget instantiation."""

    def test_create_widget_single_camera(self, nwbfile_with_single_camera_pose):
        """Test creating widget with single camera."""
        widget = NWBLocalPoseEstimationWidget(nwbfile_with_single_camera_pose)

        assert len(widget.available_cameras) == 1
        assert "LeftCamera" in widget.available_cameras
        assert widget.settings_open is True
        assert widget.selected_camera == ""  # No camera selected by default

    def test_create_widget_multiple_cameras(self, nwbfile_with_multiple_cameras_pose):
        """Test creating widget with multiple cameras."""
        widget = NWBLocalPoseEstimationWidget(nwbfile_with_multiple_cameras_pose)

        assert len(widget.available_cameras) == 3
        assert "LeftCamera" in widget.available_cameras
        assert "RightCamera" in widget.available_cameras
        assert "BodyCamera" in widget.available_cameras
        assert widget.settings_open is True

    def test_create_widget_with_videos(self, nwbfile_with_videos_and_pose):
        """Test creating widget when videos are present."""
        widget = NWBLocalPoseEstimationWidget(nwbfile_with_videos_and_pose)

        assert len(widget.available_cameras) == 3
        assert len(widget.available_videos) == 3
        assert "VideoLeftCamera" in widget.available_videos
        assert "VideoBodyCamera" in widget.available_videos
        assert "VideoRightCamera" in widget.available_videos

    def test_default_camera_selection(self, nwbfile_with_single_camera_pose):
        """Test selecting a default camera."""
        widget = NWBLocalPoseEstimationWidget(
            nwbfile_with_single_camera_pose, default_camera="LeftCamera"
        )

        assert widget.selected_camera == "LeftCamera"

    def test_invalid_default_camera(self, nwbfile_with_single_camera_pose):
        """Test that invalid default camera falls back to no selection."""
        widget = NWBLocalPoseEstimationWidget(
            nwbfile_with_single_camera_pose, default_camera="NonexistentCamera"
        )

        assert widget.selected_camera == ""


class TestLazyLoading:
    """Tests for lazy loading of pose data."""

    def test_initial_data_empty(self, nwbfile_with_multiple_cameras_pose):
        """Test that pose data is not loaded initially."""
        widget = NWBLocalPoseEstimationWidget(nwbfile_with_multiple_cameras_pose)

        assert len(widget.all_camera_data) == 0
        assert widget.loading is False

    def test_data_loads_on_selection(self, nwbfile_with_single_camera_pose):
        """Test that pose data loads when camera is selected."""
        widget = NWBLocalPoseEstimationWidget(nwbfile_with_single_camera_pose)

        # Initially empty
        assert len(widget.all_camera_data) == 0

        # Select camera
        widget.selected_camera = "LeftCamera"

        # Data should be loaded now
        assert "LeftCamera" in widget.all_camera_data
        camera_data = widget.all_camera_data["LeftCamera"]

        assert "keypoint_metadata" in camera_data
        assert "pose_coordinates" in camera_data
        assert "timestamps" in camera_data

        # Check keypoints
        assert "Nose" in camera_data["keypoint_metadata"]
        assert "LeftEar" in camera_data["keypoint_metadata"]
        assert "RightEar" in camera_data["keypoint_metadata"]

        # Check coordinates structure
        assert len(camera_data["pose_coordinates"]["Nose"]) == 30
        assert len(camera_data["timestamps"]) == 30


class TestKeypointColors:
    """Tests for keypoint color assignment."""

    def test_default_colormap(self, nwbfile_with_single_camera_pose):
        """Test that default colormap is applied."""
        widget = NWBLocalPoseEstimationWidget(nwbfile_with_single_camera_pose)

        widget.selected_camera = "LeftCamera"
        camera_data = widget.all_camera_data["LeftCamera"]

        # Each keypoint should have a color
        for keypoint_name, metadata in camera_data["keypoint_metadata"].items():
            assert "color" in metadata
            assert metadata["color"].startswith("#")  # Hex color

    def test_custom_colors(self, nwbfile_with_single_camera_pose):
        """Test custom color assignment."""
        custom_colors = {
            "Nose": "#FF0000",
            "LeftEar": "#00FF00",
            "RightEar": "#0000FF",
        }

        widget = NWBLocalPoseEstimationWidget(
            nwbfile_with_single_camera_pose, keypoint_colors=custom_colors
        )

        widget.selected_camera = "LeftCamera"
        camera_data = widget.all_camera_data["LeftCamera"]

        # Check custom colors are applied
        assert camera_data["keypoint_metadata"]["Nose"]["color"] == "#FF0000"
        assert camera_data["keypoint_metadata"]["LeftEar"]["color"] == "#00FF00"
        assert camera_data["keypoint_metadata"]["RightEar"]["color"] == "#0000FF"

    def test_different_colormap(self, nwbfile_with_single_camera_pose):
        """Test using a different colormap."""
        widget = NWBLocalPoseEstimationWidget(
            nwbfile_with_single_camera_pose, keypoint_colors="Set1"
        )

        widget.selected_camera = "LeftCamera"
        camera_data = widget.all_camera_data["LeftCamera"]

        # Verify colors are assigned (just check they exist)
        for keypoint_name in ["Nose", "LeftEar", "RightEar"]:
            assert "color" in camera_data["keypoint_metadata"][keypoint_name]


class TestErrorHandling:
    """Tests for error handling."""

    def test_raises_for_missing_pose_module(self, nwbfile_with_single_video):
        """Test that error is raised when pose_estimation module is missing."""
        with pytest.raises(ValueError, match="pose_estimation processing module"):
            NWBLocalPoseEstimationWidget(nwbfile_with_single_video)

    def test_raises_for_in_memory_nwbfile(self):
        """Test that error is raised for NWB files not loaded from disk."""
        from ndx_pose import PoseEstimation, PoseEstimationSeries
        from pynwb import ProcessingModule
        from pynwb.testing.mock.file import mock_NWBFile

        nwbfile = mock_NWBFile()

        # Add pose estimation to in-memory file
        pose_module = ProcessingModule(
            name="pose_estimation",
            description="Test pose estimation",
        )
        nwbfile.add_processing_module(pose_module)

        # Create a simple pose estimation
        series = PoseEstimationSeries(
            name="NosePoseEstimationSeries",
            data=[[100.0, 200.0], [101.0, 201.0]],
            reference_frame="top-left",
            timestamps=[0.0, 0.1],
        )
        pose_estimation = PoseEstimation(
            name="TestCamera",
            pose_estimation_series=[series],
        )
        pose_module.add(pose_estimation)

        with pytest.raises(ValueError, match="loaded from disk"):
            NWBLocalPoseEstimationWidget(nwbfile)


class TestVideoNameMapping:
    """Tests for video name to URL mapping."""

    def test_video_urls_extracted(self, nwbfile_with_videos_and_pose):
        """Test that video URLs are extracted correctly."""
        widget = NWBLocalPoseEstimationWidget(nwbfile_with_videos_and_pose)

        assert len(widget.video_name_to_url) == 3

        # Check that URLs are HTTP addresses
        for video_name, url in widget.video_name_to_url.items():
            assert url.startswith("http://127.0.0.1:")
            assert url.endswith(".mp4")

    def test_camera_to_video_initially_empty(self, nwbfile_with_videos_and_pose):
        """Test that camera-to-video mapping starts empty."""
        widget = NWBLocalPoseEstimationWidget(nwbfile_with_videos_and_pose)

        # Should start empty - users need to explicitly map cameras to videos
        assert len(widget.camera_to_video) == 0
