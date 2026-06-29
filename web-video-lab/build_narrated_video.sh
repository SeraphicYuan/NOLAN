#!/usr/bin/env bash
# Lab probe: assemble a narrated mp4 from the OmniVoice per-step wavs + the step
# frames. Each frame is held for exactly its narration's duration — reproducing
# the skill's audio-event sync ("step lasts as long as its clip") deterministically,
# no live screen-record. Uses Windows ffmpeg/ffprobe over WSL with D:/ paths.
set -euo pipefail

PRES=/mnt/d/claudeprojects/nolan/web-video-lab/human-3.0/presentation
WPRES='D:/ClaudeProjects/NOLAN/web-video-lab/human-3.0/presentation'
FFMPEG="/mnt/d/env/nolan/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe"
FFPROBE="/mnt/c/Users/yuanp/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.0.1-full_build/bin/ffprobe.EXE"

CH=(hook one-map)      # chapter ids (audio dir + wav prefix)
CI=(0 1)               # screenshot chapter index (c0/c1)

mkdir -p "$PRES/public/audio/hook" "$PRES/public/audio/one-map" "$PRES/.build"
VLIST="$PRES/.build/vlist.txt"; ALIST="$PRES/.build/alist.txt"
WVLIST="$WPRES/.build/vlist.txt"; WALIST="$WPRES/.build/alist.txt"
: > "$VLIST"; : > "$ALIST"

echo "== wav -> mp3 (skill layout) + collect durations =="
total=0
for idx in 0 1; do
  ch=${CH[$idx]}; ci=${CI[$idx]}
  for k in 1 2 3 4 5 6; do
    s=$((k-1))
    "$FFMPEG" -y -i "$WPRES/.tts_wav/${ch}_${k}.wav" -codec:a libmp3lame -q:a 2 \
      "$WPRES/public/audio/${ch}/${k}.mp3" >/dev/null 2>&1
    dur=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 \
      "$WPRES/public/audio/${ch}/${k}.mp3" | tr -d '\r')
    printf "file '%s'\nduration %s\n" "$WPRES/dist/_shots/c${ci}s${s}.png" "$dur" >> "$VLIST"
    printf "file '%s'\n" "$WPRES/public/audio/${ch}/${k}.mp3" >> "$ALIST"
    total=$(awk "BEGIN{print $total+$dur}")
    echo "  ${ch}/${k}: ${dur}s"
  done
done
# concat demuxer requires the final image repeated (its duration is ignored)
tail -2 "$VLIST" | head -1 >> "$VLIST"
echo "total ~${total}s"

echo "== concat audio =="
"$FFMPEG" -y -f concat -safe 0 -i "$WALIST" -codec:a libmp3lame -q:a 2 \
  "$WPRES/.build/full.mp3" >/dev/null 2>&1

echo "== mux frames (held to audio) + narration -> mp4 =="
"$FFMPEG" -y -f concat -safe 0 -i "$WVLIST" -i "$WPRES/.build/full.mp3" \
  -vf "scale=1920:1080,format=yuv420p" -r 30 -c:v libx264 -preset medium -crf 20 \
  -c:a aac -b:a 192k -shortest "$WPRES/human-3.0_narrated.mp4" >/dev/null 2>&1

echo "== done =="
"$FFPROBE" -v error -show_entries format=duration,size -of default=noprint_wrappers=1 \
  "$WPRES/human-3.0_narrated.mp4"
ls -la "$PRES/human-3.0_narrated.mp4"
