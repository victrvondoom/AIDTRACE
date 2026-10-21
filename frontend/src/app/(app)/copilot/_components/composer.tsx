"use client";

import { useEffect, useRef, useState } from "react";
import { cn, localDateString } from "@/lib/utils";

import { Icon } from "@/components/icon";
import { VOICE_LANGUAGES, type VoiceLanguage } from "@/lib/voice-languages";
// Web Speech API — not available in all browsers; typed as any to avoid lib conflicts.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type SpeechRecogAny = any;

export function Composer({
  value,
  onChange,
  onSubmit,
  asOf,
  onAsOfChange,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  asOf: string;
  onAsOfChange: (v: string) => void;
}) {
  const [listening, setListening] = useState(false);
  const [voiceLanguage, setVoiceLanguage] = useState<VoiceLanguage>("en");
  const [voiceError, setVoiceError] = useState("");
  const [showAsOf, setShowAsOf] = useState(false);
  const recogRef = useRef<SpeechRecogAny>(null);
  const dictatedRef = useRef("");
  const dictationBaseRef = useRef("");
  const hasSpeech =
    typeof window !== "undefined" &&
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);

  const today =
    typeof window !== "undefined" ? localDateString() : undefined;

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("kairos-voice-language") as VoiceLanguage | null;
      if (saved && VOICE_LANGUAGES.some((item) => item.code === saved && item.code !== "auto")) {
        // eslint-disable-next-line react-hooks/set-state-in-effect -- restore the saved browser dictation preference
        setVoiceLanguage(saved);
      }
    } catch { /* browser storage may be disabled */ }
  }, []);

  function toggleVoice() {
    if (listening) {
      recogRef.current?.stop();
      setListening(false);
      return;
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const win = window as any;
    const SR = win.SpeechRecognition ?? win.webkitSpeechRecognition;
    try {
      const r = new SR();
      r.lang = VOICE_LANGUAGES.find((item) => item.code === voiceLanguage)?.speechLocale || "en-IN";
      r.continuous = true;
      r.interimResults = false;
      dictatedRef.current = "";
      dictationBaseRef.current = value;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      r.onresult = (e: any) => {
        const transcript = Array.from(e.results as ArrayLike<{ 0?: { transcript?: string }; isFinal?: boolean }>)
          .slice(e.resultIndex ?? 0)
          .filter((result) => result.isFinal !== false)
          .map((result) => result[0]?.transcript ?? "")
          .filter(Boolean)
          .join(" ");
        if (transcript) {
          dictatedRef.current = [dictatedRef.current, transcript].filter(Boolean).join(" ");
          onChange([dictationBaseRef.current, dictatedRef.current].filter(Boolean).join(" "));
        }
      };
      r.onend = () => {
        setListening(false);
        if (!dictatedRef.current) setVoiceError("No speech was captured. Try again or type your question.");
      };
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      r.onerror = (event: any) => {
        setListening(false);
        setVoiceError(event.error === "not-allowed" ? "Microphone permission was denied. You can type your question instead." : "Voice input stopped. Check your microphone or type your question.");
      };
      r.start();
      recogRef.current = r;
      setVoiceError("");
      setListening(true);
    } catch {
      setVoiceError("Voice input could not start in this browser. Type your question instead.");
      setListening(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Time-travel date picker — shown when toggled or when a date is set */}
      {(showAsOf || asOf) && (
        <div className="flex items-center gap-2 text-label">
          <label htmlFor="copilot-asof" className="font-medium text-muted">
            As of
          </label>
          <input
            id="copilot-asof"
            type="date"
            value={asOf}
            onChange={(e) => onAsOfChange(e.target.value)}
            max={today}
          className="min-h-11 rounded-md border border-line bg-surface px-2 py-1 text-label outline-none focus-visible:border-accent"
          />
          {asOf && (
            <button
              type="button"
              onClick={() => {
                onAsOfChange("");
                setShowAsOf(false);
              }}
              className="min-h-11 px-2 text-muted transition-colors hover:text-ink"
              aria-label="Clear time travel date"
            >
              Clear
            </button>
          )}
        </div>
      )}

      <form
        data-testid="copilot-composer"
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        className="flex min-h-11 items-center gap-2 rounded-2xl border border-line bg-surface py-2 pl-4 pr-2 focus-within:border-[color-mix(in_srgb,var(--accent)_45%,var(--line))]"
      >
        {hasSpeech && (
          <select
            aria-label="Voice input language"
            value={voiceLanguage}
            disabled={listening}
            onChange={(event) => {
              const next = event.target.value as VoiceLanguage;
              setVoiceLanguage(next);
              try { window.localStorage.setItem("kairos-voice-language", next); } catch { /* browser storage may be disabled */ }
              setVoiceError("");
            }}
            className="max-w-24 shrink-0 bg-transparent text-xs text-muted outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            {VOICE_LANGUAGES.filter((item) => item.code !== "auto").map((item) => (
              <option key={item.code} value={item.code}>{item.label}</option>
            ))}
          </select>
        )}
        <input
          value={value}
          onChange={(e) => {
            if (listening) {
              dictationBaseRef.current = e.target.value;
              dictatedRef.current = "";
            }
            onChange(e.target.value);
          }}
          placeholder="Ask about an asset, failure, procedure, or requirement…"
          className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted"
          aria-label="Ask the copilot"
        />

        {/* Time-travel toggle */}
        <button
          type="button"
          onClick={() => setShowAsOf((v) => !v)}
          aria-label={asOf ? `Time travel set: ${asOf}` : "Set time travel date"}
          aria-pressed={showAsOf || !!asOf}
          title="Query as of a past date"
          className={cn(
            "grid size-11 shrink-0 place-items-center rounded-xl transition-colors",
            asOf
              ? "bg-accent-soft text-accent"
              : "text-muted hover:bg-surface-2 hover:text-ink"
          )}
        >
          <Icon name="clock-counter-clockwise" size={16} />
        </button>

        {hasSpeech && (
          <button
            type="button"
            onClick={toggleVoice}
            aria-label={listening ? "Stop listening" : "Speak your question"}
            aria-pressed={listening}
            className={cn(
              "grid size-11 shrink-0 place-items-center rounded-xl transition-colors",
              listening
                ? "bg-[color-mix(in_srgb,var(--danger)_15%,transparent)] text-danger"
                : "text-muted hover:bg-surface-2 hover:text-ink"
            )}
          >
            <Icon name="microphone" size={17} />
          </button>
        )}

        <button
          type="submit"
          disabled={!value.trim()}
          aria-label="Send"
          className="fill-sweep grid size-11 shrink-0 place-items-center bg-accent text-on-accent disabled:opacity-40"
        >
          <Icon name="paper-plane-right" size={17} className="relative z-10" />
        </button>
      </form>
      {voiceError && <p role="status" className="px-2 text-caption text-muted">{voiceError}</p>}
    </div>
  );
}
