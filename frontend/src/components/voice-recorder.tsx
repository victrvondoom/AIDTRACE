"use client";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui";

import { Icon } from "@/components/icon";
import { VOICE_LANGUAGES, type VoiceLanguage } from "@/lib/voice-languages";
type State = "idle" | "recording" | "paused" | "stopped";
const MAX_MB = 10;

interface Props {
  onBlob: (blob: Blob) => void;
  language?: VoiceLanguage;
  onLanguageChange?: (language: VoiceLanguage) => void;
  disabled?: boolean;
}

export function VoiceRecorder({ onBlob, language = "auto", onLanguageChange, disabled }: Props) {
  const [state, setState] = useState<State>("idle");
  const [seconds, setSeconds] = useState(0);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [denied, setDenied] = useState(false);
  const [micError, setMicError] = useState("");
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [level, setLevel] = useState(0);
  const [tooLarge, setTooLarge] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const animationRef = useRef<number | null>(null);

  function stopMeter(resetLevel = true) {
    if (animationRef.current !== null) cancelAnimationFrame(animationRef.current);
    animationRef.current = null;
    const context = audioContextRef.current;
    audioContextRef.current = null;
    if (context && context.state !== "closed") void context.close();
    if (resetLevel) setLevel(0);
  }

  function startMeter(stream: MediaStream) {
    try {
      const context = new AudioContext();
      const analyser = context.createAnalyser();
      analyser.fftSize = 512;
      context.createMediaStreamSource(stream).connect(analyser);
      audioContextRef.current = context;
      const samples = new Uint8Array(analyser.fftSize);
      let lastUpdate = 0;
      const sample = (time: number) => {
        analyser.getByteTimeDomainData(samples);
        let energy = 0;
        for (const value of samples) {
          const centered = (value - 128) / 128;
          energy += centered * centered;
        }
        const rms = Math.sqrt(energy / samples.length);
        if (time - lastUpdate > 100) {
          setLevel(Math.min(1, rms * 3));
          lastUpdate = time;
        }
        animationRef.current = requestAnimationFrame(sample);
      };
      animationRef.current = requestAnimationFrame(sample);
    } catch {
      // Recording remains available when the browser does not expose Web Audio metering.
    }
  }

  async function refreshDevices() {
    try {
      const inputs = (await navigator.mediaDevices.enumerateDevices()).filter((device) => device.kind === "audioinput");
      setDevices(inputs);
    } catch {
      setDevices([]);
    }
  }

  useEffect(
    () => () => {
      if (timerRef.current) clearInterval(timerRef.current);
      mediaRef.current?.stop();
      streamRef.current?.getTracks().forEach((track) => track.stop());
      stopMeter(false);
    },
    [],
  );

  useEffect(() => {
    let active = true;
    navigator.mediaDevices?.enumerateDevices().then((all) => {
      if (active) setDevices(all.filter((device) => device.kind === "audioinput"));
    }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  // One object URL per blob, revoked on replacement/unmount — avoids leaking a
  // blob: URL on every render (createObjectURL is not idempotent).
  useEffect(() => {
    if (!blob) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clearing the URL for an external Blob resource, not derived React state
      setAudioUrl(null);
      return;
    }
    const url = URL.createObjectURL(blob);
    // Defensive: an object URL is always a `blob:` URL. Refuse anything else before it
    // can reach the <audio src> sink, so no non-blob scheme can ever be rendered.
    setAudioUrl(url.startsWith("blob:") ? url : null);
    return () => URL.revokeObjectURL(url);
  }, [blob]);

  async function startRecording() {
    setDenied(false);
    setMicError("");
    setTooLarge(false);
    setBlob(null);
    setSeconds(0);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: deviceId ? { deviceId: { exact: deviceId } } : true,
      });
      streamRef.current = stream;
      const activeDevice = stream.getAudioTracks()[0]?.getSettings().deviceId;
      if (activeDevice) setDeviceId(activeDevice);
      await refreshDevices();
      startMeter(stream);
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        stopMeter();
        const b = new Blob(chunksRef.current, { type: mr.mimeType || "audio/webm" });
        if (b.size > MAX_MB * 1024 * 1024) {
          setTooLarge(true);
          setState("idle");
          return;
        }
        setBlob(b);
        onBlob(b);
        setState("stopped");
      };
      mr.start(250);
      mediaRef.current = mr;
      setState("recording");
      timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000);
    } catch {
      setDenied(true);
      setMicError("Microphone unavailable. Check browser permission or upload an audio file instead.");
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      stopMeter();
    }
  }

  function acceptFile(f: File | undefined) {
    if (!f) return;
    setDenied(false);
    setMicError("");
    if (f.size > MAX_MB * 1024 * 1024) {
      setTooLarge(true);
      return;
    }
    setTooLarge(false);
    setBlob(f);
    onBlob(f);
    setState("stopped");
  }

  function stopRecording() {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    mediaRef.current?.stop();
    mediaRef.current = null;
  }

  function togglePause() {
    const recorder = mediaRef.current;
    if (!recorder) return;
    if (state === "recording") {
      recorder.pause();
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = null;
      setState("paused");
    } else if (state === "paused") {
      recorder.resume();
      timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000);
      setState("recording");
    }
  }

  function reset() {
    setState("idle");
    setBlob(null);
    setSeconds(0);
    setTooLarge(false);
  }

  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");

  return (
    <div className="flex flex-col items-center gap-4">
      {denied && <p role="alert" className="w-full max-w-xs text-caption text-danger">{micError}</p>}
      {onLanguageChange && (
        <div className="flex w-full max-w-xs flex-col gap-1.5">
          <label htmlFor="voice-language" className="text-caption font-medium text-ink">Spoken language</label>
          <select
            id="voice-language"
            value={language}
            disabled={disabled || state === "recording"}
            onChange={(event) => onLanguageChange(event.target.value as VoiceLanguage)}
            className="min-h-11 w-full rounded-lg border border-line bg-surface px-3 text-body text-ink focus-visible:outline-2 focus-visible:outline-accent"
          >
            {VOICE_LANGUAGES.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}
          </select>
          <p className="text-caption text-muted">Choose the main spoken language, or let transcription detect it.</p>
        </div>
      )}
      {state === "idle" && devices.length > 1 && (
        <label className="flex w-full max-w-xs flex-col gap-1.5 text-caption font-medium text-ink">
          Microphone
          <select
            value={deviceId}
            onChange={(event) => setDeviceId(event.target.value)}
            className="min-h-11 rounded-lg border border-line bg-surface px-3 text-body font-normal focus-visible:outline-2 focus-visible:outline-accent"
          >
            {devices.map((device, index) => (
              <option key={device.deviceId || index} value={device.deviceId}>
                {device.label || `Microphone ${index + 1}`}
              </option>
            ))}
          </select>
        </label>
      )}
      {state === "idle" && (
        <button
          onClick={startRecording}
          disabled={disabled}
          aria-label="Start voice recording"
          className={cn(
            "grid size-16 place-items-center rounded-full transition-transform focus-visible:outline-2 focus-visible:outline-accent active:scale-95",
            disabled
              ? "cursor-not-allowed bg-line text-muted"
              : "bg-danger text-on-danger transition-colors hover:brightness-90",
          )}
        >
          <Icon name="microphone" className="size-7" />
        </button>
      )}

      {/* A desktop without a microphone (or a browser that never answers the permission prompt) had
          no way to submit a note at all — the upload path only appeared after an explicit denial. */}
      {state === "idle" && (
        <label className={cn("text-caption text-accent underline", disabled ? "pointer-events-none opacity-50" : "cursor-pointer hover:no-underline")}>
          or upload an audio file
          <input
            type="file"
            accept="audio/*"
            aria-label="Upload audio recording"
            className="sr-only"
            disabled={disabled}
            onChange={(e) => acceptFile(e.target.files?.[0])}
          />
        </label>
      )}

      {(state === "recording" || state === "paused") && (
        <div className="flex flex-col items-center gap-3">
          <span
            className="tabular text-display font-semibold text-danger"
            aria-live="polite"
            aria-label={`Recording ${mm}:${ss}`}
          >
            {mm}:{ss}
          </span>
          <div className="h-2 w-48 overflow-hidden rounded-full bg-line" role="meter" aria-label="Microphone sound level" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(level * 100)}>
            <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${Math.max(3, level * 100)}%` }} />
          </div>
          <span className="text-caption text-muted" aria-live="polite">
            {state === "paused" ? "Recording paused" : level < 0.02 ? "Mic is quiet — check distance or input" : "Mic signal detected"}
          </span>
          <div className="flex items-center gap-3">
            <button
              onClick={togglePause}
              aria-label={state === "paused" ? "Resume recording" : "Pause recording"}
              className="min-h-11 rounded-lg border border-line px-4 text-body font-medium text-ink hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-accent"
            >
              {state === "paused" ? "Resume" : "Pause"}
            </button>
            <button
              onClick={stopRecording}
              aria-label="Stop recording"
              className="grid size-14 place-items-center rounded-full border-4 border-danger bg-surface transition-transform focus-visible:outline-2 focus-visible:outline-accent active:scale-95"
            >
              <span className="size-5 rounded-sm bg-danger" aria-hidden="true" />
            </button>
          </div>
        </div>
      )}

      {state === "stopped" && blob && audioUrl && (
        <div className="flex w-full max-w-xs flex-col items-center gap-3">
          <audio
            controls
            src={audioUrl}
            className="w-full rounded-lg"
            aria-label="Playback of your recording"
          />
          <Button variant="ghost" onClick={reset}>
            Re-record
          </Button>
        </div>
      )}

      {tooLarge && (
        <p role="alert" className="text-body text-danger">
          Recording too large (max {MAX_MB} MB). Please record a shorter clip.
        </p>
      )}
    </div>
  );
}
