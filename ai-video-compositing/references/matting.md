# Matting — cutting the subject out of its background

## Table of contents
- [Why AI matting beats chroma key here](#why-ai-matting-beats-chroma-key-here)
- [The rembg recipe](#the-rembg-recipe)
- [Despill — killing the colour fringe](#despill--killing-the-colour-fringe)
- [When a chroma key IS the right tool](#when-a-chroma-key-is-the-right-tool)
- [Chroma-key fallback recipe](#chroma-key-fallback-recipe)

## Why AI matting beats chroma key here

Chroma keying assumes the background is **one flat, uniform colour** that is
**well separated** from every colour in the subject. AI-generated "green screens"
violate both assumptions, and you usually only discover it after a key looks
almost-right and then fails at the edges or eats part of the subject:

- **Non-uniform background.** The model renders a *two-tone* green (a brighter
  "wall" and a muted "floor"), often with a gradient and a neutral **studio seam
  line** where they meet. In a style morph (e.g. realistic→pixel) that seam
  line's position is **interpolated between keyframes, so it MOVES** frame to
  frame. A fixed key can't track it; `delogo` at a fixed Y can't either.
- **Colour collisions.** Low-chroma clothing (a pale-blue shirt, beige chinos)
  sits close to green in YUV. A key wide enough to remove a muddy floor-green
  also bites those garments. A teal/cyan jacket is *very* close to green and is
  the first thing a wide key destroys.

The result: there is no single key width that both fully removes the background
and fully preserves the subject. You end up chaining multiple narrow keys plus
alpha erosion and *still* get a halo. **AI matting sidesteps all of it** by
segmenting the *person* and ignoring whatever is behind them. It works equally on
realistic, pixel-art, and anime renders of the same character.

The cost: matting can keep a thin rim of background-tinted antialiased pixels at
the silhouette. That's what **despill** is for (below) — it's a much smaller,
better-behaved problem than keying a moving seam.

## The rembg recipe

`rembg` with the human-segmentation model is the workhorse.

```bash
pip install rembg onnxruntime
python scripts/matte_frames.py input.mp4 out_frames/ --despill
```

Key choices baked into `scripts/matte_frames.py`, and why:

- **Model `u2net_human_seg`** — tuned for people; cleaner than the generic
  `u2net` on figures, across art styles.
- **`post_process_mask=True`** — smooths the alpha edge and removes speckle.
- **One reused session for all frames.** Creating a `new_session()` per frame
  reloads the model each time — that's the difference between ~seconds and
  ~minutes for a few hundred frames. Create it once, loop.
- **Frame sequence, not a single video call.** Extract → matte per frame → keep
  as an RGBA PNG sequence. PNG preserves alpha losslessly for the stitch step;
  re-encoding to an alpha video between stages risks alpha damage.

If you have a frames directory already, point the script at it instead of a video.

## Despill — killing the colour fringe

After matting you may see a faint green (or whatever the backdrop was) rim on the
silhouette. This is **spill light baked into edge pixels**, not a keying error, so
widening anything won't help — you have to *neutralise the spill channel*.

Green-clamp despill: wherever green dominates, pull it down to the larger of red
and blue, leaving genuinely green/teal subject regions mostly intact.

```
geq=r='r(X,Y)':g='if(gt(g(X,Y),max(r(X,Y),b(X,Y))),max(r(X,Y),b(X,Y)),g(X,Y))':b='b(X,Y)':a='alpha(X,Y)'
```

`scripts/matte_frames.py --despill` applies this per frame. To despill a
different backdrop colour, clamp the corresponding channel (blue-clamp for a blue
screen, etc.). **Verify despill over a contrasting flat colour** (composite the
RGBA over solid white and magenta) so the rim is obvious — see
`references/inspection.md`.

Watch out: aggressive despill can desaturate a subject that is legitimately the
spill colour (a teal jacket under green-clamp). The `min(g, max(r,b))` form is
deliberately gentle; check the subject's own colours survive.

## When a chroma key IS the right tool

Use a key, not matting, when **all** of these hold:

- The background is a single, flat, evenly-lit colour with no seam/gradient.
- No subject colour is near the key colour.
- You control generation and can *demand* a flat uniform backdrop ("flat uniform
  #00FF00, no floor, no wall seam, even lighting").
- Speed matters and you can't run a model per frame.

In that clean case a key is faster and sharper than matting. The trouble is only
that AI generators rarely give you that clean case unless you ask explicitly.

## Chroma-key fallback recipe

If you must key (kept from a real project, for the non-uniform case where matting
wasn't available):

- **Chain several NARROW keys**, one per green shade present, instead of one wide
  key. Each segment's background green also drifts toward the next style's green
  during a morph, so keys leak exactly at transitions — cover the whole range
  with tight keys:
  ```
  chromakey=0x3E9941:0.12:0.03,chromakey=0x16D722:0.12:0.03,chromakey=0x2FB835:0.12:0.03
  ```
- **Hard key (blend 0) + 1px alpha erosion** to remove the halo:
  ```
  split[a][b];[a]alphaextract,erosion[e];[b][e]alphamerge
  ```
- Sample the actual background pixel colours from a few frames (don't guess the
  hex) — pull frames with `scripts/inspect_video.py` and read the values.

This is the fallback. If you find yourself chaining three keys plus erosion and
still fighting a halo, that's the signal to switch to `rembg`.
