# Test Video Fixtures

Stub videos used for codec detection and validation tests. Each file was downloaded from DANDI Archive and trimmed/downscaled with ffmpeg to minimize size while preserving the original codec.

## Provenance

| File | Codec | Source Dandiset | ffmpeg command |
|------|-------|-----------------|----------------|
| stub_h264.mp4 | H.264 (avc1) | [DANDI:001702](https://dandiarchive.org/dandiset/001702) | `ffmpeg -i <source> -t 0.5 -vf "scale=160:120" -c:v libx264 -crf 28 -pix_fmt yuv420p -r 10 stub_h264.mp4` |
| stub_mjpeg.avi | MJPEG | [DANDI:001432](https://dandiarchive.org/dandiset/001432) | `ffmpeg -i <source> -t 0.5 -vf "scale=160:120" -c:v mjpeg -q:v 15 -r 10 stub_mjpeg.avi` |
| stub_mp4v.mp4 | MPEG-4 Part 2 (mp4v) | [DANDI:001425](https://dandiarchive.org/dandiset/001425) | `ffmpeg -i <source> -t 0.5 -vf "scale=160:120" -c:v mpeg4 -q:v 15 -r 10 stub_mp4v.mp4` |

All files are 160x120 resolution, ~0.5 seconds, 10 fps.
