#!/usr/bin/env bash
# Lab probe: capture in-step CSS motion headlessly via Chrome --screenshot with
# rising --virtual-time-budget (deterministic), then assemble an ANIMATED narrated
# mp4 — each step plays its entry animation, then holds the settled frame for the
# rest of its OmniVoice narration. No live screen-record.
set -uo pipefail

PRES=/mnt/d/claudeprojects/nolan/web-video-lab/human-3.0/presentation
WPRES='D:/ClaudeProjects/NOLAN/web-video-lab/human-3.0/presentation'
CHROME="/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
FFMPEG="/mnt/d/env/nolan/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe"
FFPROBE="/mnt/c/Users/yuanp/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.0.1-full_build/bin/ffprobe.EXE"
WPROF='D:\ClaudeProjects\NOLAN\web-video-lab\human-3.0\presentation\dist\_prof'
CH=(hook one-map); CI=(0 1)
# virtual-time sample points (ms) — dense early where motion is fast; last = settled
TS=(0 70 150 250 370 510 680 880 1120 1400 1720 2100)

mkdir -p "$PRES/dist/_frames" "$PRES/.build"
# serve dist (localhost forwards to Windows Chrome)
( cd "$PRES/dist" && python3 -m http.server 5188 --bind 0.0.0.0 >/dev/null 2>&1 ) &
SRV=$!; sleep 1.5

echo "== capturing motion frames (12/step x 12 steps) =="
for idx in 0 1; do for s in 0 1 2 3 4 5; do
  c=${CI[$idx]}
  i=0
  for T in "${TS[@]}"; do
    "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run \
      --user-data-dir="$WPROF" --window-size=1920,1080 --virtual-time-budget="$T" \
      --screenshot="$WPRES/dist/_frames/c${c}s${s}_$(printf '%02d' $i).png" \
      "http://localhost:5188/?c=${c}&s=${s}" >/dev/null 2>&1
    i=$((i+1))
  done
  echo -n "c${c}s${s} "
done; done
echo ""
kill $SRV 2>/dev/null || true

echo "== build concat list with per-frame durations =="
VLIST="$PRES/.build/vlist_motion.txt"; WVLIST="$WPRES/.build/vlist_motion.txt"
: > "$VLIST"
DUR=(0.070 0.080 0.100 0.120 0.140 0.170 0.200 0.240 0.280 0.320 0.380)  # deltas T0..T10
for idx in 0 1; do
  c=${CI[$idx]}; ch=${CH[$idx]}
  for s in 0 1 2 3 4 5; do
    k=$((s+1))
    adur=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 \
      "$WPRES/public/audio/${ch}/${k}.mp3" | tr -d '\r')
    for i in 0 1 2 3 4 5 6 7 8 9 10; do
      printf "file '%s'\nduration %s\n" \
        "$WPRES/dist/_frames/c${c}s${s}_$(printf '%02d' $i).png" "${DUR[$i]}" >> "$VLIST"
    done
    hold=$(awk "BEGIN{h=$adur-2.1; print (h>0.1?h:0.1)}")
    printf "file '%s'\nduration %s\n" \
      "$WPRES/dist/_frames/c${c}s${s}_11.png" "$hold" >> "$VLIST"
  done
done
# repeat final frame (concat demuxer ignores its duration)
printf "file '%s'\n" "$WPRES/dist/_frames/c1s5_11.png" >> "$VLIST"

echo "== mux animated frames + narration -> mp4 =="
"$FFMPEG" -y -f concat -safe 0 -i "$WVLIST" -i "$WPRES/.build/full.mp3" \
  -vf "scale=1920:1080,format=yuv420p" -r 30 -c:v libx264 -preset medium -crf 20 \
  -c:a aac -b:a 192k -shortest "$WPRES/human-3.0_narrated_motion.mp4" >/dev/null 2>&1

echo "== done =="
"$FFPROBE" -v error -show_entries format=duration,size -of default=noprint_wrappers=1 \
  "$WPRES/human-3.0_narrated_motion.mp4"
ls -la "$PRES/human-3.0_narrated_motion.mp4"
