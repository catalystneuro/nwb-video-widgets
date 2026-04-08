/**
 * Multi-camera video player widget for synchronized playback.
 * Displays videos in a configurable grid layout with unified controls.
 *
 * JavaScript fetches video metadata from DANDI via LINDI and the DANDI REST
 * API, then writes back to the `video_urls` and `video_timing` traitlets.
 *
 * @typedef {Object.<string, string>} VideoUrls - Mapping of video names to S3 URLs
 * @typedef {Object.<string, {start: number, end: number}>} VideoTiming - Mapping of video names to time ranges
 * @typedef {string[][]} GridLayout - 2D array defining video grid (rows x cols)
 */

/**
 * Format seconds as MM:SS.ms string for session time display.
 * @param {number} seconds
 * @returns {string}
 */
function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 10);
  return mins + ":" + secs.toString().padStart(2, "0") + "." + ms;
}

/**
 * Create an SVG icon element.
 * @param {"play" | "pause" | "settings" | "warning"} type - Icon type
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
  } else if (type === "warning") {
    path.setAttribute(
      "d",
      "M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"
    );
  }
  svg.appendChild(path);
  return svg;
}

/**
 * Check if two videos are compatible for synchronized playback.
 * Videos are compatible if their start times are within tolerance and they have overlapping time ranges.
 * @param {Object} infoA - Video info {start, end}
 * @param {Object} infoB - Video info {start, end}
 * @param {number} tolerance - Maximum allowed difference in start times (default 1.0 second)
 * @returns {boolean}
 */
function areCompatible(infoA, infoB, tolerance = 1.0) {
  const startDiff = Math.abs(infoA.start - infoB.start);
  if (startDiff > tolerance) {
    return false;
  }
  // Check if there's overlap
  const overlapStart = Math.max(infoA.start, infoB.start);
  const overlapEnd = Math.min(infoA.end, infoB.end);
  return overlapEnd > overlapStart;
}

/**
 * Calculate grid dimensions based on layout mode and number of videos.
 * @param {string} layoutMode - "row", "column", or "grid"
 * @param {number} count - Number of videos
 * @returns {{rows: number, cols: number}}
 */
function calculateGridDimensions(layoutMode, count) {
  if (count === 0) return { rows: 0, cols: 0 };

  if (layoutMode === "row") {
    return { rows: 1, cols: count };
  } else if (layoutMode === "column") {
    return { rows: count, cols: 1 };
  } else {
    // Grid mode: square-ish layout
    const cols = Math.ceil(Math.sqrt(count));
    const rows = Math.ceil(count / cols);
    return { rows, cols };
  }
}

// ============ LINDI HELPERS ============

/**
 * Decode a LINDI ref value to a string.
 * Handles plain strings and base64-encoded strings.
 * Returns null for range references (arrays).
 * @param {string | Array} ref
 * @returns {string | null}
 */
function lindiRefToString(ref) {
  if (typeof ref !== "string") return null;
  if (ref.startsWith("base64:")) {
    return atob(ref.slice(7));
  }
  return ref;
}

/**
 * Decode a LINDI ref value to a Uint8Array.
 * Handles plain strings (treated as UTF-8) and base64-encoded binary.
 * Returns null for range references (arrays).
 * @param {string | Array} ref
 * @returns {Uint8Array | null}
 */
function lindiRefToBytes(ref) {
  if (typeof ref !== "string") return null;
  if (ref.startsWith("base64:")) {
    const binary = atob(ref.slice(7));
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }
  return new TextEncoder().encode(ref);
}

/**
 * Read the first string from a json2-encoded variable-length string chunk.
 * LINDI stores object (|O) arrays using json2 filter: [val1, ..., "|O", [shape]].
 * @param {string | Array} ref - LINDI ref value
 * @returns {string | null}
 */
function readLindiJson2String(ref) {
  const text = lindiRefToString(ref);
  if (!text) return null;
  try {
    const json = JSON.parse(text);
    if (Array.isArray(json) && json.length >= 2) {
      return String(json[0]);
    }
  } catch {
    // If not json2 format, try using the raw text directly
  }
  return text.trim();
}

/**
 * Read a float64 scalar from a LINDI inline chunk (base64-encoded 8 bytes).
 * @param {string | Array} ref - LINDI ref value
 * @returns {number | null}
 */
function readLindiFloat64(ref) {
  const bytes = lindiRefToBytes(ref);
  if (!bytes || bytes.length < 8) return null;
  return new DataView(bytes.buffer, bytes.byteOffset).getFloat64(0, true);
}

/**
 * Read the first and last float64 from a timestamps dataset in LINDI refs.
 *
 * Handles two cases:
 * 1. Inline (small array < 1000 frames): stored as base64-encoded float64 bytes.
 * 2. Range reference (large array): byte-range requests to the S3 URL.
 *
 * @param {Object} refs - The lindi.refs object
 * @param {string} seriesPath - e.g. "acquisition/VideoBodyCamera"
 * @returns {Promise<{start: number, end: number} | null>}
 */
async function readLindiTimestamps(refs, seriesPath) {
  const zarrayRef = refs[seriesPath + "/timestamps/.zarray"];
  if (!zarrayRef) return null;

  const zarrayText = lindiRefToString(zarrayRef);
  if (!zarrayText) return null;

  let zarray;
  try {
    zarray = JSON.parse(zarrayText);
  } catch {
    return null;
  }

  const shape = zarray.shape;
  if (!shape || shape.length === 0) return null;
  const nFrames = shape[0];
  if (nFrames === 0) return null;

  const chunkRef = refs[seriesPath + "/timestamps/0"];
  if (!chunkRef) return null;

  const hasCompressor = !!zarray.compressor;
  const hasFilters = zarray.filters && zarray.filters.length > 0;

  if (typeof chunkRef === "string") {
    // Inline data: base64-encoded raw float64 bytes (no compressor for inline arrays)
    const bytes = lindiRefToBytes(chunkRef);
    if (!bytes || bytes.byteLength < 8) return null;
    const floats = new Float64Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 8);
    return { start: floats[0], end: floats[floats.length - 1] };
  }

  if (!Array.isArray(chunkRef) || chunkRef.length !== 3) return null;
  if (hasCompressor || hasFilters) return null; // Can't do targeted byte reads with compression

  // Range reference: [url, byteOffset, byteLength]
  const [url, offset] = chunkRef;
  const chunks = zarray.chunks || [nFrames];
  const chunkSize = chunks[0];
  const nChunks = Math.ceil(nFrames / chunkSize);

  // Read first float64
  const startResp = await fetch(url, {
    headers: { Range: `bytes=${offset}-${offset + 7}` },
  });
  if (!startResp.ok) return null;
  const startBuf = await startResp.arrayBuffer();
  const start = new DataView(startBuf).getFloat64(0, true);

  let end;
  if (nChunks === 1) {
    // Single chunk: last element is at byte (nFrames-1)*8 within the chunk
    const lastByteOffset = offset + (nFrames - 1) * 8;
    const endResp = await fetch(url, {
      headers: { Range: `bytes=${lastByteOffset}-${lastByteOffset + 7}` },
    });
    if (!endResp.ok) return { start, end: start };
    const endBuf = await endResp.arrayBuffer();
    end = new DataView(endBuf).getFloat64(0, true);
  } else {
    // Multi-chunk: find the last chunk
    const lastChunkIdx = nChunks - 1;
    const lastChunkRef = refs[seriesPath + "/timestamps/" + lastChunkIdx];
    if (!lastChunkRef || !Array.isArray(lastChunkRef)) return { start, end: start };
    const [urlLast, offsetLast] = lastChunkRef;
    const framesInLastChunk = nFrames - lastChunkIdx * chunkSize;
    const lastElemByteOffset = offsetLast + (framesInLastChunk - 1) * 8;
    const endResp = await fetch(urlLast, {
      headers: { Range: `bytes=${lastElemByteOffset}-${lastElemByteOffset + 7}` },
    });
    if (!endResp.ok) return { start, end: start };
    const endBuf = await endResp.arrayBuffer();
    end = new DataView(endBuf).getFloat64(0, true);
  }

  return { start, end };
}

/**
 * Read session timing for an ImageSeries from LINDI refs.
 * Tries timestamps first; falls back to starting_time.
 * @param {Object} refs - The lindi.refs object
 * @param {string} seriesPath - e.g. "acquisition/VideoBodyCamera"
 * @returns {Promise<{start: number, end: number}>}
 */
async function readLindiSeriesTiming(refs, seriesPath) {
  // Try timestamps first
  const timing = await readLindiTimestamps(refs, seriesPath);
  if (timing !== null) return timing;

  // Fall back to starting_time (scalar float64, always inline)
  const startingTimeRef = refs[seriesPath + "/starting_time/0"];
  if (startingTimeRef) {
    const start = readLindiFloat64(startingTimeRef);
    if (start !== null) return { start, end: start };
  }

  return { start: 0, end: 0 };
}

// ============ VIDEO INFO RESOLUTION ============

/**
 * Resolve video URLs and timing from DANDI via LINDI + DANDI REST API.
 * Sets model.video_urls and model.video_timing once complete.
 * @param {Object} model - anywidget model proxy
 * @param {Object} model - anywidget model proxy
 */
async function resolveVideoInfo(model) {
  const dandisetId = model.get("_dandiset_id");
  const assetId = model.get("_nwb_asset_id");
  const assetPath = model.get("_nwb_asset_path");
  const dandiApiUrl = model.get("_dandi_api_url");
  const versionId = model.get("_version_id");
  const apiKey = model.get("_dandi_api_key");

  if (!dandisetId || !assetId) {
    return;
  }

  const lindiEnv = dandiApiUrl.includes("sandbox") ? "dandi-staging" : "dandi";
  const lindiUrl =
    "https://lindi.neurosift.org/" +
    lindiEnv +
    "/dandisets/" +
    dandisetId +
    "/assets/" +
    assetId +
    "/nwb.lindi.json";

  let lindi;
  try {
    const resp = await fetch(lindiUrl);
    if (!resp.ok) throw new Error("LINDI not available (HTTP " + resp.status + ")");
    lindi = await resp.json();
  } catch (err) {
    // LINDI unavailable, signal Python to fall back to targeted h5py reads
    model.set("_lindi_failed", true);
    model.save_changes();
    return;
  }

  const refs = lindi.refs;
  const videoUrls = {};
  const videoTiming = {};

  // Find all ImageSeries in the acquisition group
  const acquiPrefix = "acquisition/";
  const seriesNames = new Set();
  for (const key of Object.keys(refs)) {
    if (key.startsWith(acquiPrefix) && key.endsWith("/.zattrs")) {
      const parts = key.split("/");
      if (parts.length === 3) {
        seriesNames.add(parts[1]);
      }
    }
  }

  const authHeaders = apiKey ? { Authorization: "token " + apiKey } : {};
  const nwbParent = assetPath.split("/").slice(0, -1).join("/");

  for (const name of seriesNames) {
    // Check neurodata_type from .zattrs
    const zattrsRef = refs[acquiPrefix + name + "/.zattrs"];
    if (!zattrsRef) continue;

    let attrs;
    try {
      attrs = JSON.parse(lindiRefToString(zattrsRef) || "{}");
    } catch {
      continue;
    }
    if (attrs.neurodata_type !== "ImageSeries") continue;

    // Read external_file[0] - the relative path to the video file
    const extFileRef = refs[acquiPrefix + name + "/external_file/0"];
    if (!extFileRef) continue;

    const relativePath = readLindiJson2String(extFileRef);
    if (!relativePath) continue;

    // Build full DANDI path: parent(nwb_asset_path) / relative_path
    const cleanRelative = relativePath.replace(/^[./]+/, "");
    const fullPath = nwbParent ? nwbParent + "/" + cleanRelative : cleanRelative;

    // Read timing from timestamps or starting_time
    const { start, end } = await readLindiSeriesTiming(
      refs,
      acquiPrefix + name
    );

    // Resolve video asset via DANDI REST API
    let downloadUrl;
    try {
      const searchResp = await fetch(
        dandiApiUrl +
          "/dandisets/" +
          dandisetId +
          "/versions/" +
          versionId +
          "/assets/?path=" +
          encodeURIComponent(fullPath),
        { headers: authHeaders }
      );
      if (!searchResp.ok) continue;
      const searchData = await searchResp.json();
      if (!searchData.results || searchData.results.length === 0) continue;
      const videoAssetId = searchData.results[0].asset_id;
      downloadUrl =
        dandiApiUrl + "/assets/" + videoAssetId + "/download/";
    } catch {
      continue;
    }

    // Follow redirect from download URL to get the actual S3 URL.
    // Use AbortController to abort after headers are received (HEAD is CORS-blocked on S3).
    let s3Url = downloadUrl;
    try {
      const controller = new AbortController();
      const redirectResp = await fetch(downloadUrl, {
        signal: controller.signal,
        headers: authHeaders,
        redirect: "follow",
      });
      s3Url = redirectResp.url || downloadUrl;
      controller.abort();
    } catch {
      // AbortError after getting headers is expected; use the resolved URL
    }

    videoUrls[name] = s3Url;
    videoTiming[name] = { start, end };
  }

  model.set("_video_urls", videoUrls);
  model.set("_video_timing", videoTiming);
  model.save_changes();
}

/**
 * Render the multi-video player widget.
 *
 * This is the entry point called by anywidget when the widget is displayed.
 *
 * @param {Object} context - Provided by anywidget
 * @param {Object} context.model - Proxy to Python traitlets. Use model.get('name')
 *   to read synced traits and model.set('name', value) + model.save_changes()
 *   to update them. Listen for changes with model.on('change:name', callback).
 * @param {HTMLElement} context.el - The DOM element where the widget should render.
 *   Append all UI elements to this container.
 */
function render({ model, el }) {
  // Root wrapper with scoped class
  const wrapper = document.createElement("div");
  wrapper.classList.add("video-widget");

  // Control bar
  const controls = document.createElement("div");
  controls.classList.add("video-widget__controls");

  const playPauseBtn = document.createElement("button");
  playPauseBtn.classList.add("video-widget__button");
  playPauseBtn.appendChild(createIcon("play"));

  const settingsBtn = document.createElement("button");
  settingsBtn.classList.add("video-widget__button", "video-widget__settings-btn");
  settingsBtn.appendChild(createIcon("settings"));
  settingsBtn.title = "Video Settings";

  const seekBar = document.createElement("input");
  seekBar.type = "range";
  seekBar.min = 0;
  seekBar.max = 100;
  seekBar.value = 0;
  seekBar.classList.add("video-widget__seekbar");

  const timeLabel = document.createElement("span");
  timeLabel.textContent = "0:00.0 / 0:00.0";
  timeLabel.classList.add("video-widget__time-label");

  controls.appendChild(playPauseBtn);
  controls.appendChild(settingsBtn);
  controls.appendChild(seekBar);
  controls.appendChild(timeLabel);

  // Settings panel (collapsible)
  const settingsPanel = document.createElement("div");
  settingsPanel.classList.add("video-widget__settings-panel");

  const settingsPanelHeader = document.createElement("div");
  settingsPanelHeader.classList.add("video-widget__settings-header");

  const settingsTitle = document.createElement("span");
  settingsTitle.classList.add("video-widget__settings-title");
  settingsTitle.textContent = "Settings";

  const closeBtn = document.createElement("button");
  closeBtn.classList.add("video-widget__close-btn");
  closeBtn.textContent = "Close";
  closeBtn.addEventListener("click", () => {
    model.set("settings_open", false);
    model.save_changes();
  });

  settingsPanelHeader.appendChild(settingsTitle);
  settingsPanelHeader.appendChild(closeBtn);
  settingsPanel.appendChild(settingsPanelHeader);

  const videoSelectionSection = document.createElement("div");
  videoSelectionSection.classList.add("video-widget__video-selection-section");

  const videoSelectionTitle = document.createElement("span");
  videoSelectionTitle.classList.add("video-widget__section-title");
  videoSelectionTitle.textContent = "Video Selection";
  videoSelectionSection.appendChild(videoSelectionTitle);

  const videoSelectionHint = document.createElement("p");
  videoSelectionHint.classList.add("video-widget__section-hint");
  videoSelectionHint.textContent = "Videos are displayed in selection order and sync to the first selected.";
  videoSelectionSection.appendChild(videoSelectionHint);

  const videoList = document.createElement("div");
  videoList.classList.add("video-widget__video-list");
  videoSelectionSection.appendChild(videoList);

  settingsPanel.appendChild(videoSelectionSection);

  const layoutSection = document.createElement("div");
  layoutSection.classList.add("video-widget__layout-section");

  const layoutTitle = document.createElement("span");
  layoutTitle.classList.add("video-widget__section-title");
  layoutTitle.textContent = "Video Grid Layout";
  layoutSection.appendChild(layoutTitle);

  const layoutOptionsContainer = document.createElement("div");
  layoutOptionsContainer.classList.add("video-widget__layout-options");

  const layoutModes = ["row", "column", "grid"];
  layoutModes.forEach((option) => {
    const radioContainer = document.createElement("label");
    radioContainer.classList.add("video-widget__layout-option");

    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "layout-mode";
    radio.value = option;
    radio.checked = option === model.get("layout_mode");
    radio.addEventListener("change", () => {
      if (radio.checked) {
        model.set("layout_mode", option);
        model.save_changes();
      }
    });

    const labelText = document.createElement("span");
    labelText.textContent = option.charAt(0).toUpperCase() + option.slice(1);

    radioContainer.appendChild(radio);
    radioContainer.appendChild(labelText);
    layoutOptionsContainer.appendChild(radioContainer);
  });

  layoutSection.appendChild(layoutOptionsContainer);
  settingsPanel.appendChild(layoutSection);

  // Loading indicator (shown in the video list while video_urls is empty)
  const loadingMsg = document.createElement("div");
  loadingMsg.classList.add("video-widget__metadata-loading");
  const loadingSpinner = document.createElement("div");
  loadingSpinner.classList.add("video-widget__spinner");
  const loadingText = document.createElement("span");
  loadingText.classList.add("video-widget__metadata-loading-text");
  loadingText.textContent = "Loading video metadata\u2026";
  loadingMsg.appendChild(loadingSpinner);
  loadingMsg.appendChild(loadingText);

  // Grid container - using CSS Grid for proper 2D layout
  const gridContainer = document.createElement("div");
  gridContainer.classList.add("video-widget__grid");

  /** @type {HTMLVideoElement[]} */
  let videos = [];
  /** @type {HTMLDivElement[]} */
  let videoContainers = [];
  let isPlaying = false;
  let syncAnimationId = null;

  /**
   * Update loading indicator visibility based on video_urls state.
   */
  function updateLoadingIndicator() {
    const urls = model.get("_video_urls") || {};
    const hasVideos = Object.keys(urls).length > 0;
    if (hasVideos) {
      loadingMsg.style.display = "none";
    } else {
      loadingMsg.style.display = "";
      const lindiFailed = model.get("_lindi_failed");
      loadingText.textContent = lindiFailed
        ? "Loading video metadata from NWB file\u2026"
        : "Loading video metadata\u2026";
    }
  }

  /**
   * Update the settings panel with available videos and their compatibility status.
   */
  function updateSettingsPanel() {
    const videoUrls = model.get("_video_urls") || {};
    const videoTiming = model.get("_video_timing") || {};
    const selectedVideos = model.get("selected_videos") || [];
    const layoutMode = model.get("layout_mode") || "row";
    const settingsOpen = model.get("settings_open");

    // Toggle panel visibility
    if (settingsOpen) {
      settingsPanel.classList.add("video-widget__settings-panel--open");
    } else {
      settingsPanel.classList.remove("video-widget__settings-panel--open");
    }

    // Update layout radio buttons
    const radios = layoutSection.querySelectorAll('input[type="radio"]');
    radios.forEach((radio) => {
      radio.checked = radio.value === layoutMode;
    });

    // Clear and rebuild video list
    videoList.innerHTML = "";

    const videoNames = Object.keys(videoUrls);
    if (videoNames.length === 0) {
      // Don't show "No videos" while still loading
      return;
    }

    videoNames.forEach((name) => {
      const info = videoTiming[name] || { start: 0, end: 0 };
      const isSelected = selectedVideos.includes(name);

      // Check compatibility with currently selected videos
      let isCompatible = true;
      if (!isSelected && selectedVideos.length > 0) {
        isCompatible = selectedVideos.every((selectedName) => {
          const selectedInfo = videoTiming[selectedName] || { start: 0, end: 0 };
          return areCompatible(info, selectedInfo);
        });
      }

      const videoItem = document.createElement("div");
      videoItem.classList.add("video-widget__video-item");
      if (!isCompatible) {
        videoItem.classList.add("video-widget__video-item--incompatible");
      }

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.id = "video-" + name;
      checkbox.checked = isSelected;
      checkbox.disabled = !isCompatible && !isSelected;
      checkbox.addEventListener("change", () => {
        const currentSelected = [...(model.get("selected_videos") || [])];
        if (checkbox.checked) {
          if (!currentSelected.includes(name)) {
            currentSelected.push(name);
          }
        } else {
          const index = currentSelected.indexOf(name);
          if (index > -1) {
            currentSelected.splice(index, 1);
          }
        }
        model.set("selected_videos", currentSelected);
        model.save_changes();
      });

      const label = document.createElement("label");
      label.htmlFor = "video-" + name;
      label.classList.add("video-widget__video-item-label");
      label.textContent = name;

      const timeRange = document.createElement("span");
      timeRange.classList.add("video-widget__video-item-time");
      const endLabel = info.end > info.start ? formatTime(info.end) : "unknown";
      timeRange.textContent = formatTime(info.start) + " - " + endLabel;

      videoItem.appendChild(checkbox);
      videoItem.appendChild(label);
      videoItem.appendChild(timeRange);

      if (!isCompatible) {
        const warningIcon = document.createElement("span");
        warningIcon.classList.add("video-widget__warning-icon");
        warningIcon.title = "Incompatible time range with selected videos";
        warningIcon.appendChild(createIcon("warning"));
        videoItem.appendChild(warningIcon);
      }

      videoList.appendChild(videoItem);
    });
  }

  /**
   * Synchronize all videos to the master (first) video.
   * Corrects drift that occurs due to network latency and buffering differences.
   */
  function syncVideos() {
    if (videos.length < 2 || !isPlaying) {
      return;
    }

    const masterTime = videos[0].currentTime;
    for (let i = 1; i < videos.length; i++) {
      const drift = videos[i].currentTime - masterTime;
      // Correct if drift exceeds 100ms
      if (Math.abs(drift) > 0.1) {
        videos[i].currentTime = masterTime;
      }
    }

    syncAnimationId = requestAnimationFrame(syncVideos);
  }

  /**
   * Update play/pause button content.
   * @param {boolean} playing - Current play state
   */
  function updatePlayPauseButton(playing) {
    playPauseBtn.innerHTML = "";
    playPauseBtn.appendChild(createIcon(playing ? "pause" : "play"));
  }

  /**
   * Get the session time offset for the first selected video.
   * This is the starting timestamp from video_timing.
   */
  function getSessionTimeOffset() {
    const videoTiming = model.get("_video_timing") || {};
    const selectedVideos = model.get("selected_videos") || [];
    for (const name of selectedVideos) {
      if (videoTiming[name]) return videoTiming[name].start;
    }
    return 0;
  }

  /**
   * Get the session end time for the first selected video.
   */
  function getSessionEndTime() {
    const videoTiming = model.get("_video_timing") || {};
    const selectedVideos = model.get("selected_videos") || [];
    for (const name of selectedVideos) {
      if (videoTiming[name] && videoTiming[name].end > videoTiming[name].start) {
        return videoTiming[name].end;
      }
    }
    return null; // Will fall back to video duration
  }

  function updateVideos() {
    gridContainer.innerHTML = "";
    videos = [];
    videoContainers = [];
    const videoUrls = model.get("_video_urls") || {};
    const selectedVideos = model.get("selected_videos") || [];
    const layoutMode = model.get("layout_mode") || "row";
    const gridLayout = model.get("grid_layout") || [];

    // Check if we're in fixed grid mode (grid_layout is non-empty)
    const isFixedGridMode = gridLayout.length > 0;

    // Hide/show settings button based on mode
    if (isFixedGridMode) {
      settingsBtn.style.display = "none";
    } else {
      settingsBtn.style.display = "";
    }

    // Filter to only selected videos that have resolved URLs
    const videosToShow = selectedVideos.filter((name) => videoUrls[name]);

    if (videosToShow.length === 0) {
      const emptyMsg = document.createElement("div");
      emptyMsg.classList.add("video-widget__empty-grid-msg");
      emptyMsg.textContent = "Select videos above to display them here.";
      gridContainer.appendChild(emptyMsg);
      return;
    }

    let numRows, numCols;
    let videoPositions = []; // Array of {name, rowIdx, colIdx}

    if (isFixedGridMode) {
      // Fixed grid mode - use 2D layout directly
      numRows = gridLayout.length;
      numCols = Math.max(...gridLayout.map((row) => row.length));

      // Build positions from grid_layout
      gridLayout.forEach((row, rowIdx) => {
        row.forEach((name, colIdx) => {
          if (videoUrls[name]) {
            videoPositions.push({ name, rowIdx, colIdx });
          }
        });
      });
    } else {
      // Interactive mode - use selected_videos + layout_mode
      const dims = calculateGridDimensions(layoutMode, videosToShow.length);
      numRows = dims.rows;
      numCols = dims.cols;

      // Build positions from selected_videos order
      videosToShow.forEach((name, index) => {
        const rowIdx = Math.floor(index / numCols);
        const colIdx = index % numCols;
        videoPositions.push({ name, rowIdx, colIdx });
      });
    }

    gridContainer.style.gridTemplateColumns = "repeat(" + numCols + ", auto)";
    gridContainer.style.gridTemplateRows = "repeat(" + numRows + ", auto)";

    // Place videos in grid cells
    videoPositions.forEach(({ name, rowIdx, colIdx }) => {
      const url = videoUrls[name];

      const videoCell = document.createElement("div");
      videoCell.classList.add("video-widget__video-cell");
      videoCell.style.gridRow = String(rowIdx + 1);
      videoCell.style.gridColumn = String(colIdx + 1);

      const videoContainer = document.createElement("div");
      videoContainer.classList.add("video-widget__video-container");
      videoContainers.push(videoContainer);

      const video = document.createElement("video");
      video.classList.add("video-widget__video");
      video.src = url;
      video.muted = true; // Mute to allow autoplay
      video.preload = "auto"; // Preload video data
      videos.push(video);

      // Loading spinner
      const loadingDiv = document.createElement("div");
      loadingDiv.classList.add("video-widget__loading");
      const spinner = document.createElement("div");
      spinner.classList.add("video-widget__spinner");
      loadingDiv.appendChild(spinner);

      // Video loading events
      video.addEventListener("loadstart", () => {
        videoContainer.classList.add("video-widget__video-container--loading");
      });
      video.addEventListener("canplay", () => {
        videoContainer.classList.remove(
          "video-widget__video-container--loading"
        );
      });
      video.addEventListener("error", () => {
        console.error("Video error for " + name + ":", video.error);
        videoContainer.classList.remove(
          "video-widget__video-container--loading"
        );
      });

      videoContainer.appendChild(video);
      videoContainer.appendChild(loadingDiv);

      const videoLabels = model.get("video_labels") || {};
      const label = document.createElement("p");
      label.textContent = videoLabels[name] || name;
      label.classList.add("video-widget__video-label");

      videoCell.appendChild(videoContainer);
      videoCell.appendChild(label);
      gridContainer.appendChild(videoCell);
    });

    // Update seek bar max when metadata loads
    if (videos.length > 0) {
      videos[0].addEventListener("loadedmetadata", () => {
        seekBar.max = videos[0].duration;
        const offset = getSessionTimeOffset();
        const endTime = getSessionEndTime();
        const displayEnd = endTime !== null ? endTime : offset + videos[0].duration;
        timeLabel.textContent = formatTime(offset) + " / " + formatTime(displayEnd);
      });
      videos[0].addEventListener("timeupdate", () => {
        if (!seekBar.matches(":active")) {
          seekBar.value = videos[0].currentTime;
        }
        const offset = getSessionTimeOffset();
        const endTime = getSessionEndTime();
        const displayEnd = endTime !== null ? endTime : offset + videos[0].duration;
        const currentSessionTime = offset + videos[0].currentTime;
        timeLabel.textContent =
          formatTime(currentSessionTime) + " / " + formatTime(displayEnd);
      });
      // Handle video end
      videos[0].addEventListener("ended", () => {
        isPlaying = false;
        updatePlayPauseButton(false);
        if (syncAnimationId) {
          cancelAnimationFrame(syncAnimationId);
          syncAnimationId = null;
        }
      });
    }
  }

  playPauseBtn.addEventListener("click", async () => {
    if (isPlaying) {
      videos.forEach((v) => v.pause());
      if (syncAnimationId) {
        cancelAnimationFrame(syncAnimationId);
        syncAnimationId = null;
      }
      isPlaying = false;
      updatePlayPauseButton(false);
    } else {
      // Play all videos and wait for them to start
      const playPromises = videos.map((v) =>
        v.play().catch((err) => {
          console.warn("Video play failed:", err);
        })
      );
      await Promise.all(playPromises);
      isPlaying = true;
      updatePlayPauseButton(true);
      syncVideos(); // Start synchronization loop
    }
  });

  seekBar.addEventListener("input", () => {
    const time = parseFloat(seekBar.value);
    videos.forEach((v) => (v.currentTime = time));
  });

  settingsBtn.addEventListener("click", () => {
    const isOpen = model.get("settings_open");
    model.set("settings_open", !isOpen);
    model.save_changes();
  });

  model.on("change:_video_urls", () => {
    updateLoadingIndicator();
    updateVideos();
    updateSettingsPanel();
  });
  model.on("change:_video_timing", updateSettingsPanel);
  model.on("change:_lindi_failed", updateLoadingIndicator);
  model.on("change:selected_videos", () => {
    updateVideos();
    updateSettingsPanel();
  });
  model.on("change:layout_mode", updateVideos);
  model.on("change:grid_layout", updateVideos);
  model.on("change:settings_open", updateSettingsPanel);

  updateLoadingIndicator();
  updateVideos();
  updateSettingsPanel();

  videoSelectionSection.appendChild(loadingMsg);
  wrapper.appendChild(settingsPanel);
  wrapper.appendChild(gridContainer);
  wrapper.appendChild(controls);
  el.appendChild(wrapper);

  // Start resolving video info in the background (guard against re-entry)
  let videoInfoResolved = false;
  const doResolve = async () => {
    if (videoInfoResolved) return;
    videoInfoResolved = true;
    await resolveVideoInfo(model);
  };
  doResolve();

  // Cleanup function (called when widget is destroyed)
  return () => {
    if (syncAnimationId) {
      cancelAnimationFrame(syncAnimationId);
    }
  };
}

export default { render };
