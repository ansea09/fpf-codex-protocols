#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
WRAPPER = SCRIPT_DIR / "speech-to-md"
SCHEMA_DIR = SKILL_DIR / "schemas"


def find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "scripts" / "validate-json-schema.py").is_file():
            return candidate
    raise RuntimeError("could not locate repository root with scripts/validate-json-schema.py")


REPO_ROOT = find_repo_root(SCRIPT_DIR)
VALIDATOR = REPO_ROOT / "scripts" / "validate-json-schema.py"


def run(command: list[str], *, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    if check and proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(command)}\n{proc.stdout}")
    return proc


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_bundle(bundle_dir: Path) -> dict:
    run([sys.executable, str(VALIDATOR), str(SCHEMA_DIR / "speech-to-md-manifest.schema.json"), str(bundle_dir / "manifest.json")])
    run([sys.executable, str(VALIDATOR), str(SCHEMA_DIR / "speech-to-md-segments.schema.json"), str(bundle_dir / "segments.json")])
    manifest = load_json(bundle_dir / "manifest.json")
    content = (bundle_dir / "content.md").read_text(encoding="utf-8")
    if "# Transcript" not in content:
        raise AssertionError(f"missing transcript heading in {bundle_dir}")
    if "manifest.json" not in manifest.get("files", []):
        raise AssertionError(f"manifest does not list manifest.json in {bundle_dir}")
    return manifest


def validate_doctor(work_dir: Path) -> dict:
    doctor_path = work_dir / "doctor.json"
    proc = run([sys.executable, str(WRAPPER), "--doctor", "--json"])
    doctor_path.write_text(proc.stdout, encoding="utf-8")
    run([sys.executable, str(VALIDATOR), str(SCHEMA_DIR / "speech-to-md-doctor.schema.json"), str(doctor_path)])
    doctor = load_json(doctor_path)
    checks = {item.get("name"): item.get("detail") for item in doctor.get("checks", [])}
    if "engine" not in checks or "whisper-cpp" not in checks["engine"]:
        raise AssertionError("doctor did not report selected ASR engine")
    return doctor


def check_model_auto_discovery_quality_floor(work_dir: Path) -> None:
    model_dir = work_dir / "models"
    model_dir.mkdir()
    (model_dir / "ggml-tiny.bin").write_bytes(b"tiny model should not be auto-discovered\n")
    (model_dir / "ggml-base.bin").write_bytes(b"base model should not be auto-discovered\n")
    env = {
        **os.environ,
        "CODEX_HOME": str(work_dir / "isolated-codex-home"),
        "HOME": str(work_dir / "isolated-home"),
        "SPEECH_TO_MD_MODELS_DIR": str(model_dir),
    }
    doctor = json.loads(run([sys.executable, str(WRAPPER), "--doctor", "--json"], env=env).stdout)
    model_check = next(item for item in doctor["checks"] if item["name"] == "whisper-model")
    if model_check["status"] != "warn":
        raise AssertionError("tiny/base models should not satisfy automatic model discovery")

    small_model = model_dir / "ggml-small.bin"
    small_model.write_bytes(b"small model is allowed for automatic discovery\n")
    doctor = json.loads(run([sys.executable, str(WRAPPER), "--doctor", "--json"], env=env).stdout)
    model_check = next(item for item in doctor["checks"] if item["name"] == "whisper-model")
    if model_check["status"] != "ok" or model_check["detail"] != str(small_model):
        raise AssertionError("small model should satisfy automatic model discovery")


def check_transcript_import(work_dir: Path) -> None:
    transcript = work_dir / "fixture-transcript.txt"
    transcript.write_text("Alpha transcript line.\n\nBeta transcript line.\n", encoding="utf-8")
    source_audio = work_dir / "recording.mp3"
    source_audio.write_bytes(b"not real audio; import mode records metadata only\n")
    bundle = work_dir / "transcript-import-bundle"
    run(
        [
            sys.executable,
            str(WRAPPER),
            "--transcript",
            str(transcript),
            "--source-audio",
            str(source_audio),
            "-o",
            str(bundle),
        ]
    )
    manifest = validate_bundle(bundle)
    if manifest["engine"]["name"] != "transcript-import":
        raise AssertionError("transcript import did not record transcript-import engine")
    if "Alpha transcript line." not in (bundle / "content.md").read_text(encoding="utf-8"):
        raise AssertionError("transcript import content mismatch")


def check_force_is_success_atomic(work_dir: Path) -> None:
    bundle = work_dir / "atomic-bundle"
    transcript = work_dir / "atomic-transcript.txt"
    transcript.write_text("Original transcript survives failed replacement.\n", encoding="utf-8")
    run([sys.executable, str(WRAPPER), "--transcript", str(transcript), "-o", str(bundle)])
    before = (bundle / "content.md").read_text(encoding="utf-8")
    missing = work_dir / "missing-transcript.txt"
    proc = run(
        [
            sys.executable,
            str(WRAPPER),
            "--transcript",
            str(missing),
            "-o",
            str(bundle),
            "--force",
        ],
        check=False,
    )
    if proc.returncode == 0:
        raise AssertionError("expected failed --force run with missing transcript")
    after = (bundle / "content.md").read_text(encoding="utf-8")
    if after != before:
        raise AssertionError("--force failure changed existing output bundle")


def find_sample_wav() -> Path | None:
    explicit = os.environ.get("SPEECH_TO_MD_REGRESSION_WAV")
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    candidates.extend(
        [
            codex_home / "tools" / "whisper.cpp" / "samples" / "jfk.wav",
            Path.home() / ".codex" / "tools" / "whisper.cpp" / "samples" / "jfk.wav",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def doctor_ready_for_asr(doctor: dict) -> bool:
    checks = {item.get("name"): item.get("status") for item in doctor.get("checks", [])}
    return checks.get("whisper-cli") == "ok" and checks.get("whisper-model") == "ok" and checks.get("ffmpeg") == "ok"


def run_asr_bundle(source: Path, bundle: Path, extra_args: list[str] | None = None) -> dict:
    command = [
        sys.executable,
        str(WRAPPER),
        str(source),
        "-o",
        str(bundle),
        "--force",
        "--language",
        "en",
    ]
    if os.environ.get("SPEECH_TO_MD_REGRESSION_NO_GPU", "1") not in {"0", "false", "no"}:
        command.append("--no-gpu")
    if extra_args:
        command.extend(extra_args)
    run(command)
    manifest = validate_bundle(bundle)
    engine = manifest.get("engine", {})
    if engine.get("adapter") != "whisper-cpp":
        raise AssertionError("ASR manifest did not record whisper-cpp adapter")
    capabilities = engine.get("capabilities", {})
    if capabilities.get("diarization") is not False or capabilities.get("cloud") is not False:
        raise AssertionError("ASR manifest capabilities do not preserve local-core boundary")
    content = (bundle / "content.md").read_text(encoding="utf-8").lower()
    if "country" not in content:
        raise AssertionError(f"unexpected ASR content for {source}: {content[:200]}")
    return manifest


def check_asr_regressions(work_dir: Path, doctor: dict) -> None:
    required = os.environ.get("SPEECH_TO_MD_ASR_REGRESSION", "auto") == "required"
    sample = find_sample_wav()
    if not doctor_ready_for_asr(doctor) or sample is None:
        message = "SKIP: ASR regression needs whisper-cli, model, ffmpeg, and jfk.wav sample"
        if required:
            raise RuntimeError(message)
        print(message)
        return
    wav_manifest = run_asr_bundle(sample, work_dir / "wav-bundle")
    if wav_manifest["engine"]["audio_preprocess"]["normalized"]:
        raise AssertionError("WAV should pass directly in auto mode")

    ffmpeg = doctor["runtime"]["ffmpeg"]["path"]
    mp3 = work_dir / "jfk.mp3"
    m4a = work_dir / "jfk.m4a"
    run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(sample), "-codec:a", "libmp3lame", str(mp3)])
    run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(sample), "-codec:a", "aac", str(m4a)])

    mp3_manifest = run_asr_bundle(mp3, work_dir / "mp3-bundle")
    if mp3_manifest["engine"]["audio_preprocess"]["normalized"]:
        raise AssertionError("MP3 should pass directly in auto mode")

    m4a_manifest = run_asr_bundle(m4a, work_dir / "m4a-bundle")
    preprocess = m4a_manifest["engine"]["audio_preprocess"]
    if not preprocess["normalized"]:
        raise AssertionError("M4A should be normalized in auto mode")
    if "output" in preprocess:
        raise AssertionError("M4A preprocess metadata must not expose deleted temp output path")
    if m4a_manifest["engine"]["audio_input"]["path"] is not None:
        raise AssertionError("normalized audio input path should not point at deleted temp WAV")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="speech-to-md-regression.") as temp:
        work_dir = Path(temp)
        doctor = validate_doctor(work_dir)
        check_model_auto_discovery_quality_floor(work_dir)
        check_transcript_import(work_dir)
        check_force_is_success_atomic(work_dir)
        check_asr_regressions(work_dir, doctor)
    print("OK: speech-to-md regression corpus passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
