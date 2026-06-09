#!/usr/bin/env python3
"""Look at a video at the frame level so you can actually improve it.

Three modes (combine freely):
  --sheet            a contact sheet (frames tiled across the whole clip) -- the
                     fastest way to spot drift, flicker, fringe, broken transitions
  --at T [T ...]     grab full-res frames at exact timestamps (judge transitions)
  --over COLOR       composite an RGBA frame/dir over a flat colour to expose a
                     halo (white shows dark/coloured rims; magenta shows green spill)

Remember: ffmpeg CANNOT decode VP9-alpha for its own filters, so to check a
TRANSPARENT webm, open it in a browser. Use this script on the opaque mp4 (for
content) and on the matted RGBA PNGs (for edges). See references/inspection.md.

Usage:
  python inspect_video.py character.mp4 --sheet
  python inspect_video.py character.mp4 --at 4.5 9.0 13.5
  python inspect_video.py frame_0001.png --over magenta
  python inspect_video.py cut_frames/ --over white      # composites every PNG
"""
import argparse
import json
import os
import shutil
import subprocess
import sys


def find_tool(name, env_var):
    return shutil.which(name) or os.environ.get(env_var) or name


FFMPEG = find_tool("ffmpeg", "FFMPEG")
FFPROBE = find_tool("ffprobe", "FFPROBE")


def probe_duration(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", path],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def probe_dims(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    return int(s["width"]), int(s["height"])


def run(cmd):
    subprocess.run(cmd, check=True)


def contact_sheet(video, out, cols=5, rows=4):
    n = cols * rows
    dur = probe_duration(video)
    rate = max(n / dur, 0.0001)  # sample n frames across the whole duration
    vf = f"fps={rate:.5f},scale=240:-1,tile={cols}x{rows}"
    # -update 1: tell the image2 muxer this is a single image, not a sequence.
    run([FFMPEG, "-y", "-i", video, "-vf", vf, "-frames:v", "1", "-update", "1", out])
    print(f"  contact sheet -> {out}  ({n} frames across {dur:.1f}s)")


def grab(video, t, out):
    run([FFMPEG, "-y", "-ss", str(t), "-i", video, "-frames:v", "1", "-update", "1", out])
    print(f"  t={t}s -> {out}")


def over_color(img, color, out):
    w, h = probe_dims(img)
    run([FFMPEG, "-y", "-i", img, "-f", "lavfi", "-i", f"color={color}:s={w}x{h}",
         "-filter_complex", "[1][0]overlay=format=auto",
         "-frames:v", "1", "-update", "1", out])
    print(f"  {os.path.basename(img)} over {color} -> {out}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", help="a video (for --sheet/--at) or PNG/dir (for --over)")
    p.add_argument("--sheet", action="store_true", help="write a contact sheet")
    p.add_argument("--cols", type=int, default=5)
    p.add_argument("--rows", type=int, default=4)
    p.add_argument("--at", type=float, nargs="+", metavar="T",
                   help="grab full-res frames at these timestamps (seconds)")
    p.add_argument("--over", metavar="COLOR",
                   help="composite RGBA over this flat colour (white|magenta|...)")
    p.add_argument("--outdir", help="output dir (default: <input>_inspect/)")
    args = p.parse_args()

    base = os.path.splitext(os.path.basename(args.input.rstrip("/\\")))[0]
    outdir = args.outdir or f"{base}_inspect"
    os.makedirs(outdir, exist_ok=True)

    did = False
    if args.sheet:
        contact_sheet(args.input, os.path.join(outdir, f"{base}_sheet.png"),
                      args.cols, args.rows)
        did = True
    if args.at:
        for t in args.at:
            tag = str(t).replace(".", "p")  # avoid a dotted name looking like a pattern
            grab(args.input, t, os.path.join(outdir, f"{base}_t{tag}.png"))
        did = True
    if args.over:
        if os.path.isdir(args.input):
            pngs = sorted(f for f in os.listdir(args.input)
                          if f.lower().endswith(".png"))
            for f in pngs:
                over_color(os.path.join(args.input, f), args.over,
                           os.path.join(outdir, f"over_{args.over}_{f}"))
        else:
            over_color(args.input, args.over,
                       os.path.join(outdir, f"over_{args.over}_{base}.png"))
        did = True

    if not did:
        sys.exit("Pick at least one mode: --sheet, --at, or --over. See --help.")
    print(f"Done -> {outdir}")


if __name__ == "__main__":
    main()
