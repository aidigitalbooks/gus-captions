# Gus captions

Automatically burns "never say / say" captions into Gus Kessler's HeyGen videos.

- White rounded box, bold black serif text (Lora), 2–5 words at a time, at chest height
- In "Never say X." the X phrase is **red**; in "Say Y." the Y phrase is **green**
- Timing comes from the caption file (SRT) HeyGen makes with every video
- Each finished video is published as a GitHub Release with a public MP4 link you can give to Metricool

Runs on GitHub Actions (free for public repos). A tiny Cloudflare Worker (`relay/worker.js`) starts it the moment HeyGen finishes a video.

## One-time setup (about 10 minutes)

1. **Create a GitHub account** at github.com if you don't have one.
2. **Create a new repository** named `gus-captions`, set to **Public**. (Public keeps Actions free and makes the video links work in Metricool. Your API key stays private in Secrets.)
3. **Upload these files**: on the new repo page click **Add file → Upload files**, drag in everything from this folder (including the hidden `.github` folder — if your computer hides it, upload `caption.yml` into a folder you create at `.github/workflows/`), then **Commit changes**.
4. **Add your HeyGen API key**: in HeyGen go to **Settings → API** and copy your key. In GitHub go to **Settings → Secrets and variables → Actions → New repository secret**, name it `HEYGEN_API_KEY`, paste the key, save.
5. **Allow releases**: GitHub **Settings → Actions → General → Workflow permissions** → choose **Read and write permissions** → Save.

Then set up the Cloudflare relay (see the setup guide in chat) so captioning starts as soon as HeyGen finishes. As a safety net, the workflow also checks once a day for any **Gus** video it missed.

## Running it

- **Automatic:** make Gus videos in HeyGen with a title starting with "Gus". A few minutes after HeyGen finishes, the captioned version appears under **Releases**. Videos for other personas are skipped.
- **Right now, one video:** **Actions → Caption Gus videos → Run workflow**, paste the HeyGen video ID, Run.
- **No HeyGen API key?** Use **Run workflow** with `video_url` (the MP4 link) and `srt_url` (the caption file link) instead.

The finished link looks like:
`https://github.com/<you>/gus-captions/releases/download/video-<id>/gus-<id>.mp4`

## Optional settings (Settings → Secrets and variables → Actions → Variables)

| Variable | Default | What it does |
|---|---|---|
| `TITLE_PREFIX` | `Gus` | Only videos whose title starts with this are captioned |
| `CAPTION_Y` | `0.44` | Caption height (0 = top, 1 = bottom) |

Secret `NOTIFY_WEBHOOK` (optional): a URL (e.g. a Make or Zapier webhook) that receives `{"id","title","url"}` for each finished video, so the next step (like scheduling in Metricool) can run automatically.

## Run it on your own computer

```
pip install pillow        # and install ffmpeg
python captions/burn.py --video in.mp4 --srt captions.srt --out out.mp4
```

Font: Lora (SIL Open Font License).
