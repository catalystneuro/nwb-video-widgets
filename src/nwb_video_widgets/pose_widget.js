/**
 * Pose estimation video player widget.
 * Overlays keypoints on streaming video with pose estimation selection.
 *
 * JavaScript fetches video metadata (URLs and session-time ranges) from DANDI
 * via LINDI and the DANDI REST API, then writes back to the `video_urls` and `video_timing` traitlets.
 *
 * Data format (from Python via JSON):
 * - all_camera_data: {pose_name: {keypoint_metadata, pose_coordinates, timestamps}}
 * - pose_coordinates: {keypoint_name: [[x, y], null, [x, y], ...]}
 * - timestamps: [t0, t1, t2, ...] array of frame timestamps
 */

const DISPLAY_WIDTH = 640;
const DISPLAY_HEIGHT = 512;

/**
 * Format seconds as MM:SS.ms string for session time display.
 */
function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 10);
  return mins + ":" + secs.toString().padStart(2, "0") + "." + ms;
}

/**
 * Binary search for frame index closest to target time.
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
  } else if (type === "chevron-down") {
    path.setAttribute("d", "M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z");
  } else if (type === "chevron-up") {
    path.setAttribute("d", "M7.41 15.41L12 10.83l4.59 4.58L18 14l-6-6-6 6 1.41 1.41z");
  }
  svg.appendChild(path);
  return svg;
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
 * Parse a LINDI ref value that should be a JSON object (.zattrs, .zarray, etc).
 * Handles both older LINDI formats (JSON-encoded string) and newer formats
 * (inline JSON object).
 * @param {string | Object} ref - LINDI ref value
 * @returns {Object | null}
 */
function parseLindiJsonRef(ref) {
  if (ref != null && typeof ref === "object" && !Array.isArray(ref)) {
    return ref;
  }
  const text = lindiRefToString(ref);
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
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
 * @param {Object} refs - The lindi.refs object
 * @param {string} seriesPath - e.g. "acquisition/VideoBodyCamera"
 * @returns {Promise<{start: number, end: number} | null>}
 */
async function readLindiTimestamps(refs, seriesPath) {
  const zarrayRef = refs[seriesPath + "/timestamps/.zarray"];
  if (!zarrayRef) return null;

  const zarray = parseLindiJsonRef(zarrayRef);
  if (!zarray) return null;

  const shape = zarray.shape;
  if (!shape || shape.length === 0) return null;
  const nFrames = shape[0];
  if (nFrames === 0) return null;

  const chunkRef = refs[seriesPath + "/timestamps/0"];
  if (!chunkRef) return null;

  const hasCompressor = !!zarray.compressor;
  const hasFilters = zarray.filters && zarray.filters.length > 0;

  if (typeof chunkRef === "string") {
    // Inline data: base64-encoded raw float64 bytes
    const bytes = lindiRefToBytes(chunkRef);
    if (!bytes || bytes.byteLength < 8) return null;
    const floats = new Float64Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 8);
    return { start: floats[0], end: floats[floats.length - 1] };
  }

  if (!Array.isArray(chunkRef) || chunkRef.length !== 3) return null;
  if (hasCompressor || hasFilters) return null;

  const [url, offset] = chunkRef;
  const chunks = zarray.chunks || [nFrames];
  const chunkSize = chunks[0];
  const nChunks = Math.ceil(nFrames / chunkSize);

  const startResp = await fetch(url, {
    headers: { Range: `bytes=${offset}-${offset + 7}` },
  });
  if (!startResp.ok) return null;
  const startBuf = await startResp.arrayBuffer();
  const start = new DataView(startBuf).getFloat64(0, true);

  let end;
  if (nChunks === 1) {
    const lastByteOffset = offset + (nFrames - 1) * 8;
    const endResp = await fetch(url, {
      headers: { Range: `bytes=${lastByteOffset}-${lastByteOffset + 7}` },
    });
    if (!endResp.ok) return { start, end: start };
    const endBuf = await endResp.arrayBuffer();
    end = new DataView(endBuf).getFloat64(0, true);
  } else {
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
 * @param {Object} refs - The lindi.refs object
 * @param {string} seriesPath - e.g. "acquisition/VideoBodyCamera"
 * @returns {Promise<{start: number, end: number}>}
 */
async function readLindiSeriesTiming(refs, seriesPath) {
  const timing = await readLindiTimestamps(refs, seriesPath);
  if (timing !== null) return timing;

  const startingTimeRef = refs[seriesPath + "/starting_time/0"];
  if (startingTimeRef) {
    const start = readLindiFloat64(startingTimeRef);
    if (start !== null) return { start, end: start };
  }

  return { start: 0, end: 0 };
}

// ============ LINDI ARRAY READING ============
// These functions read full numeric arrays from LINDI refs via byte-range requests.
// Ported from Neurosift's lindiDatasetDataLoader.ts, simplified for 1D and 2D float64/float32.

/**
 * Parse .zarray metadata for a LINDI dataset.
 * @param {Object} refs - The lindi.refs object
 * @param {string} datasetPath - e.g. "processing/.../data"
 * @returns {{shape: number[], chunks: number[], dtype: string, compressor: object|null, filters: Array|null}|null}
 */
function readLindiZarray(refs, datasetPath) {
  const zarrayRef = refs[datasetPath + "/.zarray"];
  if (!zarrayRef) return null;
  const text = lindiRefToString(zarrayRef);
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/**
 * Read a single chunk from LINDI refs, handling inline base64 and range references.
 * @param {Object} refs - The lindi.refs object
 * @param {string} chunkPath - e.g. "processing/.../data/0.0"
 * @param {Object} [templates] - The lindi.templates object for URL expansion
 * @param {Object} [options] - Optional {startByte, endByte} for partial reads
 * @param {AbortSignal} [signal] - AbortController signal for cancellation
 * @returns {Promise<ArrayBuffer|null>}
 */
async function readLindiChunk(refs, chunkPath, templates, options, signal) {
  const ref = refs[chunkPath];
  if (!ref) return null;

  if (typeof ref === "string") {
    // Inline data: base64-encoded or plain string
    let buf;
    if (ref.startsWith("base64:")) {
      const binary = atob(ref.slice(7));
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      buf = bytes.buffer;
    } else {
      buf = new TextEncoder().encode(ref).buffer;
    }
    if (options && options.startByte !== undefined) {
      buf = buf.slice(options.startByte, options.endByte);
    }
    return buf;
  }

  if (!Array.isArray(ref) || ref.length !== 3) return null;

  let [url, offset, numBytes] = ref;
  // Apply URL templates: replace {{key}} with template values
  if (templates) {
    for (const [key, value] of Object.entries(templates)) {
      url = url.split("{{" + key + "}}").join(value);
    }
  }

  if (options && options.startByte !== undefined) {
    offset += options.startByte;
    numBytes = options.endByte - options.startByte;
  }

  const resp = await fetch(url, {
    headers: { Range: `bytes=${offset}-${offset + numBytes - 1}` },
    signal,
  });
  if (!resp.ok) return null;
  return await resp.arrayBuffer();
}

/**
 * Get byte size for a numpy dtype string.
 * @param {string} dtype - e.g. "<f8", "<f4"
 * @returns {number}
 */
function getDtypeByteSize(dtype) {
  if (dtype === "<f8" || dtype === "<d") return 8;
  if (dtype === "<f4" || dtype === "<f") return 4;
  if (dtype === "<i4" || dtype === "<i") return 4;
  if (dtype === "<i2") return 2;
  return 8; // default to float64
}

/**
 * Create a typed array view from an ArrayBuffer based on dtype.
 * @param {ArrayBuffer} buf
 * @param {string} dtype
 * @returns {Float64Array|Float32Array}
 */
function createTypedArray(buf, dtype) {
  if (dtype === "<f4" || dtype === "<f") return new Float32Array(buf);
  return new Float64Array(buf); // default for <f8
}

/**
 * Read a full numeric array from LINDI refs.
 * Supports 1D and 2D uncompressed arrays (single-chunk and multi-chunk).
 * Returns null if the data is compressed or reading fails.
 * @param {Object} refs - The lindi.refs object
 * @param {string} datasetPath - e.g. "processing/.../data"
 * @param {Object} [templates] - The lindi.templates object
 * @param {AbortSignal} [signal] - AbortController signal
 * @returns {Promise<Float64Array|Float32Array|null>}
 */
async function readLindiArray(refs, datasetPath, templates, signal) {
  const zarray = readLindiZarray(refs, datasetPath);
  if (!zarray) return null;

  const { shape, chunks, dtype, compressor, filters } = zarray;
  if (!shape || !chunks || !dtype) return null;
  if (shape.length === 0 || shape.length > 2) return null;

  // Bail out for compressed data: caller falls back to Python
  if (compressor) return null;
  if (filters && filters.length > 0) return null;

  const ndims = shape.length;
  const dtypeSize = getDtypeByteSize(dtype);
  const totalElements = shape.reduce((a, b) => a * b, 1);

  // Compute chunk grid
  const macroChunkShape = shape.map((s, i) => Math.ceil(s / chunks[i]));
  const totalChunks = macroChunkShape.reduce((a, b) => a * b, 1);

  if (totalChunks === 1) {
    // Single chunk fast path: one fetch for the entire dataset
    let chunkPath = datasetPath + "/0";
    for (let i = 1; i < ndims; i++) chunkPath += ".0";

    const buf = await readLindiChunk(refs, chunkPath, templates, null, signal);
    if (!buf) return null;
    return createTypedArray(buf, dtype);
  }

  // Multi-chunk: fetch all chunks in parallel and concatenate
  // For 1D: chunk keys are "0", "1", "2", ...
  // For 2D with chunks=[K, N2] (chunked along dim 0 only): keys are "0.0", "1.0", ...
  const resultBuf = new ArrayBuffer(totalElements * dtypeSize);
  const result = createTypedArray(resultBuf, dtype);

  if (ndims === 1) {
    const nChunks = macroChunkShape[0];
    const chunkPromises = [];
    for (let ci = 0; ci < nChunks; ci++) {
      chunkPromises.push(readLindiChunk(refs, datasetPath + "/" + ci, templates, null, signal));
    }
    const chunkBuffers = await Promise.all(chunkPromises);
    let offset = 0;
    for (let ci = 0; ci < nChunks; ci++) {
      if (!chunkBuffers[ci]) return null;
      const chunkData = createTypedArray(chunkBuffers[ci], dtype);
      // Last chunk may be padded; only copy actual data elements
      const elemsToCopy = Math.min(chunkData.length, shape[0] - ci * chunks[0]);
      result.set(chunkData.subarray(0, elemsToCopy), offset);
      offset += elemsToCopy;
    }
  } else {
    // 2D: chunks are typically [K, shape[1]] (chunked along first dim only)
    // General case: iterate over all chunk indices
    const nChunks0 = macroChunkShape[0];
    const nChunks1 = macroChunkShape[1];
    const chunkPromises = [];
    const chunkIndices = [];
    for (let ci0 = 0; ci0 < nChunks0; ci0++) {
      for (let ci1 = 0; ci1 < nChunks1; ci1++) {
        chunkIndices.push([ci0, ci1]);
        chunkPromises.push(
          readLindiChunk(refs, datasetPath + "/" + ci0 + "." + ci1, templates, null, signal),
        );
      }
    }
    const chunkBuffers = await Promise.all(chunkPromises);
    for (let i = 0; i < chunkIndices.length; i++) {
      if (!chunkBuffers[i]) return null;
      const [ci0, ci1] = chunkIndices[i];
      const chunkData = createTypedArray(chunkBuffers[i], dtype);

      // Determine the actual region this chunk covers
      const row0 = ci0 * chunks[0];
      const col0 = ci1 * chunks[1];
      const rowEnd = Math.min(row0 + chunks[0], shape[0]);
      const colEnd = Math.min(col0 + chunks[1], shape[1]);
      const chunkRows = rowEnd - row0;
      const chunkCols = colEnd - col0;

      // Copy chunk data into the result array
      for (let r = 0; r < chunkRows; r++) {
        const srcOffset = r * chunks[1]; // chunk is stored with its full chunk width
        const dstOffset = (row0 + r) * shape[1] + col0;
        for (let c = 0; c < chunkCols; c++) {
          result[dstOffset + c] = chunkData[srcOffset + c];
        }
      }
    }
  }

  return result;
}

/**
 * Read the full timestamps array for a pose series from LINDI.
 * Tries the timestamps dataset first, falls back to starting_time + rate.
 * @param {Object} refs - The lindi.refs object
 * @param {string} seriesPath - path to the PoseEstimationSeries
 * @param {Object} [templates] - The lindi.templates object
 * @param {AbortSignal} [signal] - AbortController signal
 * @returns {Promise<Float64Array|null>}
 */
async function readLindiFullTimestamps(refs, seriesPath, templates, signal) {
  // Try reading the timestamps dataset directly
  const tsArray = await readLindiArray(refs, seriesPath + "/timestamps", templates, signal);
  if (tsArray) return tsArray instanceof Float64Array ? tsArray : new Float64Array(tsArray);

  // Fall back to starting_time + rate (synthesize timestamps)
  const zattrsRef = refs[seriesPath + "/.zattrs"];
  if (!zattrsRef) return null;
  const zattrsText = lindiRefToString(zattrsRef);
  if (!zattrsText) return null;

  let zattrs;
  try {
    zattrs = JSON.parse(zattrsText);
  } catch {
    return null;
  }

  // Need to read starting_time scalar and get rate from zattrs
  const startingTimeRef = refs[seriesPath + "/starting_time/0"];
  const startingTime = startingTimeRef ? readLindiFloat64(startingTimeRef) : null;
  if (startingTime === null) return null;

  // Rate is stored in starting_time's zattrs (as "rate" attribute on the starting_time dataset)
  const stZattrsRef = refs[seriesPath + "/starting_time/.zattrs"];
  if (!stZattrsRef) return null;
  const stZattrsText = lindiRefToString(stZattrsRef);
  if (!stZattrsText) return null;

  let stZattrs;
  try {
    stZattrs = JSON.parse(stZattrsText);
  } catch {
    return null;
  }

  const rate = stZattrs.rate;
  if (!rate || rate <= 0) return null;

  // Determine number of frames from the data dataset shape
  const dataZarray = readLindiZarray(refs, seriesPath + "/data");
  if (!dataZarray || !dataZarray.shape) return null;
  const nFrames = dataZarray.shape[0];

  const timestamps = new Float64Array(nFrames);
  for (let i = 0; i < nFrames; i++) {
    timestamps[i] = startingTime + i / rate;
  }
  return timestamps;
}

// ============ POSE DATA LOADING ============

/**
 * Load all pose data for a camera from LINDI refs.
 * Reads keypoint coordinate arrays and timestamps in parallel.
 * @param {Object} lindi - Parsed LINDI JSON ({refs, templates})
 * @param {Object} seriesPaths - {shortName: "processing/.../SeriesName"}
 * @param {AbortSignal} [signal] - AbortController signal
 * @returns {Promise<{coordinates: Object, timestamps: Float64Array, nFrames: number}|null>}
 *   coordinates maps shortName -> Float64Array (flat, n_frames * 2)
 *   Returns null if any dataset is compressed or reading fails.
 */
async function loadCameraPoseDataFromLindi(lindi, seriesPaths, signal) {
  const refs = lindi.refs;
  const templates = lindi.templates;
  const names = Object.keys(seriesPaths);
  if (names.length === 0) return null;

  // Read all keypoint data arrays and timestamps in parallel
  const dataPromises = names.map((name) =>
    readLindiArray(refs, seriesPaths[name] + "/data", templates, signal),
  );
  const timestampsPromise = readLindiFullTimestamps(refs, seriesPaths[names[0]], templates, signal);

  const results = await Promise.all([...dataPromises, timestampsPromise]);
  const timestamps = results[results.length - 1];
  if (!timestamps) return null;

  const coordinates = {};
  for (let i = 0; i < names.length; i++) {
    if (!results[i]) return null; // compressed or failed, fall back to Python
    coordinates[names[i]] = results[i];
  }

  const nFrames = timestamps.length;
  return { coordinates, timestamps, nFrames };
}

// ============ VIDEO INFO RESOLUTION ============

/**
 * Resolve video info from DANDI via LINDI + DANDI REST API.
 * For the pose widget, uses video_nwb_* seeds if set, falling back to nwb_* seeds.
 * Also caches the LINDI JSON for reuse by pose data loading.
 * @param {Object} model - anywidget model proxy
 * @param {Object} state - shared state object for LINDI cache
 */
async function resolveVideoInfo(model, state) {
  const dandisetId = model.get("_dandiset_id");
  const versionId = model.get("_version_id");
  const dandiApiUrl = model.get("_dandi_api_url");
  const apiKey = model.get("_dandi_api_key");

  // For the split-file case, use video_nwb_* seeds; fall back to main nwb_* seeds
  const assetId =
    model.get("_video_nwb_asset_id") || model.get("_nwb_asset_id");
  const assetPath =
    model.get("_video_nwb_asset_path") || model.get("_nwb_asset_path");

  if (!dandisetId || !assetId) {
    if (state && state._resolveLindiReady) state._resolveLindiReady();
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
    if (state && state._resolveLindiReady) state._resolveLindiReady();
    return;
  }

  // Cache LINDI JSON for pose data loading
  if (state) state.lindi = lindi;

  const refs = lindi.refs;
  const videoUrls = {};
  const videoTiming = {};

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
    const zattrsRef = refs[acquiPrefix + name + "/.zattrs"];
    if (!zattrsRef) continue;

    const attrs = parseLindiJsonRef(zattrsRef);
    if (!attrs || attrs.neurodata_type !== "ImageSeries") continue;

    const extFileRef = refs[acquiPrefix + name + "/external_file/0"];
    if (!extFileRef) continue;

    const relativePath = readLindiJson2String(extFileRef);
    if (!relativePath) continue;

    const cleanRelative = relativePath.replace(/^[./]+/, "");
    const fullPath = nwbParent ? nwbParent + "/" + cleanRelative : cleanRelative;

    const { start, end } = await readLindiSeriesTiming(
      refs,
      acquiPrefix + name
    );

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
      downloadUrl = dandiApiUrl + "/assets/" + videoAssetId + "/download/";
    } catch {
      continue;
    }

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
      // AbortError after getting headers is expected
    }

    videoUrls[name] = s3Url;
    videoTiming[name] = { start, end };
  }

  model.set("_video_urls", videoUrls);
  model.set("_video_timing", videoTiming);
  model.save_changes();

  // Signal that LINDI resolution is complete (pose loading may be waiting)
  if (state && state._resolveLindiReady) state._resolveLindiReady();
}

/**
 * Render the pose video player widget.
 */
function render({ model, el }) {
  const wrapper = document.createElement("div");
  wrapper.classList.add("pose-widget");

  // Shared state for LINDI cache and pose data
  const sharedState = {
    lindi: null, // Cached LINDI JSON, populated by resolveVideoInfo
    lindiReady: null, // Promise resolved when resolveVideoInfo completes
    _resolveLindiReady: null, // Resolver function, called by resolveVideoInfo
    lindiPoseCache: {}, // {cameraName: {coordinates, timestamps, nFrames}}
    poseAbortController: null, // AbortController for in-flight pose loads
  };
  sharedState.lindiReady = new Promise((resolve) => {
    sharedState._resolveLindiReady = resolve;
  });

  // ============ POSE ESTIMATION SELECTION SECTION ============
  const poseSection = document.createElement("div");
  poseSection.classList.add("pose-widget__section", "pose-widget__section--pose");

  const poseHeader = document.createElement("div");
  poseHeader.classList.add("pose-widget__section-header");

  const poseTitleWrapper = document.createElement("div");
  poseTitleWrapper.classList.add("pose-widget__section-title-wrapper");

  const poseTitle = document.createElement("span");
  poseTitle.classList.add("pose-widget__section-title");
  poseTitle.textContent = "Pose Estimation";

  const poseSelectedLabel = document.createElement("span");
  poseSelectedLabel.classList.add("pose-widget__section-selected");

  poseTitleWrapper.appendChild(poseTitle);
  poseTitleWrapper.appendChild(poseSelectedLabel);

  const poseToggleIcon = document.createElement("span");
  poseToggleIcon.classList.add("pose-widget__section-toggle");
  poseToggleIcon.appendChild(createIcon("chevron-down"));

  poseHeader.appendChild(poseTitleWrapper);
  poseHeader.appendChild(poseToggleIcon);

  const poseContent = document.createElement("div");
  poseContent.classList.add("pose-widget__section-content");

  const poseHint = document.createElement("p");
  poseHint.classList.add("pose-widget__section-hint");
  poseHint.textContent = "Select a pose estimation to display.";

  const poseList = document.createElement("div");
  poseList.classList.add("pose-widget__pose-list");

  poseContent.appendChild(poseHint);
  poseContent.appendChild(poseList);

  poseSection.appendChild(poseHeader);
  poseSection.appendChild(poseContent);

  // Toggle pose section collapse
  poseHeader.addEventListener("click", () => {
    poseSection.classList.toggle("pose-widget__section--collapsed");
    poseToggleIcon.innerHTML = "";
    poseToggleIcon.appendChild(
      createIcon(
        poseSection.classList.contains("pose-widget__section--collapsed")
          ? "chevron-down"
          : "chevron-up"
      )
    );
  });

  // ============ VIDEO SELECTION SECTION ============
  const videoSection = document.createElement("div");
  videoSection.classList.add(
    "pose-widget__section",
    "pose-widget__section--video",
    "pose-widget__section--hidden"
  );

  const videoHeader = document.createElement("div");
  videoHeader.classList.add("pose-widget__section-header");

  const videoTitleWrapper = document.createElement("div");
  videoTitleWrapper.classList.add("pose-widget__section-title-wrapper");

  const videoTitle = document.createElement("span");
  videoTitle.classList.add("pose-widget__section-title");
  videoTitle.textContent = "Video Selection";

  const videoSelectedLabel = document.createElement("span");
  videoSelectedLabel.classList.add("pose-widget__section-selected");

  videoTitleWrapper.appendChild(videoTitle);
  videoTitleWrapper.appendChild(videoSelectedLabel);

  const videoToggleIcon = document.createElement("span");
  videoToggleIcon.classList.add("pose-widget__section-toggle");
  videoToggleIcon.appendChild(createIcon("chevron-down"));

  videoHeader.appendChild(videoTitleWrapper);
  videoHeader.appendChild(videoToggleIcon);

  // Toggle video section collapse
  videoHeader.addEventListener("click", () => {
    videoSection.classList.toggle("pose-widget__section--collapsed");
    videoToggleIcon.innerHTML = "";
    videoToggleIcon.appendChild(
      createIcon(
        videoSection.classList.contains("pose-widget__section--collapsed")
          ? "chevron-down"
          : "chevron-up"
      )
    );
  });

  const videoContent = document.createElement("div");
  videoContent.classList.add("pose-widget__section-content");

  const videoHint = document.createElement("p");
  videoHint.classList.add("pose-widget__section-hint");
  videoHint.textContent = "Select the video to overlay the pose estimation on.";

  const videoSelect = document.createElement("select");
  videoSelect.classList.add("pose-widget__video-select");

  videoContent.appendChild(videoHint);
  videoContent.appendChild(videoSelect);

  videoSection.appendChild(videoHeader);
  videoSection.appendChild(videoContent);

  // ============ VIDEO CONTAINER ============
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

  const emptyMsg = document.createElement("div");
  emptyMsg.classList.add("pose-widget__empty-msg");
  emptyMsg.textContent = "Select a pose estimation and video to begin.";

  const loadingOverlay = document.createElement("div");
  loadingOverlay.classList.add("pose-widget__loading-overlay");

  const loadingSpinner = document.createElement("div");
  loadingSpinner.classList.add("pose-widget__loading-spinner");

  const loadingText = document.createElement("div");
  loadingText.classList.add("pose-widget__loading-text");
  loadingText.textContent = "Loading pose data...";

  loadingOverlay.appendChild(loadingSpinner);
  loadingOverlay.appendChild(loadingText);

  videoContainer.appendChild(video);
  videoContainer.appendChild(canvas);
  videoContainer.appendChild(emptyMsg);
  videoContainer.appendChild(loadingOverlay);

  // ============ CONTROLS ============
  const controls = document.createElement("div");
  controls.classList.add("pose-widget__controls");

  const playPauseBtn = document.createElement("button");
  playPauseBtn.classList.add("pose-widget__button");
  playPauseBtn.appendChild(createIcon("play"));

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
  controls.appendChild(seekBar);
  controls.appendChild(timeLabel);

  // ============ KEYPOINT VISIBILITY SECTION (after controls) ============
  const keypointSection = document.createElement("div");
  keypointSection.classList.add(
    "pose-widget__section",
    "pose-widget__section--keypoints",
    "pose-widget__section--hidden"
  );

  const keypointHeader = document.createElement("div");
  keypointHeader.classList.add("pose-widget__section-header");

  const keypointTitle = document.createElement("span");
  keypointTitle.classList.add("pose-widget__section-title");
  keypointTitle.textContent = "Keypoint Visibility";

  keypointHeader.appendChild(keypointTitle);

  const keypointContent = document.createElement("div");
  keypointContent.classList.add("pose-widget__section-content");

  const keypointTogglesWrapper = document.createElement("div");
  keypointTogglesWrapper.classList.add("pose-widget__keypoint-toggles-wrapper");

  const utilityRow = document.createElement("div");
  utilityRow.classList.add("pose-widget__keypoint-toggles");

  const keypointRow = document.createElement("div");
  keypointRow.classList.add("pose-widget__keypoint-toggles");

  keypointTogglesWrapper.appendChild(utilityRow);
  keypointTogglesWrapper.appendChild(keypointRow);
  keypointContent.appendChild(keypointTogglesWrapper);

  keypointSection.appendChild(keypointHeader);
  keypointSection.appendChild(keypointContent);

  // ============ DISPLAY OPTIONS SECTION (after keypoints) ============
  const displaySection = document.createElement("div");
  displaySection.classList.add(
    "pose-widget__section",
    "pose-widget__section--display",
    "pose-widget__section--hidden"
  );

  const displayHeader = document.createElement("div");
  displayHeader.classList.add("pose-widget__section-header");

  const displayTitle = document.createElement("span");
  displayTitle.classList.add("pose-widget__section-title");
  displayTitle.textContent = "Display Options";

  displayHeader.appendChild(displayTitle);

  const displayContent = document.createElement("div");
  displayContent.classList.add("pose-widget__section-content");

  const labelToggle = document.createElement("label");
  labelToggle.classList.add("pose-widget__label-toggle");
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = model.get("show_labels");
  labelToggle.appendChild(checkbox);
  labelToggle.appendChild(document.createTextNode(" Show keypoint labels"));
  displayContent.appendChild(labelToggle);

  displaySection.appendChild(displayHeader);
  displaySection.appendChild(displayContent);

  // ============ STATE ============
  let isPlaying = false;
  let animationId = null;
  let visibleKeypoints = { ...model.get("visible_keypoints") };

  // ============ FUNCTIONS ============

  /**
   * Get pose data for the currently selected camera.
   * Returns a normalized object with timestamps, keypoint_metadata, and either
   * pose_coordinates (Python path) or lindi_coordinates (LINDI path).
   * @returns {Object|null}
   */
  function getCurrentCameraData() {
    const camera = model.get("selected_camera");
    // Check LINDI cache first (binary data loaded directly from S3)
    const lindiData = sharedState.lindiPoseCache[camera];
    if (lindiData) {
      const metadata = (model.get("_keypoint_metadata") || {})[camera] || {};
      return {
        source: "lindi",
        timestamps: lindiData.timestamps,
        keypoint_metadata: metadata,
        lindi_coordinates: lindiData.coordinates, // {name: Float64Array} flat pairs
        nFrames: lindiData.nFrames,
      };
    }
    // Fall back to Python-provided data
    const allData = model.get("all_camera_data");
    if (allData[camera]) {
      return {
        source: "python",
        ...allData[camera], // timestamps, keypoint_metadata, pose_coordinates
      };
    }
    return null;
  }

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

  function updatePoseList() {
    const poses = model.get("available_cameras") || [];
    const posesInfo = model.get("available_cameras_info") || {};
    const selectedPose = model.get("selected_camera");

    poseList.innerHTML = "";

    if (poses.length === 0) {
      const emptyText = document.createElement("p");
      emptyText.classList.add("pose-widget__empty-text");
      emptyText.textContent = "No pose estimations available.";
      poseList.appendChild(emptyText);
      return;
    }

    poses.forEach((pose) => {
      const info = posesInfo[pose] || {};
      const isSelected = pose === selectedPose;

      const poseItem = document.createElement("div");
      poseItem.classList.add("pose-widget__pose-item");
      if (isSelected) {
        poseItem.classList.add("pose-widget__pose-item--selected");
      }

      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "pose-select";
      radio.id = "pose-" + pose;
      radio.value = pose;
      radio.checked = isSelected;
      radio.addEventListener("change", () => {
        if (radio.checked) {
          model.set("selected_camera", pose);
          model.save_changes();
        }
      });

      const label = document.createElement("label");
      label.htmlFor = "pose-" + pose;
      label.classList.add("pose-widget__pose-item-label");
      label.textContent = pose;

      const infoSpan = document.createElement("span");
      infoSpan.classList.add("pose-widget__pose-item-info");
      if (info.start !== undefined) {
        const endLabel = info.end !== undefined && info.end > info.start ? formatTime(info.end) : "unknown";
        infoSpan.textContent =
          formatTime(info.start) +
          " - " +
          endLabel +
          (info.keypoints ? " | " + info.keypoints.length + " keypoints" : "");
      }

      poseItem.appendChild(radio);
      poseItem.appendChild(label);
      poseItem.appendChild(infoSpan);

      poseList.appendChild(poseItem);
    });
  }

  function updateVideoSelect() {
    const videoUrls = model.get("_video_urls") || {};
    const videoTiming = model.get("_video_timing") || {};
    const selectedPose = model.get("selected_camera");
    const cameraToVideo = model.get("camera_to_video") || {};
    const currentVideoName = cameraToVideo[selectedPose] || "";

    videoSelect.innerHTML = "";

    // Add empty option
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = "-- Select video --";
    videoSelect.appendChild(emptyOption);

    // Add video options from video_urls, with timing from video_timing
    for (const videoName of Object.keys(videoUrls)) {
      const option = document.createElement("option");
      const info = videoTiming[videoName] || {};
      option.value = videoName;
      option.textContent = videoName;
      if (info.start !== undefined) {
        const endLabel =
          info.end !== undefined && info.end > info.start
            ? formatTime(info.end)
            : "unknown";
        option.textContent +=
          " (" + formatTime(info.start) + " - " + endLabel + ")";
      }
      videoSelect.appendChild(option);
    }

    videoSelect.value = currentVideoName;
  }

  function updateSectionVisibility() {
    const selectedPose = model.get("selected_camera");
    const cameraToVideo = model.get("camera_to_video") || {};
    const currentVideoName = cameraToVideo[selectedPose] || "";
    const data = getCurrentCameraData();

    // Update selected labels
    poseSelectedLabel.textContent = selectedPose ? selectedPose : "";
    videoSelectedLabel.textContent = currentVideoName ? currentVideoName : "";

    // Show video section when pose is selected
    if (selectedPose) {
      videoSection.classList.remove("pose-widget__section--hidden");
      // Collapse pose section
      poseSection.classList.add("pose-widget__section--collapsed");
      poseToggleIcon.innerHTML = "";
      poseToggleIcon.appendChild(createIcon("chevron-down"));
    } else {
      videoSection.classList.add("pose-widget__section--hidden");
      poseSection.classList.remove("pose-widget__section--collapsed");
      poseToggleIcon.innerHTML = "";
      poseToggleIcon.appendChild(createIcon("chevron-up"));
    }

    // Collapse video section when video is selected
    if (currentVideoName) {
      videoSection.classList.add("pose-widget__section--collapsed");
      videoToggleIcon.innerHTML = "";
      videoToggleIcon.appendChild(createIcon("chevron-down"));
    } else {
      videoSection.classList.remove("pose-widget__section--collapsed");
      videoToggleIcon.innerHTML = "";
      videoToggleIcon.appendChild(createIcon("chevron-up"));
    }

    // Show keypoint and display sections when we have data and video
    if (selectedPose && currentVideoName && data) {
      keypointSection.classList.remove("pose-widget__section--hidden");
      displaySection.classList.remove("pose-widget__section--hidden");
    } else {
      keypointSection.classList.add("pose-widget__section--hidden");
      displaySection.classList.add("pose-widget__section--hidden");
    }

    // Update video container empty state
    if (!selectedPose || !currentVideoName) {
      videoContainer.classList.add("pose-widget__video-container--empty");
    } else {
      videoContainer.classList.remove("pose-widget__video-container--empty");
    }
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

  function getFrameIndex() {
    const data = getCurrentCameraData();
    const timestamps = data?.timestamps;
    if (!timestamps || timestamps.length === 0) return 0;
    return findFrameIndex(timestamps, timestamps[0] + video.currentTime);
  }

  function drawPose() {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const selectedCamera = model.get("selected_camera");
    if (!selectedCamera) return;

    const data = getCurrentCameraData();
    if (!data) return;

    const metadata = data.keypoint_metadata;
    const timestamps = data.timestamps;
    const showLabels = model.get("show_labels");

    if (!timestamps || timestamps.length === 0) return;

    const frameIdx = getFrameIndex();

    if (!video.videoWidth || !video.videoHeight) return;

    const scaleX = DISPLAY_WIDTH / video.videoWidth;
    const scaleY = DISPLAY_HEIGHT / video.videoHeight;

    if (data.source === "lindi") {
      // LINDI path: coordinates are flat Float64Array (pairs of x, y)
      const coordinates = data.lindi_coordinates;
      if (!coordinates) return;
      for (const [name, coords] of Object.entries(coordinates)) {
        if (visibleKeypoints[name] === false) continue;
        const offset = frameIdx * 2;
        const x = coords[offset];
        const y = coords[offset + 1];
        if (isNaN(x) || isNaN(y)) continue;
        drawKeypoint(ctx, x * scaleX, y * scaleY, metadata[name], showLabels);
      }
    } else {
      // Python path: coordinates are nested arrays [[x, y], null, ...]
      const coordinates = data.pose_coordinates;
      if (!coordinates) return;
      for (const [name, coords] of Object.entries(coordinates)) {
        if (visibleKeypoints[name] === false) continue;
        const coord = coords[frameIdx];
        if (!coord) continue;
        drawKeypoint(ctx, coord[0] * scaleX, coord[1] * scaleY, metadata[name], showLabels);
      }
    }
    updateTimeLabel(frameIdx);
  }

  function drawKeypoint(ctx, x, y, kp, showLabels) {
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, 2 * Math.PI);
    ctx.fillStyle = kp?.color || "#fff";
    ctx.fill();
    ctx.strokeStyle = "#000";
    ctx.lineWidth = 1.5;
    ctx.stroke();

    if (showLabels && kp) {
      ctx.font = "bold 10px sans-serif";
      ctx.fillStyle = "#fff";
      ctx.strokeStyle = "#000";
      ctx.lineWidth = 2;
      ctx.strokeText(kp.label, x + 6, y + 3);
      ctx.fillText(kp.label, x + 6, y + 3);
    }
  }

  function animate() {
    drawPose();
    if (isPlaying) animationId = requestAnimationFrame(animate);
  }

  function updateLoadingState() {
    const isLoading = model.get("loading");
    const camera = model.get("selected_camera");
    const cameraToVideo = model.get("camera_to_video") || {};
    const currentVideoName = cameraToVideo[camera] || "";
    const data = getCurrentCameraData();

    if (isLoading || (camera && currentVideoName && !data)) {
      loadingOverlay.classList.add("pose-widget__loading-overlay--visible");
      video.style.visibility = "hidden";
      canvas.style.visibility = "hidden";
    } else {
      loadingOverlay.classList.remove("pose-widget__loading-overlay--visible");
      video.style.visibility = "visible";
      canvas.style.visibility = "visible";
    }
  }

  function loadVideo() {
    const camera = model.get("selected_camera");
    const cameraToVideo = model.get("camera_to_video") || {};
    const videoName = cameraToVideo[camera];

    if (!camera || !videoName) {
      video.src = "";
      return;
    }

    const videoUrls = model.get("_video_urls") || {};
    const videoUrl = videoUrls[videoName];

    if (videoUrl && video.src !== videoUrl) {
      video.src = videoUrl;
    }
    updateLoadingState();
  }

  function updatePlayPauseIcon(playing) {
    playPauseBtn.innerHTML = "";
    playPauseBtn.appendChild(createIcon(playing ? "pause" : "play"));
  }

  function switchCamera() {
    const data = getCurrentCameraData();
    seekBar.max = data?.timestamps?.length - 1 || 100;
    createKeypointToggles();
    loadVideo();
    drawPose();
    updateSectionVisibility();
  }

  // ============ INITIALIZE ============
  updatePoseList();
  updateVideoSelect();
  updateSectionVisibility();
  loadVideo();

  const initialData = getCurrentCameraData();
  if (initialData?.timestamps) {
    seekBar.max = initialData.timestamps.length - 1;
  }

  // ============ EVENT LISTENERS ============

  video.addEventListener("loadedmetadata", drawPose);
  video.addEventListener("seeked", drawPose);
  video.addEventListener("timeupdate", drawPose);

  model.on("change:selected_camera", async () => {
    if (isPlaying) {
      video.pause();
      updatePlayPauseIcon(false);
      if (animationId) cancelAnimationFrame(animationId);
      isPlaying = false;
    }
    updatePoseList();
    updateVideoSelect();

    // Abort any in-flight LINDI pose load for a previous camera
    if (sharedState.poseAbortController) {
      sharedState.poseAbortController.abort();
      sharedState.poseAbortController = null;
    }

    const camera = model.get("selected_camera");
    if (!camera) {
      switchCamera();
      return;
    }

    // If data is already available (LINDI cache or Python), switch immediately
    if (sharedState.lindiPoseCache[camera] || model.get("all_camera_data")[camera]) {
      switchCamera();
      return;
    }

    // Try loading from LINDI if paths are available and LINDI JSON is cached
    const seriesPaths = (model.get("_pose_series_paths") || {})[camera];
    if (seriesPaths && sharedState.lindi) {
      loadingOverlay.classList.add("pose-widget__loading-overlay--visible");
      video.style.visibility = "hidden";
      canvas.style.visibility = "hidden";

      const controller = new AbortController();
      sharedState.poseAbortController = controller;

      try {
        const result = await loadCameraPoseDataFromLindi(
          sharedState.lindi,
          seriesPaths,
          controller.signal,
        );
        if (controller.signal.aborted) return; // camera was switched during load

        if (result) {
          sharedState.lindiPoseCache[camera] = result;
          switchCamera();
          updateLoadingState();
          return;
        }
      } catch (err) {
        if (err.name === "AbortError") return;
        // Fall through to Python fallback
      }

      // LINDI loading failed, signal Python to load data
      model.set("_pose_lindi_failed", true);
      model.save_changes();
    } else if (seriesPaths && !sharedState.lindi) {
      // LINDI JSON not fetched yet (resolveVideoInfo still in progress).
      // Wait for it, then load pose data.
      loadingOverlay.classList.add("pose-widget__loading-overlay--visible");
      video.style.visibility = "hidden";
      canvas.style.visibility = "hidden";

      const controller = new AbortController();
      sharedState.poseAbortController = controller;

      // Wait for LINDI to become available (resolveVideoInfo sets sharedState.lindi)
      await sharedState.lindiReady;
      if (controller.signal.aborted) return;

      if (sharedState.lindi) {
        try {
          const result = await loadCameraPoseDataFromLindi(
            sharedState.lindi,
            seriesPaths,
            controller.signal,
          );
          if (controller.signal.aborted) return;

          if (result) {
            sharedState.lindiPoseCache[camera] = result;
            switchCamera();
            updateLoadingState();
            return;
          }
        } catch (err) {
          if (err.name === "AbortError") return;
        }
      }

      // LINDI unavailable or loading failed
      model.set("_pose_lindi_failed", true);
      model.save_changes();
    }

    // For non-LINDI path or when waiting for Python fallback, just switch
    // (Python observer will populate all_camera_data and trigger change event)
    switchCamera();
  });

  model.on("change:available_cameras", updatePoseList);

  model.on("change:_video_urls", () => {
    updateVideoSelect();
    loadVideo();
  });
  model.on("change:_video_timing", updateVideoSelect);

  model.on("change:camera_to_video", () => {
    updateSectionVisibility();
    loadVideo();
  });

  model.on("change:all_camera_data", () => {
    updateLoadingState();
    createKeypointToggles();
    updateSectionVisibility();

    // Update seek bar max when camera data loads
    const data = getCurrentCameraData();
    if (data?.timestamps?.length) {
      seekBar.max = data.timestamps.length - 1;
    }

    drawPose();
  });

  model.on("change:visible_keypoints", () => {
    visibleKeypoints = { ...model.get("visible_keypoints") };
    updateToggleStyles();
    drawPose();
  });

  model.on("change:loading", updateLoadingState);

  videoSelect.addEventListener("change", () => {
    const selectedVideo = videoSelect.value;
    const selectedPose = model.get("selected_camera");
    const newMapping = { ...model.get("camera_to_video") };

    if (selectedVideo) {
      newMapping[selectedPose] = selectedVideo;
    } else {
      delete newMapping[selectedPose];
    }

    model.set("camera_to_video", newMapping);
    model.save_changes();
  });

  playPauseBtn.addEventListener("click", () => {
    const selectedCamera = model.get("selected_camera");
    const cameraToVideo = model.get("camera_to_video") || {};
    if (!selectedCamera || !cameraToVideo[selectedCamera]) {
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

  // ============ LAYOUT ============
  wrapper.appendChild(poseSection);
  wrapper.appendChild(videoSection);
  wrapper.appendChild(videoContainer);
  wrapper.appendChild(controls);
  wrapper.appendChild(keypointSection);
  wrapper.appendChild(displaySection);
  el.appendChild(wrapper);

  // Start resolving video info in the background (guard against re-entry)
  let videoInfoResolved = false;
  const doResolve = async () => {
    if (videoInfoResolved) return;
    videoInfoResolved = true;
    await resolveVideoInfo(model, sharedState);
  };
  doResolve();

  return () => {
    if (animationId) {
      cancelAnimationFrame(animationId);
    }
  };
}

export default { render };
