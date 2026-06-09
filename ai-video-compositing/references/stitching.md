# Stitching — joining clips into one seamless (looping) sequence

## Table of contents
- [Design the loop before you cut a frame](#design-the-loop-before-you-cut-a-frame)
- [Transitions: alpha dissolve, not fancy xfades](#transitions-alpha-dissolve-not-fancy-xfades)
- [Making the loop seam invisible](#making-the-loop-seam-invisible)
- [Re-applying a lost style in post](#re-applying-a-lost-style-in-post)
- [The assembly graph](#the-assembly-graph)

## Design the loop before you cut a frame

The biggest lever is structural, decided up front: **dwell vs transition**.

A first/last-frame video model (Seedance, Kling, etc.) does **not** smoothly morph
an *extreme* style jump across the whole clip. Instead the whole clip renders in
the **start frame's style**, and only the last moment snaps toward the target.
Rather than fight this, exploit it:

- Make each clip a **dwell→transition** segment: it lives in style A for most of
  its duration, then pops toward style B at the very end. The pop reads as an
  intentional "transformation beat".
- Make **segment N's last frame == segment N+1's first frame** (literally the
  same keyframe image fed to both generations). Then the clips stitch with no
  visible jump — the styles already line up at the boundary.
- For a **loop**, close the ring: the last segment ends back at the first
  segment's start style. Example 3-segment loop:
  `realistic-dwell→pixel`, `pixel-dwell→anime`, `anime-dwell→realistic`. The wrap
  (anime→…→realistic back to realistic) is then realistic↔realistic — trivially
  seamless.

This single decision is why the result looks like one continuous metamorphosis
instead of three clips taped together.

## Transitions: alpha dissolve, not fancy xfades

`xfade=transition=pixelize` (and several other xfade modes) operate on **opaque
RGB** and detonate at the midpoint — pixelize blows the whole frame into giant
blocks that read as "stuck / broken". Once your clips are matted to alpha, you
don't need xfade at all.

**Fade each clip's alpha** in and out at the boundaries and `overlay` them onto a
transparent base, offsetting each with `setpts`:

- Clip k starts at `t_k = k * (dwell + xfade_overlap_adjust)`.
- `fade=t=in:alpha=1` at clip start (except the first), `fade=t=out:alpha=1`
  before its end (except the last) — overlap windows = your crossfade duration.
- `overlay` clip k over the running composite at its `setpts` offset.

The dissolve happens in the alpha channel, so it cross-dissolves the *cutouts*
cleanly with no RGB artifact. `scripts/loop_stitch.py` builds this graph for you;
the raw filtergraph is in `references/ffmpeg-recipes.md`.

If your subject is **not** matted (you genuinely want a rectangular crossfade),
prefer the plain `xfade=transition=fade` (a straight dissolve) over the decorative
modes — those are the ones that explode.

## Making the loop seam invisible

A loop has one extra cut the linear case doesn't: the **wrap** from the last frame
back to the first. Two rules:

1. **Match the ends.** If the first and last frames are the same style and near
   the same pose, the wrap is invisible — see the loop design above. This is 90%
   of the battle.
2. **Hard-cut the wrap, don't dissolve it.** A crossfade across the wrap would
   blend the end *and* the beginning on screen simultaneously (you'd see the
   subject "ghost"). With matched ends a hard cut has nothing to hide.

Also handle playback wrap in code if you're driving events off the video: native
`loop` doesn't reliably fire `seeking`/`play`, so detect the wrap yourself
(playhead jumped backward) and reset any per-cycle state.

## Re-applying a lost style in post

Video models smooth away crisp stylization (pixel-art, hard cel edges, halftone).
If a "pixel world" came back smoothed, **re-apply the style with ffmpeg** rather
than re-generating:

- **Pixel-art**: nearest-neighbour downscale then upscale:
  `scale=110:-1:flags=neighbor,scale=W:H:flags=neighbor` (110 = the chunk size;
  tune it — too small reads as noise, too large erases the figure).

Two cautions learned the hard way:
- **Apply the style on the matted RGBA, and only to the clip that should have it.**
  If you pixelate before/around a dissolve, the blocks **bleed into the adjacent
  clip** during the crossfade (a smooth anime frame picking up pixel chunks).
- **Don't over-do it.** Very chunky pixelation looked broken; a moderate size that
  preserved the silhouette read as intentional. When in doubt, less.

If a truly crisp stylized world matters and post-pixelation looks rough,
regenerate that segment with a model/setting that preserves the style in motion —
but try post first; it's far cheaper.

## The assembly graph

One ffmpeg invocation does the whole stitch: N matted inputs → (optional
per-clip style filter) → per-clip alpha fades + `setpts` offsets → `overlay`
chain on a transparent base → encode. Produce three outputs from it:

- the transparent **VP9-alpha WebM** (`-pix_fmt yuva420p`),
- an opaque **MP4 fallback** (overlay the same composite on a solid background
  colour matching the destination page),
- a **poster** PNG (one representative keyed frame).

`scripts/loop_stitch.py` emits all three. The exact commands and the hand-written
filtergraph are in `references/ffmpeg-recipes.md` for when you need to customize
beyond the script's flags.
