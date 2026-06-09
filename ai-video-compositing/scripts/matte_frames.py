#!/usr/bin/env python3
"""Matte a clip (or a folder of frames) to a transparent RGBA PNG sequence.

Uses rembg AI matting (model u2net_human_seg, post_process_mask) with ONE reused
session for the whole run -- per-frame session creation is the difference between
seconds and many minutes. Optionally despills a colour fringe left on the edges.

Why matting and not chroma key: AI-generated backdrops are rarely a flat, uniform
key colour (two-tone greens, gradients, a moving studio seam). See
references/matting.md for the full reasoning and the chroma-key fallback.

Usage:
  pip install rembg onnxruntime pillow numpy
  python matte_frames.py input.mp4 out_frames/            # video -> RGBA PNGs
  python matte_frames.py input.mp4 out_frames/ --despill  # + green-clamp despill
  python matte_frames.py in_frames/ out_frames/ --despill  # an existing frame dir
  python matte_frames.py input.mp4 out/ --fps 24 --despill-channel blue

Outputs %04d.png (RGBA) into the output dir, ready for loop_stitch.py.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile


def find_tool(name, env_var):
    """Resolve ffmpeg/ffprobe via PATH then an env override (Windows winget trap)."""
    return shutil.which(name) or os.environ.get(env_var) or name


FFMPEG = find_tool("ffmpeg", "FFMPEG")

FRAME_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


def extract_frames(video, out_dir, fps=None):
    os.makedirs(out_dir, exist_ok=True)
    cmd = [FFMPEG, "-y", "-i", video]
    if fps:
        cmd += ["-r", str(fps)]
    else:
        cmd += ["-vsync", "0"]
    cmd += [os.path.join(out_dir, "%04d.png")]
    subprocess.run(cmd, check=True)
    return sorted(
        os.path.join(out_dir, f) for f in os.listdir(out_dir)
        if f.lower().endswith(".png")
    )


def list_frames(d):
    return sorted(
        os.path.join(d, f) for f in os.listdir(d)
        if f.lower().endswith(FRAME_EXTS)
    )


def despill(img, channel="green"):
    """Clamp the spill channel so it never dominates: c = min(c, max(other two)).

    Removes a backdrop-colour halo baked into antialiased edge pixels without
    destroying subject regions that are genuinely that colour-ish.
    """
    import numpy as np

    a = np.asarray(img.convert("RGBA")).astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    idx = {"red": 0, "green": 1, "blue": 2}[channel]
    others = [c for i, c in enumerate((r, g, b)) if i != idx]
    cap = np.maximum(others[0], others[1])
    a[..., idx] = np.minimum(a[..., idx], cap)
    from PIL import Image

    return Image.fromarray(a.astype("uint8"), "RGBA")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", help="video file OR a directory of frames")
    p.add_argument("out_dir", help="output dir for the RGBA PNG sequence")
    p.add_argument("--model", default="u2net_human_seg",
                   help="rembg model (default: u2net_human_seg, tuned for people)")
    p.add_argument("--fps", type=float, default=None,
                   help="frame rate when extracting from a video (default: native)")
    p.add_argument("--despill", action="store_true",
                   help="clamp the spill channel to remove an edge colour halo")
    p.add_argument("--despill-channel", default="green",
                   choices=["green", "blue", "red"],
                   help="which backdrop colour to despill (default: green)")
    args = p.parse_args()

    try:
        from rembg import remove, new_session
        from PIL import Image
    except ImportError:
        sys.exit("Missing deps. Run: pip install rembg onnxruntime pillow numpy")

    # Gather input frames (extracting from video into a temp dir if needed).
    tmp = None
    if os.path.isdir(args.input):
        frames = list_frames(args.input)
        if not frames:
            sys.exit(f"No frames found in {args.input}")
    else:
        tmp = tempfile.mkdtemp(prefix="matte_extract_")
        frames = extract_frames(args.input, tmp, args.fps)

    os.makedirs(args.out_dir, exist_ok=True)
    session = new_session(args.model)  # created ONCE, reused for every frame
    n = len(frames)
    print(f"Matting {n} frames with {args.model}"
          f"{' + despill' if args.despill else ''} ...")

    for i, src in enumerate(frames, 1):
        img = Image.open(src).convert("RGBA")
        cut = remove(img, session=session, post_process_mask=True)
        if args.despill:
            cut = despill(cut, args.despill_channel)
        cut.save(os.path.join(args.out_dir, f"{i:04d}.png"))
        if i % 25 == 0 or i == n:
            print(f"  {i}/{n}")

    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"Done -> {args.out_dir}  (verify edges over flat colours; see "
          f"references/inspection.md)")


if __name__ == "__main__":
    main()
