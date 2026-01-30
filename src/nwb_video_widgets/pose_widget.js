/**
 * Pose estimation video player widget.
 * Overlays DeepLabCut keypoints on streaming video with camera selection.
 *
 * Data format (from Python via JSON):
 * - all_camera_data: {camera_name: {keypoint_metadata, pose_coordinates, timestamps}}
 *   All camera data is loaded upfront for instant switching
 * - pose_coordinates: {keypoint_name: [[x, y], null, [x, y], ...]}
 *   Each keypoint has an array of coordinates per frame, null for missing data
 * - timestamps: [t0, t1, t2, ...] array of frame timestamps
 */

const DISPLAY_WIDTH = 640;
const DISPLAY_HEIGHT = 512;

/**
 * Format seconds as MM:SS.ms string for session time display.
 * @param {number} seconds - Time in seconds
 * @returns {string} Formatted time string
 */
function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 10);
  return mins + ":" + secs.toString().padStart(2, "0") + "." + ms;
}

/**
 * Binary search for frame index closest to target time.
 * @param {number[]} timestamps - Sorted array of timestamps
 * @param {number} targetTime - Time to find
 * @returns {number} Index of closest timestamp
 */
function findFrameIndex(timestamps, targetTime) {
  if (!timestamps || timestamps.length === 0) return 0;
  let left = 0;
  let right = timestamps.length - 1;
  while (left < right) {
    const mid = Math.floor((left + right) / 2);
    if (timestamps[mid] < targetTime) {
      left = mid + 1;
    } else {
      right = mid;
    }
  }
  return left;
}

/**
 * Create an SVG icon element.
 * @param {"play" | "pause" | "settings"} type - Icon type
 * @returns {SVGElement}
 */
function createIcon(type) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "currentColor");

  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  if (type === "play") {
    path.setAttribute("d", "M8 5v14l11-7z");
  } else if (type === "pause") {
    path.setAttribute("d", "M6 19h4V5H6v14zm8-14v14h4V5h-4z");
  } else if (type === "settings") {
    path.setAttribute(
      "d",
      "M19.14 12.94c.04-.31.06-.63.06-.94 0-.31-.02-.63-.06-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"
    );
  }
  svg.appendChild(path);
  return svg;
}

/**
 * Render the pose video player widget.
 *
 * @param {Object} context - Provided by anywidget
 * @param {Object} context.model - Proxy to Python traitlets
 * @param {HTMLElement} context.el - The DOM element where the widget should render
 */
function render({ model, el }) {
  // Root wrapper with scoped class
  const wrapper = document.createElement("div");
  wrapper.classList.add("pose-widget");

  // Control bar
  const controls = document.createElement("div");
  controls.classList.add("pose-widget__controls");

  const playPauseBtn = document.createElement("button");
  playPauseBtn.classList.add("pose-widget__button");
  playPauseBtn.appendChild(createIcon("play"));

  const settingsBtn = document.createElement("button");
  settingsBtn.classList.add("pose-widget__button", "pose-widget__settings-btn");
  settingsBtn.appendChild(createIcon("settings"));
  settingsBtn.title = "Settings";

  const seekBar = document.createElement("input");
  seekBar.type = "range";
  seekBar.min = 0;
  seekBar.max = 100;
  seekBar.value = 0;
  seekBar.classList.add("pose-widget__seekbar");

  const timeLabel = document.createElement("span");
  timeLabel.classList.add("pose-widget__time-label");
  timeLabel.textContent = "0:00.0 / 0:00.0";

  controls.appendChild(playPauseBtn);
  controls.appendChild(settingsBtn);
  controls.appendChild(seekBar);
  controls.appendChild(timeLabel);

  // Settings panel (collapsible)
  const settingsPanel = document.createElement("div");
  settingsPanel.classList.add("pose-widget__settings-panel");

  const settingsPanelHeader = document.createElement("div");
  settingsPanelHeader.classList.add("pose-widget__settings-header");

  const settingsTitle = document.createElement("span");
  settingsTitle.classList.add("pose-widget__settings-title");
  settingsTitle.textContent = "Settings";

  const closeBtn = document.createElement("button");
  closeBtn.classList.add("pose-widget__close-btn");
  closeBtn.textContent = "Close";
  closeBtn.addEventListener("click", () => {
    model.set("settings_open", false);
    model.save_changes();
  });

  settingsPanelHeader.appendChild(settingsTitle);
  settingsPanelHeader.appendChild(closeBtn);
  settingsPanel.appendChild(settingsPanelHeader);

  // Camera selection section
  const cameraSection = document.createElement("div");
  cameraSection.classList.add("pose-widget__camera-section");

  const cameraTitle = document.createElement("span");
  cameraTitle.classList.add("pose-widget__section-title");
  cameraTitle.textContent = "Camera Selection";
  cameraSection.appendChild(cameraTitle);

  const cameraHint = document.createElement("p");
  cameraHint.classList.add("pose-widget__section-hint");
  cameraHint.textContent = "Select a camera to display pose estimation overlay.";
  cameraSection.appendChild(cameraHint);

  const cameraList = document.createElement("div");
  cameraList.classList.add("pose-widget__camera-list");
  cameraSection.appendChild(cameraList);

  settingsPanel.appendChild(cameraSection);

  // Keypoint visibility section
  const keypointSection = document.createElement("div");
  keypointSection.classList.add("pose-widget__keypoint-section");

  const keypointTitle = document.createElement("span");
  keypointTitle.classList.add("pose-widget__section-title");
  keypointTitle.textContent = "Keypoint Visibility";
  keypointSection.appendChild(keypointTitle);

  const keypointTogglesWrapper = document.createElement("div");
  keypointTogglesWrapper.classList.add("pose-widget__keypoint-toggles-wrapper");

  const utilityRow = document.createElement("div");
  utilityRow.classList.add("pose-widget__keypoint-toggles");

  const keypointRow = document.createElement("div");
  keypointRow.classList.add("pose-widget__keypoint-toggles");

  keypointTogglesWrapper.appendChild(utilityRow);
  keypointTogglesWrapper.appendChild(keypointRow);
  keypointSection.appendChild(keypointTogglesWrapper);

  settingsPanel.appendChild(keypointSection);

  // Display options section
  const displaySection = document.createElement("div");
  displaySection.classList.add("pose-widget__display-section");

  const displayTitle = document.createElement("span");
  displayTitle.classList.add("pose-widget__section-title");
  displayTitle.textContent = "Display Options";
  displaySection.appendChild(displayTitle);

  const labelToggle = document.createElement("label");
  labelToggle.classList.add("pose-widget__label-toggle");
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = model.get("show_labels");
  labelToggle.appendChild(checkbox);
  labelToggle.appendChild(document.createTextNode(" Show keypoint labels"));
  displaySection.appendChild(labelToggle);

  settingsPanel.appendChild(displaySection);

  // Debug info
  const debugDiv = document.createElement("div");
  debugDiv.classList.add("pose-widget__debug");

  // Video container
  const videoContainer = document.createElement("div");
  videoContainer.classList.add("pose-widget__video-container");

  const video = document.createElement("video");
  video.classList.add("pose-widget__video");
  video.muted = true;
  video.playsInline = true;

  const canvas = document.createElement("canvas");
  canvas.width = DISPLAY_WIDTH;
  canvas.height = DISPLAY_HEIGHT;
  canvas.classList.add("pose-widget__canvas");

  // Empty state message
  const emptyMsg = document.createElement("div");
  emptyMsg.classList.add("pose-widget__empty-msg");
  emptyMsg.textContent = "Select a camera above to display video with pose overlay.";

  videoContainer.appendChild(video);
  videoContainer.appendChild(canvas);
  videoContainer.appendChild(emptyMsg);

  let isPlaying = false;
  let animationId = null;
  let visibleKeypoints = { ...model.get("visible_keypoints") };

  /**
   * Get current camera's data from all_camera_data.
   */
  function getCurrentCameraData() {
    const camera = model.get("selected_camera");
    const allData = model.get("all_camera_data");
    return allData[camera] || null;
  }

  /**
   * Update debug info display.
   */
  function updateDebug(frameIdx, extra = "") {
    const camera = model.get("selected_camera");
    const data = getCurrentCameraData();
    const nFrames = data?.timestamps?.length || 0;
    if (camera) {
      debugDiv.textContent =
        camera +
        " | Frame: " +
        frameIdx +
        "/" +
        nFrames +
        " | Video: " +
        video.videoWidth +
        "x" +
        video.videoHeight +
        " | " +
        extra;
    } else {
      debugDiv.textContent = "No camera selected";
    }
  }

  /**
   * Update time label with NWB session timestamps.
   */
  function updateTimeLabel(frameIdx) {
    const data = getCurrentCameraData();
    const timestamps = data?.timestamps;
    if (!timestamps || timestamps.length === 0) {
      timeLabel.textContent = "0:00.0 / 0:00.0";
      return;
    }
    const currentTime = timestamps[frameIdx] || timestamps[0];
    const endTime = timestamps[timestamps.length - 1];
    timeLabel.textContent = formatTime(currentTime) + " / " + formatTime(endTime);
  }

  /**
   * Update the settings panel with camera list and visibility.
   */
  function updateSettingsPanel() {
    const cameras = model.get("available_cameras") || [];
    const camerasInfo = model.get("available_cameras_info") || {};
    const selectedCamera = model.get("selected_camera");
    const settingsOpen = model.get("settings_open");

    // Toggle panel visibility
    if (settingsOpen) {
      settingsPanel.classList.add("pose-widget__settings-panel--open");
    } else {
      settingsPanel.classList.remove("pose-widget__settings-panel--open");
    }

    // Clear and rebuild camera list
    cameraList.innerHTML = "";

    if (cameras.length === 0) {
      const emptyText = document.createElement("p");
      emptyText.classList.add("pose-widget__empty-text");
      emptyText.textContent = "No cameras available.";
      cameraList.appendChild(emptyText);
      return;
    }

    cameras.forEach((cam) => {
      const info = camerasInfo[cam] || {};
      const isSelected = cam === selectedCamera;

      const cameraItem = document.createElement("div");
      cameraItem.classList.add("pose-widget__camera-item");
      if (isSelected) {
        cameraItem.classList.add("pose-widget__camera-item--selected");
      }

      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "camera-select";
      radio.id = "camera-" + cam;
      radio.value = cam;
      radio.checked = isSelected;
      radio.addEventListener("change", () => {
        if (radio.checked) {
          model.set("selected_camera", cam);
          model.save_changes();
        }
      });

      const label = document.createElement("label");
      label.htmlFor = "camera-" + cam;
      label.classList.add("pose-widget__camera-item-label");
      label.textContent = cam;

      const timeRange = document.createElement("span");
      timeRange.classList.add("pose-widget__camera-item-time");
      if (info.start !== undefined && info.end !== undefined) {
        timeRange.textContent = formatTime(info.start) + " - " + formatTime(info.end);
      }

      const keypoints = document.createElement("span");
      keypoints.classList.add("pose-widget__camera-item-keypoints");
      if (info.keypoints) {
        keypoints.textContent = info.keypoints.length + " keypoints";
      }

      cameraItem.appendChild(radio);
      cameraItem.appendChild(label);
      cameraItem.appendChild(timeRange);
      cameraItem.appendChild(keypoints);

      cameraList.appendChild(cameraItem);
    });
  }

  function updateToggleStyles() {
    const buttons = keypointRow.querySelectorAll("button[data-keypoint]");
    const data = getCurrentCameraData();
    const metadata = data?.keypoint_metadata || {};
    buttons.forEach((btn) => {
      const name = btn.dataset.keypoint;
      const isVisible = visibleKeypoints[name] !== false;
      const color = metadata[name]?.color || "#999";

      if (isVisible) {
        btn.classList.add("pose-widget__keypoint-toggle--active");
        btn.style.backgroundColor = color;
        btn.style.borderColor = color;
      } else {
        btn.classList.remove("pose-widget__keypoint-toggle--active");
        btn.style.backgroundColor = "";
        btn.style.borderColor = color;
      }
    });
  }

  function createKeypointToggles() {
    utilityRow.innerHTML = "";
    keypointRow.innerHTML = "";
    const data = getCurrentCameraData();
    const metadata = data?.keypoint_metadata || {};
    if (Object.keys(metadata).length === 0) return;

    // All button
    const allBtn = document.createElement("button");
    allBtn.textContent = "All";
    allBtn.classList.add(
      "pose-widget__keypoint-toggle",
      "pose-widget__keypoint-toggle--utility"
    );
    allBtn.addEventListener("click", () => {
      for (const name of Object.keys(metadata)) visibleKeypoints[name] = true;
      model.set("visible_keypoints", { ...visibleKeypoints });
      model.save_changes();
      updateToggleStyles();
      drawPose();
    });

    // None button
    const noneBtn = document.createElement("button");
    noneBtn.textContent = "None";
    noneBtn.classList.add(
      "pose-widget__keypoint-toggle",
      "pose-widget__keypoint-toggle--utility"
    );
    noneBtn.addEventListener("click", () => {
      for (const name of Object.keys(metadata)) visibleKeypoints[name] = false;
      model.set("visible_keypoints", { ...visibleKeypoints });
      model.save_changes();
      updateToggleStyles();
      drawPose();
    });

    utilityRow.appendChild(allBtn);
    utilityRow.appendChild(noneBtn);

    // Individual keypoint buttons
    for (const [name, kp] of Object.entries(metadata)) {
      const btn = document.createElement("button");
      btn.textContent = name;
      btn.dataset.keypoint = name;
      btn.classList.add("pose-widget__keypoint-toggle");
      btn.style.borderColor = kp.color;
      btn.addEventListener("click", () => {
        visibleKeypoints[name] = !visibleKeypoints[name];
        model.set("visible_keypoints", { ...visibleKeypoints });
        model.save_changes();
        updateToggleStyles();
        drawPose();
      });
      keypointRow.appendChild(btn);
    }
    updateToggleStyles();
  }

  /**
   * Get current frame index based on video time.
   */
  function getFrameIndex() {
    const data = getCurrentCameraData();
    const timestamps = data?.timestamps;
    if (!timestamps || timestamps.length === 0) return 0;
    return findFrameIndex(timestamps, timestamps[0] + video.currentTime);
  }

  /**
   * Draw pose keypoints on canvas overlay.
   */
  function drawPose() {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const selectedCamera = model.get("selected_camera");
    if (!selectedCamera) {
      updateDebug(0, "No camera selected");
      return;
    }

    const data = getCurrentCameraData();
    if (!data) {
      updateDebug(0, "No pose data");
      return;
    }

    const metadata = data.keypoint_metadata;
    const coordinates = data.pose_coordinates;
    const timestamps = data.timestamps;
    const showLabels = model.get("show_labels");

    if (!coordinates || !timestamps || timestamps.length === 0) {
      updateDebug(0, "No pose data");
      return;
    }

    const frameIdx = getFrameIndex();

    if (!video.videoWidth || !video.videoHeight) {
      updateDebug(frameIdx, "Loading video...");
      return;
    }

    const scaleX = DISPLAY_WIDTH / video.videoWidth;
    const scaleY = DISPLAY_HEIGHT / video.videoHeight;

    let drawnCount = 0;

    for (const [name, coords] of Object.entries(coordinates)) {
      if (visibleKeypoints[name] === false) continue;

      const coord = coords[frameIdx];
      if (!coord) continue; // null means no data for this frame

      const x = coord[0] * scaleX;
      const y = coord[1] * scaleY;
      const kp = metadata[name];

      ctx.beginPath();
      ctx.arc(x, y, 5, 0, 2 * Math.PI);
      ctx.fillStyle = kp?.color || "#fff";
      ctx.fill();
      ctx.strokeStyle = "#000";
      ctx.lineWidth = 1.5;
      ctx.stroke();
      drawnCount++;

      if (showLabels && kp) {
        ctx.font = "bold 10px sans-serif";
        ctx.fillStyle = "#fff";
        ctx.strokeStyle = "#000";
        ctx.lineWidth = 2;
        ctx.strokeText(kp.label, x + 6, y + 3);
        ctx.fillText(kp.label, x + 6, y + 3);
      }
    }
    updateDebug(frameIdx, "Drew " + drawnCount + " keypoints");
    updateTimeLabel(frameIdx);
  }

  function animate() {
    drawPose();
    if (isPlaying) animationId = requestAnimationFrame(animate);
  }

  function loadVideo() {
    const camera = model.get("selected_camera");
    if (!camera) {
      video.src = "";
      videoContainer.classList.add("pose-widget__video-container--empty");
      return;
    }
    videoContainer.classList.remove("pose-widget__video-container--empty");
    const videoUrl = model.get("camera_to_video")[camera];
    if (videoUrl && video.src !== videoUrl) {
      video.src = videoUrl;
    }
  }

  function updatePlayPauseIcon(playing) {
    playPauseBtn.innerHTML = "";
    playPauseBtn.appendChild(createIcon(playing ? "pause" : "play"));
  }

  /**
   * Switch to a new camera - updates UI immediately since all data is preloaded.
   */
  function switchCamera() {
    // Update seek bar max for new camera
    const data = getCurrentCameraData();
    seekBar.max = data?.timestamps?.length - 1 || 100;

    // Recreate keypoint toggles for new camera
    createKeypointToggles();

    // Load new video URL
    loadVideo();

    // Draw immediately (data is already available)
    drawPose();
  }

  // Initialize
  loadVideo();
  createKeypointToggles();
  updateSettingsPanel();

  // Set initial seek bar max
  const initialData = getCurrentCameraData();
  if (initialData?.timestamps) {
    seekBar.max = initialData.timestamps.length - 1;
  }

  video.addEventListener("loadedmetadata", drawPose);
  video.addEventListener("seeked", drawPose);
  video.addEventListener("timeupdate", drawPose);

  // Listen for camera changes
  model.on("change:selected_camera", () => {
    if (isPlaying) {
      video.pause();
      updatePlayPauseIcon(false);
      if (animationId) cancelAnimationFrame(animationId);
      isPlaying = false;
    }
    switchCamera();
    updateSettingsPanel();
  });

  model.on("change:settings_open", updateSettingsPanel);
  model.on("change:available_cameras", updateSettingsPanel);
  model.on("change:available_cameras_info", updateSettingsPanel);

  playPauseBtn.addEventListener("click", () => {
    const selectedCamera = model.get("selected_camera");
    if (!selectedCamera) {
      // Open settings if no camera selected
      model.set("settings_open", true);
      model.save_changes();
      return;
    }
    if (isPlaying) {
      video.pause();
      if (animationId) cancelAnimationFrame(animationId);
    } else {
      video.play();
      animate();
    }
    isPlaying = !isPlaying;
    updatePlayPauseIcon(isPlaying);
  });

  seekBar.addEventListener("input", () => {
    const frameIdx = parseInt(seekBar.value);
    const data = getCurrentCameraData();
    const timestamps = data?.timestamps;
    if (timestamps && timestamps.length > 0) {
      video.currentTime = timestamps[frameIdx] - timestamps[0];
    }
  });

  checkbox.addEventListener("change", () => {
    model.set("show_labels", checkbox.checked);
    model.save_changes();
    drawPose();
  });

  settingsBtn.addEventListener("click", () => {
    const isOpen = model.get("settings_open");
    model.set("settings_open", !isOpen);
    model.save_changes();
  });

  updateDebug(0, "Ready");
  updateTimeLabel(0);

  wrapper.appendChild(settingsPanel);
  wrapper.appendChild(videoContainer);
  wrapper.appendChild(debugDiv);
  wrapper.appendChild(controls);
  el.appendChild(wrapper);

  // Cleanup function
  return () => {
    if (animationId) {
      cancelAnimationFrame(animationId);
    }
  };
}

export default { render };
