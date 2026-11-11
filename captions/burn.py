#!/usr/bin/env python3
"""
Burn "never say / say" style captions into a vertical video.

Look: white rounded box, bold black serif text, 2-5 words at a time, at chest
height. In "Never say X." the X phrase is red; in "Say Y." the Y phrase is green.

Usage:
  python burn.py --video in.mp4 --srt captions.srt --out out.mp4
  python burn.py --video in.mp4 --script script.txt --out out.mp4   # no SRT: times spread evenly

Requires: ffmpeg on PATH, Pillow.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(HERE, "fonts", "Lora-Variable.ttf")

BLACK = (17, 17, 17)
RED = (211, 47, 47)
GREEN = (46, 125, 50)
WHITE = (255, 255, 255)

SENTENCE_END = re.compile(r"[.!?]+[\"'”’)]*$")
QUOTE_CHARS = "\"“”"


# ---------------------------------------------------------------- input parsing

def parse_ts(ts):
    h, m, rest = ts.strip().split(":")
    s, ms = re.split(r"[,.]", rest)
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000.0


def read_srt(path):
    with open(path, encoding="utf-8-sig") as f:
        blocks = re.split(r"\n\s*\n", f.read().strip())
    cues = []
    for b in blocks:
        lines = [l for l in b.strip().splitlines() if l.strip()]
        tline = next((l for l in lines if "-->" in l), None)
        if not tline:
            continue
        a, b2 = tline.split("-->")
        text = " ".join(lines[lines.index(tline) + 1:])
        text = re.sub(r"<[^>]+>", "", text).strip()
        if text:
            cues.append((parse_ts(a), parse_ts(b2), text))
    return cues


def probe_duration(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", video],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def probe_size(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", video],
        capture_output=True, text=True, check=True).stdout.strip()
    w, h = out.split(",")[:2]
    return int(w), int(h)


def words_with_times(cues):
    """Spread each cue's time across its words, weighted by word length."""
    out = []
    for start, end, text in cues:
        words = text.split()
        if not words:
            continue
        weights = [len(w.strip(QUOTE_CHARS + ",.!?")) + 2 for w in words]
        total = float(sum(weights))
        t = start
        for w, wt in zip(words, weights):
            d = (end - start) * wt / total
            out.append([w, t, t + d])
            t += d
    return out


# ---------------------------------------------------------------- colouring

def norm(w):
    return re.sub(r"[^a-z']", "", w.lower().replace("’", "'"))


def assign_colors(words):
    """Red after 'never say' / 'don't say' until sentence end; green for a sentence starting with 'Say'."""
    colors = []
    mode = None
    sentence_start = True
    for i, w in enumerate(words):
        n = norm(w)
        prev = norm(words[i - 1]) if i > 0 else ""
        color = BLACK
        if mode:
            color = RED if mode == "red" else GREEN
        colors.append(color)
        # decide mode for following words
        if mode is None:
            if n == "say" and prev in ("never", "don't", "dont"):
                mode = "red"
            elif n == "say" and sentence_start:
                mode = "green"
        ends = bool(SENTENCE_END.search(w))
        if ends:
            # a sentence ending right after 'say' (e.g. "never say.") keeps nothing coloured
            mode = None
        sentence_start = ends
    return colors


# ---------------------------------------------------------------- chunking

def chunk_words(words, max_words=5, max_chars=24):
    """Group words into short on-screen chunks, breaking at sentence ends and colour changes."""
    chunks = []
    cur = []
    for i, item in enumerate(words):
        w = item[0]
        if cur:
            cur_text = " ".join(x[0] for x in cur)
            color_change = item[3] != cur[-1][3] and (item[3] == BLACK or cur[-1][3] == BLACK)
            too_long = len(cur) >= max_words or len(cur_text) + 1 + len(w) > max_chars
            if too_long or color_change:
                chunks.append(cur)
                cur = []
        cur.append(item)
        if SENTENCE_END.search(w) or (w.endswith(",") and len(cur) >= 2):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    # merge tiny single-word chunks that share colour with the next chunk
    merged = []
    for c in chunks:
        if merged and len(c) == 1 and len(merged[-1]) == 1 \
                and not SENTENCE_END.search(merged[-1][-1][0]) and c[0][3] == merged[-1][-1][3]:
            merged[-1].extend(c)
        else:
            merged.append(c)
    return merged


# ---------------------------------------------------------------- rendering

def load_font(size):
    f = ImageFont.truetype(FONT_PATH, size)
    try:
        f.set_variation_by_axes([700])
    except Exception:
        pass
    return f


def render_chunk(chunk, video_w, path):
    size = int(video_w * 0.06)
    font = load_font(size)
    pad_x, pad_y = int(size * 0.55), int(size * 0.32)
    space = font.getlength(" ")
    pieces = [(re.sub("[" + QUOTE_CHARS + "]", "", it[0]), it[3]) for it in chunk]
    pieces = [(t, c) for t, c in pieces if t]
    widths = [font.getlength(t) for t, _ in pieces]
    text_w = sum(widths) + space * (len(pieces) - 1)
    max_w = video_w * 0.86
    if text_w > max_w:  # shrink to fit
        size = int(size * max_w / text_w)
        font = load_font(size)
        space = font.getlength(" ")
        widths = [font.getlength(t) for t, _ in pieces]
        text_w = sum(widths) + space * (len(pieces) - 1)
    ascent, descent = font.getmetrics()
    box_w = int(text_w + 2 * pad_x)
    box_h = int(ascent + descent + 2 * pad_y)
    img = Image.new("RGBA", (box_w + 8, box_h + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # soft shadow, then box
    d.rounded_rectangle([4, 6, box_w + 4, box_h + 6], radius=int(box_h * 0.22), fill=(0, 0, 0, 60))
    d.rounded_rectangle([2, 2, box_w + 2, box_h + 2], radius=int(box_h * 0.22), fill=WHITE + (255,))
    x = 2 + pad_x
    y = 2 + pad_y
    for (t, c), wdt in zip(pieces, widths):
        d.text((x, y), t, font=font, fill=c + (255,))
        x += wdt + space
    img.save(path)
    return img.size


def build(video, out, cues, y_frac=0.44, keep_tmp=False):
    W, H = probe_size(video)
    words = words_with_times(cues)
    colors = assign_colors([w[0] for w in words])
    for w, c in zip(words, colors):
        w.append(c)
    chunks = chunk_words(words)
    tmp = tempfile.mkdtemp(prefix="caps_")
    overlays = []
    for i, ch in enumerate(chunks):
        p = os.path.join(tmp, f"c{i:03d}.png")
        cw, chh = render_chunk(ch, W, p)
        start = ch[0][1]
        end = chunks[i + 1][0][1] if i + 1 < len(chunks) else ch[-1][2]
        if end - ch[-1][2] > 0.6:  # don't hold a caption through a long pause
            end = ch[-1][2] + 0.25
        overlays.append((p, start, end, cw, chh))

    # ffmpeg filter graph: chain overlays, each enabled only in its window
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", video]
    for p, *_ in overlays:
        cmd += ["-i", p]
    parts = []
    last = "0:v"
    y = int(H * y_frac)
    for i, (p, s, e, cw, chh) in enumerate(overlays, start=1):
        tag = f"v{i}"
        parts.append(f"[{last}][{i}:v]overlay=x=(W-w)/2:y={y}-h/2:enable='between(t,{s:.3f},{e:.3f})'[{tag}]")
        last = tag
    filt = ";".join(parts) if parts else "[0:v]null[v0]"
    if not parts:
        last = "v0"
    script_path = os.path.join(tmp, "filter.txt")
    with open(script_path, "w") as f:
        f.write(filt)
    cmd += ["-filter_complex_script", script_path, "-map", f"[{last}]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    if not keep_tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    return len(overlays)


def cues_from_script(script_text, duration):
    """No SRT: spread the script evenly over the video (rough fallback)."""
    words = script_text.split()
    lead = 0.3
    span = max(duration - lead - 0.5, 1.0)
    return [(lead, lead + span, " ".join(words))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--srt")
    ap.add_argument("--script", help="text file; used only when no SRT is given")
    ap.add_argument("--y", type=float, default=0.44, help="vertical centre of captions (0-1 of height)")
    ap.add_argument("--keep-tmp", action="store_true")
    a = ap.parse_args()
    if a.srt:
        cues = read_srt(a.srt)
    elif a.script:
        with open(a.script, encoding="utf-8") as f:
            cues = cues_from_script(f.read(), probe_duration(a.video))
    else:
        sys.exit("give --srt or --script")
    n = build(a.video, a.out, cues, a.y, a.keep_tmp)
    print(f"burned {n} captions -> {a.out}")


if __name__ == "__main__":
    main()
