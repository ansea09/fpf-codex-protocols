---
name: speech-to-md
description: Convert trusted local speech audio into Markdown transcript bundles for LLM analysis, with timestamped segments, source manifest, audit notes, and explicit ASR runtime boundaries. Use when Codex is asked to transcribe, ingest, summarize, analyze, quote, review, or prepare Markdown from local speech recordings such as lectures, interviews, meetings, podcasts, voice notes, or other audio files; when timestamps or transcript evidence matter; or when audio should be routed away from doc-to-md document conversion.
---

# Speech To Md

## Document Roles

This `SKILL.md` is the executable routing contract. Keep detailed output and
runtime rules in references:

- `references/audio-bundle.md` - canonical transcript bundle contract.
- `references/runtime.md` - local ASR engine, model, install, and support
  boundaries.
- `references/extension-boundaries.md` - refactoring thresholds for additional
  ASR engines, diarization, long-recording chunking, and cloud workflows.

## Operating Contract

This skill handles trusted local speech recordings. It is separate from
`doc-to-md`: document conversion extracts existing file content, while speech
conversion performs ASR and must preserve uncertainty through timestamps,
engine metadata, and audit notes.

The public skill source does not bundle ASR models, Homebrew packages, Python
virtual environments, cloud credentials, or generated transcripts. Use a local
ASR engine deliberately. The first supported source-level engine contract is
`whisper.cpp` through a `whisper-cli` executable and a user-provided model file.

Cloud transcription, diarization, translation, speaker identification,
long-recording chunking, and meeting-minutes generation are explicit advanced
modes. Do not imply they work unless the needed engine, credentials, workflow,
and output evidence contract have been installed and checked.

## Route Selection

| Situation | Action |
| --- | --- |
| Trusted local speech audio and `whisper.cpp` is configured | `speech-to-md audio-file -o audio-bundle --model /path/to/model.bin` |
| Existing transcript should be packaged for LLM analysis | `speech-to-md --transcript transcript.txt --source-audio audio-file -o audio-bundle` |
| User asks to convert audio through `doc-to-md` | Route here; audio is outside `doc-to-md` core. |
| Speaker labels or diarization are required | Explain that the current local workflow does not provide diarization; use an explicit advanced engine later. |
| Untrusted, remote, hosted, or shared-user audio ingestion | Stop and require separate sandboxing and privacy review before processing. |

## Workflow

1. Identify whether the source is a trusted local audio file or an existing
   transcript to bundle.
2. Run the doctor before relying on ASR:

```bash
speech-to-md --doctor
speech-to-md --doctor --json
```

If `speech-to-md` is not on PATH, use the installed skill script directly:

```bash
python3 "${SPEECH_TO_MD_SKILL_DIR:-${CODEX_HOME:-$HOME/.codex}/skills/speech-to-md}/scripts/speech-to-md" --doctor
```

3. Convert trusted local speech audio:

```bash
speech-to-md lecture.mp3 -o lecture-audio-bundle --model /path/to/ggml-model.bin
```

By default, `--audio-normalization auto` passes formats known to work with
`whisper.cpp` directly and uses `ffmpeg` to normalize other local containers,
such as M4A/AAC/MP4, to mono 16 kHz WAV before ASR. Use
`--audio-normalization always` for a consistent normalized path, or `never`
only when you know the input is accepted by `whisper.cpp` directly.

If the local Metal/GPU path fails, retry the same trusted file with CPU
fallback:

```bash
speech-to-md lecture.wav -o lecture-audio-bundle --model /path/to/ggml-model.bin --no-gpu
```

For long local ASR runs, `speech-to-md` streams `whisper.cpp` output. It does
not use the helper `--timeout` as a total ASR wall-time kill switch. Use
`--asr-idle-timeout N` only when the process should be killed after N seconds
without stdout progress; `0` disables that inactivity timeout. The wrapper may
write best-effort `<output>.partial` bundles every
`--partial-bundle-interval` seconds while timestamped stdout is available. Use
partial bundles only as progress evidence; the final bundle remains the source
of truth after ASR completes.

4. Or package an existing transcript:

```bash
speech-to-md --transcript transcript.txt --source-audio lecture.mp3 -o lecture-audio-bundle
```

5. Verify the result:

```bash
sed -n '1,80p' lecture-audio-bundle/LLM_README.md
sed -n '1,80p' lecture-audio-bundle/content.md
sed -n '1,120p' lecture-audio-bundle/audit.md
```

6. Report the output path, engine, warnings, and any limitations that affect
   trust in the transcript.

## Output Contract

Expected bundle files:

- `LLM_README.md` - how Codex, Claude Code, or another agent should inspect the bundle.
- `content.md` - clean transcript text for ordinary reading and analysis.
- `segments.md` - timestamped transcript evidence when available.
- `segments.json` - machine-readable segments.
- `manifest.json` - source, engine, runtime fingerprint, model, command, size,
  audio normalization, and checksum metadata.
- `audit.md` - warnings, unsupported features, and trust boundaries.
- `conversion-report.md` - human-readable run summary.
- `timestamps.vtt` - optional, only when the engine emitted it.

Read `references/audio-bundle.md` before changing this contract.

## Guardrails

- Process trusted local files only. Do not fetch remote audio or accept hosted
  untrusted uploads without a separate sandbox and privacy boundary.
- Do not send audio to cloud transcription unless the user explicitly requests
  it and understands privacy, cost, and credential requirements.
- Do not claim speaker labels, diarization, speaker identity, or exact quotes
  unless the bundle contains explicit evidence for them.
- Treat ASR output as probabilistic. No transcript is proof of what was said
  without source audio review or a stronger evidence process.
- Keep generated bundles separate from source audio unless the user explicitly
  requests another location.
- Long recordings may require chunking by the engine. Record chunking and loss
  notes in `audit.md`.
- For MP3/M4A/container inputs, rely on local `ffmpeg` normalization rather
  than remote conversion services.
- Do not treat internal temporary normalized WAV paths as durable evidence.
  `manifest.json` records normalization parameters and checksum metadata instead.

## Useful Commands

```bash
speech-to-md --doctor
speech-to-md --doctor --json
speech-to-md audio.mp3 -o audio-bundle --model /path/to/ggml-model.bin
speech-to-md audio.m4a -o audio-bundle --model /path/to/ggml-model.bin --audio-normalization auto
speech-to-md audio.mp3 -o audio-bundle --model /path/to/ggml-model.bin --audio-normalization always
speech-to-md audio.wav -o audio-bundle --model /path/to/ggml-model.bin --no-gpu
speech-to-md --transcript transcript.txt --source-audio audio.mp3 -o audio-bundle
speech-to-md --help
python3 scripts/speech-to-md --doctor
python3 scripts/speech-to-md --transcript transcript.txt -o audio-bundle
```

## Installation

Install the command shim from the skill directory:

```bash
bash "${SPEECH_TO_MD_SKILL_DIR:-${CODEX_HOME:-$HOME/.codex}/skills/speech-to-md}/scripts/install.sh"
```

Set the model path for local `whisper.cpp` runs:

```bash
export SPEECH_TO_MD_WHISPER_CPP_MODEL="/absolute/path/to/ggml-model.bin"
```

The wrapper also auto-discovers common local model paths under
`${CODEX_HOME:-$HOME/.codex}/tools/whisper.cpp/models`, but only for
`medium`/`small` quality-floor models. Lower-quality `tiny` and `base` models
must be selected explicitly with `--model` when a speed-first test is intended.
Use `--model` when several models exist or when a specific quality/speed
tradeoff matters.

For MP3/M4A and audio normalization paths, install a local `ffmpeg` binary on
PATH or set:

```bash
export SPEECH_TO_MD_FFMPEG_BIN="/absolute/path/to/ffmpeg"
```

Read `references/runtime.md` before installing ASR engines or promising support
outside trusted local macOS/Codex usage.
