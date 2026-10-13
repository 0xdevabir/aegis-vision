# Demo assets for graduation defense

Place short MP4 clips here for reliable demo playback.

## Recommended clips (30–60 seconds each)

1. **sample.mp4** — person walking through gate (triggers detection)
2. **watchlist.mp4** — known person from `data/watchlist/`
3. **vehicle.mp4** — vehicle for ANPR demo (optional)

## Usage

```bash
# Primary defense demo (always works, no camera needed)
python main.py --video data/demo/clips/sample.mp4

# Performance evaluation for thesis
python scripts/evaluate_pipeline.py --video data/demo/clips/sample.mp4 --frames 200 --output data/results/eval.json
```

## Tips

- Record clips at the same resolution you will present (720p or 1080p)
- Keep file sizes under 50 MB for fast loading
- Test the full flow 24 hours before defense
