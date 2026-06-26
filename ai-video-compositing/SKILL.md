---
name: ai-video-compositing
description: >-
  Post-production for AI-generated video clips: stitch clips into one seamless
  (often looping) sequence with clean transitions, matte the subject off its
  background (green screen / studio backdrop) to float transparent, kill the
  green/colour edge fringe, re-apply a stylized look (pixel-art) the model
  smoothed away, and inspect frame-by-frame for flicker, identity drift, broken
  transitions, or wrong/black transparency. Use when ASSEMBLING or CLEANING UP
  already-generated video — Seedance/Kling/Veo/Runway/Sora clips, a
  character/avatar/talking-head loop — e.g. "stitch these AI clips into a loop",
  "make the character's background transparent", "remove the green screen from my
  video", "transparent webm shows black in ffmpeg", "the transition explodes /
  edges have a green halo", or building a transparent WebM (+MP4 fallback) for a
  site. NOT for generating the video/image/music/lip-sync or single-photo
  background removal (use a dedicated generation / kie.ai integration skill), nor
  ordinary non-AI editing (trim, plain concat, captions, colour grade).
---

# AI video compositing — stitch, matte, and inspect

AI video models give you **raw clips**, not a finished asset. The clip morphs
identity, the "green screen" isn't a clean key, style effects get smoothed away,
transitions explode, and the loop seam cuts. The work that makes it look
*intentional* happens in post. This skill is the hard-won recipe for that work,
organized around the three things that actually move the needle:

1. **Matting** — getting a clean transparent cutout of the subject.
2. **Stitching** — joining clips into one seamless (often looping) sequence.
3. **Inspection** — looking at the result at the frame level so you can improve it.

Most of the value is in *choosing the approach that works* rather than the first
one that seems obvious. The sections below lead with those decisions and the
reasoning, then point at the reference files and bundled scripts for execution.

## The one-screen decision cheatsheet

| Problem | The naive choice | What actually works | Why |
|---|---|---|---|
| Cut subject from background | chroma key (`chromakey`/`colorkey`) | **AI matting (`rembg`)** | AI backdrops are non-uniform (two-tone, gradients, a moving seam line). A key that's tight enough to keep them also eats skin/cloth; loose enough to remove them leaks at edges. Matting ignores the background entirely. |
| Green/colour halo at edges after matting | wider key / feather | **despill** (clamp the spill channel) | The halo is real spill *baked into edge pixels*, not a keying miss. Clamp green to `min(g, max(r,b))`. |
| Transition between clips | `xfade=transition=pixelize` (or other fancy xfades) | **alpha crossfade dissolve** | Many xfade transitions operate on opaque RGB and detonate at the midpoint (pixelize → giant blocks). Fade each clip's *alpha* in/out and overlay. |
| Loop seam | rely on `-stream_loop` / native `loop` | **make first frame ≈ last frame**, hard-cut the wrap | A dissolve across the wrap shows both ends at once. If the ends match (same style/pose), a hard cut is invisible. |
| Stylized look (pixel-art, halftone) lost | trust the model to keep it | **apply the style in POST** | Video models interpolate stylization away. Re-apply with ffmpeg (e.g. nearest-neighbour downscale/upscale for pixel-art). |
| Verify a transparent WebM | open it in ffmpeg / extract a frame | **check it in a browser** | ffmpeg can't decode VP9 side-data alpha for its own filters — it shows black/green even when the file is correct. Browsers honour it. |

If you remember nothing else: **matte with `rembg`, transition on alpha, match the
loop ends, style in post, and verify alpha in a browser.**

## Workflow

Think of it as a loop, not a line. You will inspect, find an artifact, fix one
stage, and re-inspect. Don't try to nail it in one pass.

1. **Plan the loop / sequence.** Decide the clip order and where each clip
   "dwells" vs "transitions". For a metamorphosis/style loop, design it so each
   clip *starts* in its dwell style and ends matching the next clip's start —
   see `references/stitching.md`.
2. **Matte each clip** to a transparent (RGBA) frame sequence. Use
   `scripts/matte_frames.py`. Add despill if edges are tinted. Details:
   `references/matting.md`.
3. **Stitch** the matted clips into one loop with alpha-dissolve transitions and
   a matched hard-cut wrap. Use `scripts/loop_stitch.py`. Details and the raw
   ffmpeg graph: `references/stitching.md` + `references/ffmpeg-recipes.md`.
4. **Encode for the web**: a VP9-alpha WebM (true transparency) plus an opaque
   MP4 fallback baked onto your page's background colour, plus a poster frame.
   See `references/ffmpeg-recipes.md`.
5. **Inspect frame-by-frame.** Build a contact sheet and pull frames at the
   transition timestamps with `scripts/inspect_video.py`; check transparency in
   a browser. Find the worst artifact, go back to the stage that owns it, fix,
   repeat. Details: `references/inspection.md`.

## Pillar 1 — Matting (background removal)

**Default to `rembg` AI matting, not chroma key.** Reach for a key *only* when the
background is a genuinely flat, uniform colour clearly separated from the
subject's colours — which AI-generated "green screens" usually are not.

Minimum viable pipeline:

```bash
# Matte a clip to an RGBA PNG sequence (reuses one model session — fast)
python scripts/matte_frames.py input.mp4 out_frames/ --despill
```

Why this and not a key, when despill matters, and the chroma-key fallback recipe
(for when you truly have a flat key) are all in **`references/matting.md`**.
`rembg` install: `pip install rembg onnxruntime`.

## Pillar 2 — Stitching into a seamless loop

The two failure modes are **transitions that explode** and **a visible loop seam**.
Both are solved by working on alpha and designing the ends to match.

```bash
# Stitch matted clips into one transparent loop (alpha dissolves + matched wrap)
python scripts/loop_stitch.py seg1_frames/ seg2_frames/ seg3_frames/ \
  --fps 24 --xfade 0.4 --out character.webm
```

The dwell-vs-transition loop design, alpha-dissolve vs xfade, `setpts`/`overlay`
graph, and how to make the wrap invisible are in **`references/stitching.md`**.

## Pillar 3 — Inspecting a video to improve it

You can't fix what you can't see. The single most useful artifact is a **contact
sheet** (frames tiled across the whole duration) — it reveals drift, flicker,
fringe, and broken transitions at a glance. Then pull full-res frames at the exact
transition timestamps to judge them.

```bash
python scripts/inspect_video.py character.mp4 --sheet --at 4.5 9.0 13.5
```

How to read a contact sheet, what each artifact class looks like and which stage
owns it, and the browser-vs-ffmpeg alpha-verification rule are in
**`references/inspection.md`**.

## Web delivery (if the target is a website)

- **Transparent**: VP9-alpha WebM (`-pix_fmt yuva420p`). Chrome/Firefox/Edge honour
  it. Safari does **not** decode VP9 alpha — it needs an HEVC-alpha `.mov`, which
  is not producible with stock ffmpeg on Windows.
- **Fallback**: an opaque MP4 with the subject baked onto the page's background
  colour, for engines without VP9 alpha. Offer both `<source>`s; the browser
  picks.
- **Poster**: a transparent PNG of a representative frame.
- **Cache-busting**: when you re-encode, bump a version query (`?v=N`) on the URL
  or the CDN/browser will keep serving the stale clip — a very common "my fix
  isn't showing up" trap.

Exact encode commands: `references/ffmpeg-recipes.md`.

## Environment gotchas

- **ffmpeg may not be on PATH** (e.g. installed via winget on Windows — the PATH
  isn't refreshed inside already-running tool shells). The scripts resolve ffmpeg
  via `shutil.which`, then the `FFMPEG`/`FFPROBE` env vars; set those to the full
  `...\bin\ffmpeg.exe` path if discovery fails.
- **rembg** downloads its model on first run; allow network + a minute. Reuse one
  session across frames (the bundled script does) — per-frame session creation is
  the difference between seconds and many minutes.
- **Verify transparency in a browser, not ffmpeg** (see the cheatsheet).

## Generic example pattern

A typical landing-page character loop can use this shape: 3 AI-generated clips
where each one is a dwell→morph segment, `rembg` matting per frame, despill,
alpha-dissolve stitching, a matched hard-cut wrap, VP9-alpha WebM, opaque MP4
fallback, and a transparent PNG poster.

Keep project-specific case studies, asset paths, and implementation manifests in
the project repository that owns those assets. This skill should stay generic and
portable so it can be shared without exposing personal or project-specific
context.
