# Pitchroom feature film

The homepage's narrated product tour is rendered from `src/scenes.json` with the same local Kokoro voice used by the live assistant.

From the repository root, regenerate narration and timing files with the configured Kokoro environment:

```sh
.venv/bin/python video-explainer/scripts/generate_voiceover.py
```

Then lint and render the 1080p film and poster:

```sh
cd video-explainer
npm run lint
npx remotion render src/index.ts PitchroomExplainer ../frontend/static/assets/pitchroom-feature-explainer.mp4 --codec h264 --crf 20
npx remotion still src/index.ts PitchroomExplainer ../frontend/static/assets/pitchroom-feature-explainer-poster.jpg --frame 24
```

The generated WebVTT captions are at `public/voiceover/captions.vtt` and the scene audio at `public/voiceover/`.
