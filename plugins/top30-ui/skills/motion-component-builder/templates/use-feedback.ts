/**
 * useFeedback: a short vibration (and, if you opt in, a quiet tick) to confirm an action.
 *
 *   const feedback = useFeedback();            // vibration only
 *   const feedback = useFeedback({ sound: true });
 *   <button onClick={() => { copy(); feedback('success'); }}>Copy</button>
 *
 * The idea of pairing copy, click and error with a haptic cue comes from Amicro's useWebHaptics
 * hook (github.com/Subhan-code/Amicro--Micro-transitions-, MIT). This is an independent
 * implementation. Rules it follows: sound is off unless asked for, nothing fires under
 * prefers-reduced-motion, it only runs from a user gesture, and every failure is silent because
 * feedback is never required for the action to work.
 */
import { useCallback, useRef } from "react";

export type FeedbackKind = "light" | "medium" | "success" | "warning" | "error";

const PATTERNS: Record<FeedbackKind, number[]> = {
  light: [8],
  medium: [14],
  success: [10, 40, 16],
  warning: [18, 60, 18],
  error: [24, 50, 24, 50, 24],
};
const TONES: Record<FeedbackKind, [frequency: number, ms: number]> = {
  light: [660, 30],
  medium: [520, 40],
  success: [880, 70],
  warning: [440, 90],
  error: [220, 120],
};

export function useFeedback({ sound = false, volume = 0.04 }: { sound?: boolean; volume?: number } = {}) {
  const ctxRef = useRef<AudioContext | null>(null);
  return useCallback(
    (kind: FeedbackKind = "light") => {
      if (typeof window === "undefined") return;
      if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
      try {
        navigator.vibrate?.(PATTERNS[kind]);
      } catch {
        /* unsupported or blocked: fine */
      }
      if (!sound) return;
      try {
        const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (!Ctx) return;
        const ctx = (ctxRef.current ??= new Ctx());
        if (ctx.state === "suspended") void ctx.resume();
        const [frequency, ms] = TONES[kind];
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.frequency.value = frequency;
        gain.gain.setValueAtTime(volume, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + ms / 1000);
        osc.connect(gain).connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + ms / 1000);
      } catch {
        /* audio blocked: fine */
      }
    },
    [sound, volume],
  );
}
