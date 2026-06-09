# nehorai-skills

Personal collection of [Claude Code](https://claude.com/claude-code) / Claude Agent
skills — reusable, self-documenting capabilities Claude can invoke across projects.

## Skills

| Skill | What it does |
|-------|--------------|
| [`ai-video-compositing`](ai-video-compositing/SKILL.md) | Post-production for AI-generated video clips: stitch clips into one seamless loop, matte the subject off its background (rembg over chroma key), kill the green/colour fringe, re-apply styles the model smoothed away, and inspect the result frame-by-frame. Bundles `matte_frames.py`, `loop_stitch.py`, `inspect_video.py`. |

## Install

Each skill is a self-contained folder (a `SKILL.md` plus `references/` and `scripts/`).

**User-level (available in every project):** copy the skill folder into your user
skills directory.

```bash
# macOS / Linux
cp -r ai-video-compositing ~/.claude/skills/
```

```powershell
# Windows
Copy-Item -Recurse ai-video-compositing "$env:USERPROFILE\.claude\skills\"
```

**Project-level (versioned with one project):** copy it into that project's
`.claude/skills/` instead.

Restart Claude Code (or reload skills) and the skill appears in the available-skills
list; Claude triggers it from its `description`.

## Notes

- Skills live under `~/.claude/skills/`, which is git-ignored by individual projects
  — this repo is the canonical, versioned source + backup for them.
- The `ai-video-compositing` scripts need `ffmpeg`/`ffprobe` on `PATH` (or set the
  `FFMPEG`/`FFPROBE` env vars), plus `pip install rembg onnxruntime pillow numpy`
  for matting.
