#!/usr/bin/env python3
"""Stitch matted (RGBA) clips into one transparent loop with alpha dissolves.

Joins N clips by fading each clip's ALPHA in/out and overlaying them on a
transparent base, offset so they crossfade -- NOT xfade=pixelize (which detonates
at the midpoint). The loop WRAP (last clip -> first clip) is a hard cut, so keep
those end frames matched in style/pose (see references/stitching.md).

Builds one lossless RGBA composite, then derives three web outputs from it:
  - <out>.webm        VP9-alpha, true transparency (Chrome/Firefox/Edge)
  - <out>.mp4         opaque fallback, baked over --bg (Safari/old engines)
  - <out>.poster.png  a representative transparent frame

Deriving the mp4/poster from a qtrle composite (not the VP9 webm) sidesteps the
trap that ffmpeg cannot decode VP9 side-data alpha for its own filters.

Inputs may be matted frame DIRECTORIES (%04d.png from matte_frames.py) or clips.

Usage:
  python loop_stitch.py seg1/ seg2/ seg3/ --out character --fps 24 --xfade 0.4 \
      --mp4 --poster --bg 0x050e22
  python loop_stitch.py a.webm b.webm --out loop --pixelate 0:110   # pixelate clip 0
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile


def find_tool(name, env_var):
    return shutil.which(name) or os.environ.get(env_var) or name


FFMPEG = find_tool("ffmpeg", "FFMPEG")
FFPROBE = find_tool("ffprobe", "FFPROBE")


def probe_dims(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    return int(s["width"]), int(s["height"])


def probe_duration(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", path],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def count_pngs(d):
    return len([f for f in os.listdir(d) if f.lower().endswith(".png")])


def build_sources(inputs, fps):
    """Return (ffmpeg_input_args, [duration...], (W,H)). Dirs feed as image seqs."""
    in_args, durations = [], []
    dims = None
    for path in inputs:
        if os.path.isdir(path):
            n = count_pngs(path)
            if n == 0:
                sys.exit(f"No PNG frames in {path}")
            pattern = os.path.join(path, "%04d.png")
            in_args += ["-framerate", str(fps), "-start_number", "1", "-i", pattern]
            durations.append(n / fps)
            if dims is None:
                first = sorted(f for f in os.listdir(path)
                               if f.lower().endswith(".png"))[0]
                dims = probe_dims(os.path.join(path, first))
        else:
            in_args += ["-i", path]
            durations.append(probe_duration(path))
            if dims is None:
                dims = probe_dims(path)
    return in_args, durations, dims


def build_filter(n, durations, fps, xfade, w, h, pixelate):
    """Alpha-dissolve overlay graph. Last clip has no fade-out => hard-cut wrap."""
    # Offsets: each clip overlaps the previous by xfade seconds.
    offsets = [0.0]
    for i in range(1, n):
        offsets.append(offsets[i - 1] + durations[i - 1] - xfade)
    total = offsets[-1] + durations[-1]

    parts = [f"color=c=black@0.0:s={w}x{h}:r={fps},format=rgba,"
             f"trim=duration={total:.4f}[base]"]
    for i in range(n):
        chain = [f"[{i}:v]format=rgba"]
        if i in pixelate:
            px = pixelate[i]
            chain.append(f"scale={px}:-1:flags=neighbor,scale={w}:{h}:flags=neighbor")
        if i > 0:  # fade alpha in (not the first clip)
            chain.append(f"fade=t=in:st=0:d={xfade}:alpha=1")
        if i < n - 1:  # fade alpha out (not the last clip -> hard-cut the loop wrap)
            chain.append(f"fade=t=out:st={durations[i] - xfade:.4f}:d={xfade}:alpha=1")
        chain.append(f"setpts=PTS-STARTPTS+{offsets[i]:.4f}/TB")
        parts.append(",".join(chain) + f"[c{i}]")

    prev = "base"
    for i in range(n):
        out_lbl = "out" if i == n - 1 else f"o{i}"
        parts.append(f"[{prev}][c{i}]overlay[{out_lbl}]")
        prev = out_lbl
    return ";".join(parts), total


def run(cmd):
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("inputs", nargs="+", help="matted frame dirs OR clip files, in order")
    p.add_argument("--out", default="loop", help="output basename (default: loop)")
    p.add_argument("--fps", type=float, default=24.0)
    p.add_argument("--xfade", type=float, default=0.4, help="crossfade seconds")
    p.add_argument("--size", help="WxH (default: first input's dimensions)")
    p.add_argument("--pixelate", action="append", default=[],
                   metavar="I:SIZE", help="pixelate clip I to chunk SIZE (repeatable)")
    p.add_argument("--mp4", action="store_true", help="also write the opaque fallback")
    p.add_argument("--bg", default="0x050e22", help="bg colour to bake the mp4 over")
    p.add_argument("--poster", action="store_true", help="also write a poster PNG")
    p.add_argument("--poster-at", type=float, default=1.0, help="poster timestamp (s)")
    p.add_argument("--crf", type=int, default=30, help="VP9 webm quality (lower=better)")
    args = p.parse_args()

    pixelate = {}
    for spec in args.pixelate:
        i, size = spec.split(":")
        pixelate[int(i)] = int(size)

    in_args, durations, dims = build_sources(args.inputs, args.fps)
    if args.size:
        w, h = (int(x) for x in args.size.lower().split("x"))
    else:
        w, h = dims
    n = len(args.inputs)
    flt, total = build_filter(n, durations, args.fps, args.xfade, w, h, pixelate)
    print(f"{n} clips, durations={['%.2f' % d for d in durations]}, "
          f"xfade={args.xfade}s -> loop {total:.2f}s @ {w}x{h}")

    tmp = tempfile.mkdtemp(prefix="stitch_")
    composite = os.path.join(tmp, "composite.mov")  # qtrle = lossless RGBA, ffmpeg-readable
    try:
        run([FFMPEG, "-y", *in_args, "-filter_complex", flt, "-map", "[out]",
             "-c:v", "qtrle", "-pix_fmt", "rgba", composite])

        webm = f"{args.out}.webm"
        run([FFMPEG, "-y", "-i", composite, "-c:v", "vp9", "-pix_fmt", "yuva420p",
             "-b:v", "0", "-crf", str(args.crf), webm])
        print(f"  transparent -> {webm}  (verify in a BROWSER, not ffmpeg)")

        if args.mp4:
            mp4 = f"{args.out}.mp4"
            run([FFMPEG, "-y", "-f", "lavfi", "-i",
                 f"color=c={args.bg}:s={w}x{h}:r={args.fps}", "-i", composite,
                 "-filter_complex", "[0][1]overlay=shortest=1,format=yuv420p",
                 "-c:v", "libx264", "-movflags", "+faststart", mp4])
            print(f"  opaque fallback -> {mp4}")

        if args.poster:
            poster = f"{args.out}.poster.png"
            run([FFMPEG, "-y", "-ss", str(args.poster_at), "-i", composite,
                 "-frames:v", "1", "-update", "1", poster])
            print(f"  poster -> {poster}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
