# ffmpeg recipes (copy-paste, then adapt)

Concrete commands behind the workflow. The bundled scripts wrap most of these;
use these directly when you need to customize beyond the script flags.

Notation: `W`/`H` = output width/height, `FPS` = frame rate, `BG` = the page
background colour (e.g. `0x050e22`).

> **Finding ffmpeg**: if `ffmpeg` isn't on PATH (common after a winget install on
> Windows — running shells don't see the updated PATH), call it by full path, e.g.
> `C:\Users\<you>\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_*\...\bin\ffmpeg.exe`,
> or set `FFMPEG`/`FFPROBE` env vars (the scripts read those).

## Table of contents
- [Extract frames](#extract-frames)
- [Reassemble RGBA frames to video](#reassemble-rgba-frames-to-video)
- [Despill (green clamp)](#despill-green-clamp)
- [Pixel-art (nearest neighbour)](#pixel-art-nearest-neighbour)
- [Alpha-dissolve stitch (the assembly graph)](#alpha-dissolve-stitch-the-assembly-graph)
- [Encode: transparent WebM + opaque fallback + poster](#encode-transparent-webm--opaque-fallback--poster)
- [Chroma-key fallback](#chroma-key-fallback)
- [Inspection: contact sheet, frame grabs, flat composites](#inspection-contact-sheet-frame-grabs-flat-composites)

## Extract frames

```bash
ffmpeg -i input.mp4 -vsync 0 frames/%04d.png            # all frames, lossless PNG
ffmpeg -i input.mp4 -r FPS frames/%04d.png              # force a frame rate
```

## Reassemble RGBA frames to video

```bash
ffmpeg -framerate FPS -i frames_cut/%04d.png -c:v vp9 -pix_fmt yuva420p out.webm
```

PNG sequences preserve alpha losslessly between stages — prefer them over an
intermediate alpha video.

## Despill (green clamp)

Per frame or in a filter chain. Wherever green dominates, pull it to `max(r,b)`:

```
geq=r='r(X,Y)':g='if(gt(g(X,Y),max(r(X,Y),b(X,Y))),max(r(X,Y),b(X,Y)),g(X,Y))':b='b(X,Y)':a='alpha(X,Y)'
```

Blue screen → clamp blue instead; mutatis mutandis for other backdrops.

## Pixel-art (nearest neighbour)

Apply on the matted RGBA, only to the clip that should be pixelated:

```
scale=110:-1:flags=neighbor,scale=W:H:flags=neighbor
```

110 = chunk size; tune. Keep it off the dissolve windows (see stitching.md — style
bleed).

## Alpha-dissolve stitch (the assembly graph)

Three matted clips (already RGBA), dwell ~`D`s each, crossfade `X`s, onto a
transparent base. Clip k offset `t_k = k*(D - X)`. Schematic:

```bash
ffmpeg \
  -i seg1.webm -i seg2.webm -i seg3.webm \
  -filter_complex "
    color=c=black@0.0:s=WxH:r=FPS,format=rgba,trim=duration=TOTAL[base];
    [0]format=rgba,fade=t=out:st=ST1:d=X:alpha=1,setpts=PTS-STARTPTS[c0];
    [1]format=rgba,fade=t=in:st=0:d=X:alpha=1,fade=t=out:st=ST2:d=X:alpha=1,setpts=PTS-STARTPTS+T1/TB[c1];
    [2]format=rgba,fade=t=in:st=0:d=X:alpha=1,setpts=PTS-STARTPTS+T2/TB[c2];
    [base][c0]overlay[o0];[o0][c1]overlay[o1];[o1][c2]overlay[out]
  " -map "[out]" -c:v vp9 -pix_fmt yuva420p character.webm
```

Replace `ST*`, `T1/T2` (clip offsets in seconds), `TOTAL`, `WxH`, `FPS`, `X`.
`scripts/loop_stitch.py` computes these from `--fps`/`--xfade` and the per-clip
frame counts so you don't hand-math them. The loop **wrap** is a hard cut (no fade
between the last clip's end and the first clip's start) — keep those frames
matched in style/pose.

## Encode: transparent WebM + opaque fallback + poster

```bash
# Transparent (Chrome/FF/Edge). yuva420p carries alpha; the file gets alpha_mode=1.
ffmpeg -i composite.mov -c:v vp9 -pix_fmt yuva420p -b:v 0 -crf 30 character.webm

# Opaque MP4 fallback: bake the composite over the page background colour.
ffmpeg -f lavfi -i color=c=BG:s=WxH:r=FPS -i composite.mov \
  -filter_complex "[0][1]overlay=shortest=1,format=yuv420p" \
  -c:v libx264 -movflags +faststart character.mp4

# Poster: one representative transparent frame.
ffmpeg -i composite.mov -ss 2.0 -frames:v 1 character.poster.png
```

Safari note: VP9 alpha is **not** decoded by Safari; true Safari transparency
needs an HEVC-alpha `.mov` (not producible with stock ffmpeg on Windows). Without
it, Safari falls back to the opaque MP4 (shows the baked background).

## Chroma-key fallback

Only when the backdrop is genuinely flat (see matting.md). Chain narrow keys +
hard key + 1px erosion:

```
chromakey=0x3E9941:0.12:0.03,chromakey=0x16D722:0.12:0.03,chromakey=0x2FB835:0.12:0.03,
split[a][b];[a]alphaextract,erosion[e];[b][e]alphamerge
```

Sample real background hex from extracted frames; don't guess.

## Inspection: contact sheet, frame grabs, flat composites

```bash
# Contact sheet (5 cols, frames every ~1s) — tile thumbnails of the whole clip.
ffmpeg -i input.mp4 -vf "fps=1,scale=240:-1,tile=5x4" -frames:v 1 sheet.png

# Grab a frame at an exact time.
ffmpeg -ss 9.0 -i input.mp4 -frames:v 1 at_9s.png

# Expose fringe: composite an RGBA frame over magenta (green spill) or white.
ffmpeg -i frame.png -f lavfi -i color=magenta:s=WxH \
  -filter_complex "[1][0]overlay=format=auto" -frames:v 1 over_magenta.png
```

`scripts/inspect_video.py` wraps the sheet/grab/flat-composite cases.
