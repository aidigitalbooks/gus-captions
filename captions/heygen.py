#!/usr/bin/env python3
"""
Small HeyGen helper (stdlib only).

  python heygen.py list-new --prefix "Gus" --hours 48     -> prints completed video IDs, one per line
  python heygen.py fetch VIDEO_ID --out work/             -> downloads video.mp4 (+ captions.srt if available)

Needs env var HEYGEN_API_KEY.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

API = "https://api.heygen.com"


def call(path):
    key = os.environ.get("HEYGEN_API_KEY")
    if not key:
        sys.exit("HEYGEN_API_KEY is not set")
    req = urllib.request.Request(API + path, headers={"X-Api-Key": key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "gus-captions/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)


def to_epoch(v):
    if v is None:
        return None
    try:
        v = float(v)
        return v / 1000.0 if v > 1e12 else v
    except (TypeError, ValueError):
        return None


def list_new(prefix, hours):
    cutoff = time.time() - hours * 3600
    data = call("/v1/video.list").get("data") or {}
    videos = data.get("videos") or data.get("list") or []
    for v in videos:
        vid = v.get("video_id") or v.get("id")
        title = v.get("video_title") or v.get("title") or ""
        status = (v.get("status") or "").lower()
        created = to_epoch(v.get("created_at"))
        if not vid or status != "completed":
            continue
        if prefix and not title.lower().startswith(prefix.lower()):
            continue
        if created is not None and created < cutoff:
            continue
        print(vid)


def fetch(video_id, out):
    os.makedirs(out, exist_ok=True)
    d = call(f"/v1/video_status.get?video_id={video_id}").get("data") or {}
    if (d.get("status") or "").lower() != "completed":
        sys.exit(f"video {video_id} is not completed (status={d.get('status')})")
    video_url = d.get("video_url")
    if not video_url:
        sys.exit("no video_url in HeyGen response")
    download(video_url, os.path.join(out, "video.mp4"))
    srt_url = d.get("caption_url") or d.get("subtitle_url")
    if srt_url:
        download(srt_url, os.path.join(out, "captions.srt"))
        print("downloaded video + captions")
    else:
        print("downloaded video (no caption file from HeyGen)")
    title = d.get("video_title") or d.get("title") or lookup_title(video_id)
    with open(os.path.join(out, "meta.json"), "w") as f:
        # "untitled" never matches the Gus prefix, so the relay skips videos it can't identify
        json.dump({"video_id": video_id, "title": title or "untitled",
                   "duration": d.get("duration")}, f)


def lookup_title(video_id):
    """video_status.get doesn't always include the title; find it in the video list."""
    token = None
    for _ in range(10):  # up to ~10 pages of recent videos
        path = "/v1/video.list" + (f"?token={token}" if token else "")
        try:
            data = call(path).get("data") or {}
        except Exception:
            return ""
        for v in data.get("videos") or data.get("list") or []:
            if (v.get("video_id") or v.get("id")) == video_id:
                return v.get("video_title") or v.get("title") or ""
        token = data.get("token")
        if not token:
            break
    return ""


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("list-new")
    a.add_argument("--prefix", default="Gus")
    a.add_argument("--hours", type=float, default=48)
    b = sub.add_parser("fetch")
    b.add_argument("video_id")
    b.add_argument("--out", default="work")
    args = ap.parse_args()
    if args.cmd == "list-new":
        list_new(args.prefix, args.hours)
    else:
        fetch(args.video_id, args.out)


if __name__ == "__main__":
    main()
