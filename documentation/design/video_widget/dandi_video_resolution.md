# DANDI Video Resolution Strategy

## Problem

DANDI widgets need to discover ImageSeries in an NWB file, read their `external_file` paths
and session-time ranges, then resolve those paths to S3 URLs via the DANDI REST API. The
original approach loaded the full NWB file in Python via `pynwb.NWBHDF5IO.read()`, which
took 10-30 seconds for large files (IBL datasets) because pynwb loads namespaces and builds
the entire object graph.

## Strategy: LINDI first, targeted h5py fallback

### Primary path: LINDI (JavaScript)

LINDI is a pre-indexed JSON representation of an NWB/HDF5 file hosted at
`lindi.neurosift.org`. It maps Zarr-style paths to inline data or byte-range references into
the original HDF5 file. When available, JavaScript can resolve everything without Python:

1. Fetch the LINDI JSON (~100-500 KB, one HTTP request)
2. Find ImageSeries by reading `.zattrs` for each acquisition group
3. Read `external_file[0]` (inline json2-encoded string)
4. Read `timestamps[0]` and `timestamps[-1]` (inline bytes or targeted range requests)
5. Resolve video paths to S3 URLs via the DANDI REST API

Total time: 1-2 seconds.

### Fallback path: targeted h5py (Python)

LINDI coverage is not universal. If `lindi.neurosift.org` returns 404, JavaScript signals the
failure back to Python via a traitlet, and Python reads the values directly using `h5py` +
`remfile`:

```python
rf = remfile.File(s3_url)
h5f = h5py.File(rf, "r")
for name in h5f["acquisition"]:
    obj = h5f["acquisition"][name]
    if obj.attrs.get("neurodata_type") == "ImageSeries" and "external_file" in obj:
        path = obj["external_file"][0]
        start = float(obj["timestamps"][0])
        end = float(obj["timestamps"][-1])
```

This is significantly faster than the old `NWBHDF5IO.read()` approach because it skips pynwb
entirely: no namespace loading, no object graph construction, no schema validation. It reads
only the specific HDF5 datasets and attributes needed.

Measured performance on an IBL NWB file (dandiset 000409, ~2 GB):
- `NWBHDF5IO.read()` + Python URL resolution: 10-30 seconds
- Targeted `h5py` reads (no pynwb): ~5-6 seconds
- LINDI (when available): ~1-2 seconds

### Why not HDF5-in-JavaScript?

Neurosift implements a full HDF5-over-HTTP reader in JavaScript (~2000 lines of TypeScript)
that can parse the HDF5 superblock, walk B-trees, decode Zarr chunks with various compressors,
and handle multi-dimensional slicing. This allows Neurosift to work entirely in the browser
with no Python backend.

We chose not to implement this because:

1. **Scope**: We only need 4 values per ImageSeries (`neurodata_type`, `external_file[0]`,
   `timestamps[0]`, `timestamps[-1]`). A full HDF5 parser is massive overkill.

2. **Existing dependencies**: We already have `h5py` and `remfile` in our Python dependencies.
   The fallback path is ~15 lines of Python.

3. **Maintenance**: A JavaScript HDF5 parser requires handling B-tree traversal, chunk layouts,
   compression codecs (blosc, gzip, zstd), shuffle filters, and variable-length string
   encoding. Each of these is a potential source of bugs. The Python ecosystem handles all of
   this through battle-tested libraries.

4. **Performance**: The fallback path (5-6 seconds) is acceptable. Users who need faster
   resolution will benefit from LINDI coverage expanding over time. The HDF5-in-JS approach
   would not be significantly faster because the bottleneck is HTTP round-trips, not parsing.

### Why not generate LINDI on-the-fly in Python?

We tested using the `lindi` Python library to generate the LINDI JSON from the S3 URL:

```python
store = LindiH5ZarrStore.from_file(s3_url)
rfs = store.to_reference_file_system()
```

This took ~8 seconds for the same IBL file because `to_reference_file_system()` indexes ALL
datasets in the NWB file (including large electrophysiology arrays with hundreds of chunks),
not just the ImageSeries we need. It produces ~500 KB of JSON, most of which we discard. The
targeted `h5py` approach is both faster and simpler.

## Data flow

```
Widget created
    |
    v
Python: extract seeds from asset (instant)
    |
    v
JavaScript: fetch LINDI JSON
    |
    +--[200 OK]----> Parse LINDI, resolve URLs and timing
    |                    |
    |                    v
    |                Set _video_urls + _video_timing traitlets
    |
    +--[404]-------> Set _lindi_failed = true traitlet
                         |
                         v
                     Python: @observe("_lindi_failed")
                         |
                         v
                     Python: targeted h5py reads via remfile
                         |
                         v
                     Set _video_urls + _video_timing traitlets
```

## Related

- `neurosift_pattern_migration.md`: Overall architecture and traitlet design
- `timestamp_based_seeking.md`: How timing data is used in the UI
- Neurosift LINDI implementation: `~/development/work_repos/neurosift/src/remote-h5-file/lib/lindi/`
- Neurosift HDF5 reader: `~/development/work_repos/neurosift/src/remote-h5-file/lib/RemoteH5File.ts`
