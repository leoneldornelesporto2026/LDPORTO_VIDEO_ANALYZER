from pathlib import Path
import json
import math
import os
import re
import shutil
import sys
import numpy as np
import soundfile as sf
from .core import run_command, ok, Unavailable, overlap
from .config import asset_path


def ffmpeg_audio(source, destination, *, filters=None, sample_rate=16000,
                 channels=1, start=None, duration=None, codec="pcm_s16le"):
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if start is not None:
        args += ["-ss", f"{start:.9f}"]
    args += ["-i", str(source)]
    if duration is not None:
        args += ["-t", f"{duration:.9f}"]
    args += ["-map", "0:a:0", "-vn"]
    if filters:
        args += ["-af", filters]
    args += ["-ar", str(sample_rate), "-ac", str(channels), "-c:a", codec,
             "-rf64", "auto", str(destination)]
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    run_command(args)
    return Path(destination)


def extract_audio(ctx, metadata):
    folder = ctx.output / "audio"
    folder.mkdir(exist_ok=True)
    original, mono, clean = [folder / n for n in
                             ("original.wav", "original_mono_16k.wav", "speech_clean.wav")]
    # Keep original sampling/channels. Align every derived track to video t=0.
    offset = metadata["audio_start_time"] - metadata["video_start_time"]
    sync = f"atrim=start={-offset:.9f},asetpts=PTS-STARTPTS" if offset < 0 else "asetpts=PTS-STARTPTS"
    if offset > 0:
        sync += f",adelay={offset * 1000:.6f}:all=1"
    sync += f",apad,atrim=duration={metadata['duration']:.9f}"
    ffmpeg_audio(ctx.video, original, filters=sync,
                 sample_rate=metadata["audio_sample_rate"],
                 channels=metadata["audio_channels"], codec="pcm_s24le")
    ffmpeg_audio(original, mono)
    filters = [f"highpass=f={ctx.config['audio']['highpass_hz']}"]
    if ctx.config["audio"]["denoise"]:
        filters += ["afftdn=nf=-30:tn=1"]
    if ctx.config["audio"]["normalize"]:
        # Dynamic loudness compensation; no trimming or time stretching.
        filters += ["dynaudnorm=f=500:g=7:p=0.90:m=4"]
    ffmpeg_audio(mono, clean, filters=",".join(filters))
    notes = ["speech_clean é um derivado conservador; ruído/reverberação não são removidos por garantia."]
    artifacts = [original, mono, clean]
    isolated = None
    external = ctx.config["audio"]["isolated_file"]
    if external:
        src = asset_path(external)
        if not src.is_file():
            notes.append("isolated_file não encontrado; mantendo fontes original/clean.")
        else:
            isolated = folder / "speech_isolated.wav"
            shift = ctx.config["audio"]["isolated_offset_seconds"]
            transform = f"atrim=start={-shift},asetpts=PTS-STARTPTS" if shift < 0 else "asetpts=PTS-STARTPTS"
            if shift > 0:
                transform += f",adelay={shift * 1000}:all=1"
            ffmpeg_audio(src, isolated, filters=transform)
            length = sf.info(isolated).duration
            if abs(length - metadata["duration"]) > 0.12:
                raise ValueError("isolated_file com duração diferente; forneça uma trilha "
                                 "sincronizada de vídeo inteiro, sem cortes.")
            artifacts.append(isolated)
            notes.append("Áudio isolado fornecido externamente. Duração confere; sincronismo interno precisa de revisão.")
    return ok({"original": str(original.resolve()), "mono": str(mono.resolve()),
               "speech_clean": str(clean.resolve()),
               "speech_isolated": str(isolated.resolve()) if isolated else None,
               "timeline_origin": "video start, seconds", "audio_offset_corrected": offset},
              notes=notes, artifacts=artifacts)


def audio_metrics(ctx, audio, metadata):
    windows = []
    duration = metadata["duration"]
    with sf.SoundFile(audio["original"]) as f:
        rate = f.samplerate
        time = 0.0
        for block in f.blocks(blocksize=rate * 10, dtype="float32", always_2d=True):
            # Measure clipping before downmixing: opposite-polarity channels must not hide it.
            rms = float(np.sqrt(np.mean(block.astype("float64") ** 2)))
            windows.append({"start": time, "end": min(duration, time + len(block) / rate),
                            "rms_dbfs": 20 * math.log10(max(rms, 1e-12)),
                            "peak": float(np.max(np.abs(block))),
                            "clipping_fraction": float(np.mean(np.abs(block) >= 0.999)),
                            "speech_quality": None, "background_music_level": None,
                            "background_noise_level": None, "speech_to_background_ratio": None,
                            "transcription_difficulty": None})
            time += len(block) / rate
    _, stderr = run_command(["ffmpeg", "-hide_banner", "-i", audio["mono"],
                             "-af", f"silencedetect=noise={ctx.config['audio']['silence_db']}dB:"
                                    f"d={ctx.config['audio']['silence_min_seconds']}",
                             "-f", "null", "-"])
    silences, pending = [], None
    for line in stderr.splitlines():
        m = re.search(r"silence_start:\s*([0-9.e+-]+)", line)
        if m:
            pending = max(0, float(m.group(1)))
        m = re.search(r"silence_end:\s*([0-9.e+-]+)", line)
        if m and pending is not None:
            end = min(duration, float(m.group(1)))
            silences.append({"start": pending, "end": end, "duration": end - pending,
                             "classification": "unknown", "method": "amplitude_threshold",
                             "inference": False})
            pending = None
    if pending is not None:
        silences.append({"start": pending, "end": duration, "duration": duration - pending,
                         "classification": "unknown", "method": "amplitude_threshold",
                         "inference": False})
    return ok({"quality_windows": windows, "silences": silences,
               "audio_quality": None, "speech_clarity": None,
               "background_noise_level": None,
               "clipping_detected": any(w["clipping_fraction"] > 0.0001 for w in windows),
               "music_under_speech": None, "music_level_relative_to_speech": None,
               "possible_transcription_difficulty": None},
              notes=["RMS/clipping/silêncio medidos. Inteligibilidade e relação voz/música "
                     "não são deduzidas de volume; campos sem evidência ficam null."])


def separate_review_region(ctx, mono, start, end, folder):
    python = ctx.config["audio"]["demucs_python"] or sys.executable
    src = folder / "region.wav"
    ffmpeg_audio(mono, src, start=start, duration=end-start, sample_rate=44100, channels=2)
    target = folder / "separated"
    run_command([python, "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs",
                 "--segment", "7", "--shifts", "0", "-d", "cpu",
                 "-o", target, src])
    vocals = target / "htdemucs" / "region" / "vocals.wav"
    isolated = folder / "isolated_16k.wav"
    ffmpeg_audio(vocals, isolated)
    if abs(sf.info(isolated).duration - (end-start)) > 0.12:
        raise ValueError("Separação alterou a duração; hipótese descartada.")
    return isolated


def plan_clip_audio(candidates, events, start, end, *, instrumental=False, gain=0.10,
                    track_title='Eu Não Vou Parar'):
    """Downstream evidence plan; never infers stems, origin or effective ducking."""
    if isinstance(gain, bool) or not isinstance(gain, (int, float)) or not math.isfinite(gain) or not 0 <= gain <= .25:
        raise ValueError('INSTRUMENTAL_GAIN_MUST_BE_FINITE_0_TO_025')
    performance = any(any(token in ' '.join(str(c.get(k) or '').lower()
        for k in ('content_type', 'story_type', 'category', 'categories'))
        for token in ('performance', 'show_musical', 'concert', 'musical', 'live_music'))
        for c in candidates)
    evidence = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        left, right = event.get('start'), event.get('end')
        if (isinstance(left, bool) or isinstance(right, bool) or
            not isinstance(left, (int, float)) or not isinstance(right, (int, float)) or
            not math.isfinite(left) or not math.isfinite(right) or right <= left or
            left >= end or right <= start):
            continue
        label = str(event.get('type') or event.get('label') or event.get('event') or '').lower()
        kind = {'speech': 'voice', 'laughter': 'reaction', 'laugh': 'reaction',
                'risada': 'reaction', 'applause': 'reaction', 'aplauso': 'reaction',
                'music': 'source_music', 'sound_effect': 'effect'}.get(label, 'unknown')
        origin = event.get('origin') if event.get('origin_verified') is True else None
        if origin not in ('audience', 'studio', 'speaker', 'performance', 'original_background', 'effect'):
            origin = None
        evidence.append({'start': max(start, left), 'end': min(end, right),
                         'type': label, 'role': kind, 'origin': origin,
                         'confidence': event.get('confidence'), 'method': event.get('method'),
                         'inference': event.get('inference'), 'listen_required': True})
    source_music = any(e['role'] == 'source_music' for e in evidence)
    mode = ('original_performance' if performance else 'source_original'
            if source_music or not instrumental or gain == 0 else 'source_plus_instrumental')
    return {'policy_version': '24.1', 'audio_mode': mode, 'source_preserved': True,
            'source_music_role': 'performance' if performance else None,
            'events': evidence, 'humor_reaction_evidence': [e for e in evidence if e['role'] in ('reaction', 'effect')],
            'reaction_is_payoff_proof': False, 'stems_separated': False,
            'instrumental_title': track_title if instrumental else None,
            'instrumental_gain': gain if mode == 'source_plus_instrumental' else 0.,
            'instrumental_reason': 'preserve_performance' if performance else
                'source_music_hypothesis_requires_listening' if source_music else
                'optional_background' if mode == 'source_plus_instrumental' else 'disabled',
            'ducking_applied': False, 'ducking_verified': None,
            'ducking_reason': 'no_measured_and_listened_safe_ducking_evidence',
            'listening_verified': None, 'publication_ready': False}


def delivery_audio_filter(audio_plan):
    if audio_plan['audio_mode'] != 'source_plus_instrumental':
        return '[0:a:0]anull[a]'
    # No amix normalization or automatic makeup gain. Limiting is not ducking.
    gain = audio_plan['instrumental_gain']
    return (f'[0:a:0]anull[a0];[1:a:0]volume={gain:.6f}[bed];'
            '[a0][bed]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,'
            'alimiter=limit=0.95:level=0:latency=1[a]')


def sound_events(ctx, audio, transcript):
    cfg = ctx.config["audio_events"]
    if not cfg["enabled"]:
        return ok({"events": [], "music_under_speech": None}, "skipped")
    if not cfg["checkpoint"] or not asset_path(cfg["checkpoint"]).is_file():
        raise Unavailable("PANNs requer checkpoint local em audio_events.checkpoint.")
    try:
        from panns_inference import AudioTagging
        from panns_inference.config import labels
    except ImportError:
        raise Unavailable("Instale requirements/audio-events.txt para classificar sons.")
    model = AudioTagging(checkpoint_path=str(asset_path(cfg["checkpoint"])), device="cpu")
    temporary = ctx.cache / "events_32k.wav"
    ffmpeg_audio(audio["original"], temporary, sample_rate=32000)
    lookup = {"Speech": "speech", "Music": "music", "Laughter": "laughter",
              "Applause": "applause", "Noise": "noise"}
    events = []
    with sf.SoundFile(temporary) as f:
        start = 0.0
        for samples in f.blocks(blocksize=int(32000 * cfg["window_seconds"]), dtype="float32"):
            end = start + len(samples) / 32000
            if len(samples) < 32000:
                samples = np.pad(samples, (0, 32000-len(samples)))
            scores, _ = model.inference(samples[None, :])
            for name, category in lookup.items():
                if name not in labels:
                    continue
                score = float(scores[0, labels.index(name)])
                if score >= cfg["threshold"]:
                    events.append({"start": start, "end": end, "type": category,
                                   "confidence": score, "method": "panns_clipwise",
                                   "inference": True,
                                   "temporal_resolution_seconds": cfg["window_seconds"]})
            start = end
    music_speech = any(e["type"] == "music" and any(overlap(e["start"], e["end"],
                            s["start"], s["end"]) > 0 for s in transcript.get("segments", []))
                       for e in events)
    del model
    return ok({"events": events, "music_under_speech": music_speech,
               "music_under_speech_method": "music_window_overlaps_asr_segment"},
              notes=["Eventos PANNs são hipóteses por janela; não timestamps exatos de risadas "
                     "nem medição de nível da música. Resultado negativo não exclui música."])
