# Inspection — evaluating a video at the frame level so you can improve it

You cannot fix what you cannot see, and playback at speed hides almost every
artifact. Slow down and look at frames. This is the step people skip and then
wonder why the clip "feels off".

## Table of contents
- [The contact sheet: your primary instrument](#the-contact-sheet-your-primary-instrument)
- [Inspect the transition timestamps at full res](#inspect-the-transition-timestamps-at-full-res)
- [Verifying transparency: browser, not ffmpeg](#verifying-transparency-browser-not-ffmpeg)
- [Composite over flat colours to expose fringe](#composite-over-flat-colours-to-expose-fringe)
- [Artifact → which stage owns it](#artifact--which-stage-owns-it)

## The contact sheet: your primary instrument

A **contact sheet** — frames sampled evenly across the whole duration and tiled
into one image — is the fastest way to see drift, flicker, fringe, and broken
transitions at a glance.

```bash
python scripts/inspect_video.py character.mp4 --sheet
```

Scan it for: the subject's **identity/pose drifting** between clips; **flicker**
(a frame that jumps brightness/colour); a **green/colour halo** on the silhouette;
**transition frames** that look exploded, muddy, or doubled; the **loop wrap**
looking like a jump.

## Inspect the transition timestamps at full res

Transitions are where things break, and they're brief — a contact sheet may
straddle them. Pull the exact boundary frames full-size:

```bash
python scripts/inspect_video.py character.mp4 --at 4.5 9.0 13.5
```

Judge: does the style change land *as a beat* or as an *ugly cut*? Is there a
midpoint frame where both styles/poses are visible at once (a dissolve across a
mismatched boundary)? Are pixel blocks bleeding into a smooth clip?

## Verifying transparency: browser, not ffmpeg

**ffmpeg cannot decode VP9 side-data alpha for its own filters.** If you overlay a
VP9-alpha WebM onto a background in ffmpeg, or extract a frame from it, you'll see
**black or green where it should be transparent** — even when the file is
perfectly correct. This trap eats hours.

Rules:
- To check a **transparent WebM**, load it in a real browser over the actual
  background it'll sit on. That is the authoritative test.
- For **content** checks (is the motion right? is the figure centered?), scan the
  **opaque MP4 fallback** — ffmpeg decodes it fine.
- For **alpha-edge/fringe** checks, inspect the **RGBA PNG frame sequence** from
  the matting stage (PNG alpha is universally readable), or composite those PNGs
  over flat colours (below).

If you have a preview/dev server, drive it and screenshot in the browser to prove
the transparent asset renders correctly over the page background.

## Composite over flat colours to expose fringe

A halo invisible over a busy background screams over a flat one. Composite the
matted RGBA over **white** and over **magenta** (or any colour complementary to
the fringe) and look at the silhouette:

```bash
# (inspect_video.py --over white|magenta on a frames dir, or an ffmpeg one-liner)
ffmpeg -i frame_0001.png -f lavfi -i color=magenta:s=WxH -filter_complex \
  "[1][0]overlay=format=auto" -frames:v 1 over_magenta.png
```

White exposes dark/coloured rims; magenta exposes green spill specifically. If you
see a rim, that's a despill (not a re-key) job — see `references/matting.md`.

## Artifact → which stage owns it

Diagnose by symptom so you fix the right stage instead of thrashing:

| What you see | Owning stage | Fix |
|---|---|---|
| Green/colour rim on silhouette | Matting | Add/strengthen **despill**; don't widen a key. |
| Chunks/blocks in a clip that should be smooth | Stitching (style bleed) | Apply the style filter only to its own clip, on RGBA, away from the dissolve. |
| Midpoint frame shows two poses/styles at once | Stitching (transition) | Boundary frames don't match, or you dissolved a mismatch — match ends, or hard-cut. |
| Subject's face/outfit changes between clips | Generation | Re-generate with stronger identity/outfit refs (a *visual* reference, not just words). Post can't fix identity drift. |
| Jittery / too-fast motion | Generation | Use the model's standard (not "fast") mode; ask for subtle natural motion. |
| Background box visible on a textured page | Delivery | You shipped the opaque (baked) variant; ship the **alpha WebM** and confirm in-browser. |
| "My fix isn't showing up" | Delivery (cache) | Bump the cache-busting version on the asset URL. |

The throughline: **identity/motion problems are generation problems** (re-roll the
clip), **fringe is a matting problem** (despill), **explosions/double-images are
stitching problems** (alpha + matched ends), and **boxes/staleness are delivery
problems** (alpha variant + cache-bust).
