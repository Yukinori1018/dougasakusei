#!/usr/bin/env bash
set -euo pipefail
cd "/home/user/dougasakusei/projects/2026-05-11_invoice-keiakasochi-2026"

# Generate a concat list from current audio segments.
rm -f concat.txt
echo "file 'audio/user_segments/seg_000_RECORD_ME.wav'" >> concat.txt
echo "file 'audio/ai_segments/seg_001.wav'" >> concat.txt
echo "file 'audio/ai_segments/seg_002.wav'" >> concat.txt
echo "file 'audio/user_segments/seg_003_RECORD_ME.wav'" >> concat.txt
echo "file 'audio/ai_segments/seg_004.wav'" >> concat.txt
echo "file 'audio/ai_segments/seg_005.wav'" >> concat.txt
echo "file 'audio/user_segments/seg_006_RECORD_ME.wav'" >> concat.txt
echo "file 'audio/user_segments/seg_007_RECORD_ME.wav'" >> concat.txt
ffmpeg -y -f concat -safe 0 -i concat.txt -c copy mixed.audio.wav || true
# Burn subtitles onto a black frame as a quick preview; real B-roll happens in NLE.
ffmpeg -y -f lavfi -i color=c=black:s=1920x1080:r=30 -i mixed.audio.wav -vf "subtitles=subtitles/ja.srt" -shortest -c:v libx264 -c:a aac "preview.mp4"
