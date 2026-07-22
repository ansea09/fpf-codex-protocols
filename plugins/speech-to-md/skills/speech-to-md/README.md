# Speech To Md

`speech-to-md` turns trusted local speech recordings, or existing transcripts,
into Markdown bundles for LLM analysis.

The public skill does not bundle ASR models, cloud credentials, or generated
outputs. It provides the routing contract, bundle format, doctor checks, and a
local wrapper that can use `whisper.cpp` when `whisper-cli` and a model file are
installed by the user.

The runtime has an explicit ASR engine adapter boundary. The current supported
adapter is still only `whisper-cpp`; the boundary exists so future local engines
can be added without changing the bundle contract.

## Current Update

This update prepares `speech-to-md` for the next growth step without changing
the day-to-day command. It keeps the current local `whisper.cpp` workflow, but
adds a clear internal boundary between the transcript bundle format and the ASR
engine that produces transcript text.

This is useful for:

- users who want stable Markdown transcript bundles today;
- maintainers who may later add another local ASR engine;
- reviewers who need to see whether diarization, chunking, or cloud
  transcription are actually supported;
- LLM agents that should inspect `manifest.json` and `audit.md` before making
  speaker-sensitive or quote-sensitive claims.

The update matters most when the skill is used in contexts such as lectures,
interviews, meetings, podcasts, field notes, or long voice recordings where the
transcript may later need stronger evidence: timestamps, engine metadata,
runtime fingerprints, speaker labels, or chunking records. It does not claim
new transcription quality by itself; it makes future quality-related features
safer to add and easier to audit.

## Quick Start

Install the command shim from an installed skill directory:

```bash
bash "${CODEX_HOME:-$HOME/.codex}/skills/speech-to-md/scripts/install.sh"
```

Check runtime readiness:

```bash
speech-to-md --doctor
```

Package an existing transcript:

```bash
speech-to-md --transcript transcript.txt --source-audio recording.mp3 -o recording-audio-bundle
```

Transcribe with local `whisper.cpp` after installing `whisper-cli` and a model:

```bash
speech-to-md recording.mp3 -o recording-audio-bundle --model /path/to/ggml-model.bin
```

`--audio-normalization auto` is the default. It passes WAV/MP3/FLAC directly to
`whisper.cpp` and uses local `ffmpeg` to normalize other containers, such as
M4A/AAC/MP4, to mono 16 kHz WAV before ASR. Use
`--audio-normalization always` to force normalization, or `never` to disable it.

If the model is stored under
`${CODEX_HOME:-$HOME/.codex}/tools/whisper.cpp/models`, the wrapper can find
common `medium`/`small` model filenames automatically. It intentionally skips
`tiny` and `base` models unless they are passed explicitly with `--model`.

This quality floor keeps routine transcripts from silently using very small
models that are fast but often too error-prone for reading, quoting, or
summarizing. Use `tiny` or `base` only as an explicit speed-first choice, for
example when testing that the local runtime is wired correctly.

If the local Metal/GPU backend fails, retry with CPU fallback:

```bash
speech-to-md recording.wav -o recording-audio-bundle --model /path/to/ggml-model.bin --no-gpu
```

Long local ASR runs are streamed. The wrapper no longer kills `whisper.cpp`
because the total ASR wall time is long; it only applies `--asr-idle-timeout`
when no stdout progress is seen. The default `--asr-idle-timeout 0` disables
this ASR inactivity timeout.

While `whisper.cpp` emits timestamped stdout, the wrapper can write a
best-effort partial bundle next to the final output:

```bash
speech-to-md long-recording.mp3 -o long-recording-audio-bundle --partial-bundle-interval 300
```

The partial output path is `<output>.partial`. Treat it as progress evidence
only; the final bundle is still parsed from the completed `whisper.cpp` JSON/TXT
outputs.

## Output

The bundle contains:

```text
LLM_README.md
content.md
segments.md
segments.json
manifest.json
audit.md
conversion-report.md
timestamps.vtt
```

`timestamps.vtt` appears only when the ASR engine emits it.

## Boundaries

- Trusted local audio only by default.
- No bundled model files or runtime environments.
- MP3/M4A support depends on the local ASR engine plus optional local `ffmpeg`
  normalization.
- `manifest.json` records runtime fingerprints and audio-normalization metadata;
  temporary normalized WAV files are not retained in the bundle.
- No cloud transcription unless the user explicitly opts in later.
- No diarization or speaker identity in the first local workflow.
- A second ASR engine, diarization, deterministic long-recording chunking, or
  cloud transcription must follow `references/extension-boundaries.md` before
  being advertised as supported.
- Native Windows support is not claimed.

Read `references/runtime.md`, `references/audio-bundle.md`, and
`references/extension-boundaries.md` before extending the runtime or output
contract.
