import type { Transition } from "framer-motion";

/**
 * Motion tokens: one place for every spring and curve, so components feel like one family.
 *
 * Spring values adapted from EasyUI (github.com/Surajmaurya1/easyui, src/lib/motion-tokens.ts),
 * MIT License, Copyright (c) 2026 Suraj Maurya. See THIRD_PARTY_NOTICE.md next to this file.
 *
 * Tuning rules: damping near critical (no wobble) unless overshoot is the point; settle in
 * ~200 ms for feedback, ~400 ms for layout; keep mass low (0.4-1.0) so motion feels immediate.
 */
export const motionTransitions = {
  /** Tabs, accordions, dialog content: ~400 ms, no overshoot. */
  springGentle: { type: "spring", stiffness: 170, damping: 26, mass: 0.9 } as Transition,
  /** Cards and standard movement: a hint of organic settle. */
  springSmooth: { type: "spring", stiffness: 200, damping: 28, mass: 0.85 } as Transition,
  /** Buttons, hover indicators, dock icons: ~200 ms. */
  springSnappy: { type: "spring", stiffness: 380, damping: 30, mass: 0.5 } as Transition,
  /** Shared-layout morphs (layoutId): long, fluid, no overshoot. */
  springMorph: { type: "spring", stiffness: 220, damping: 32, mass: 1.0 } as Transition,
  /** Magnetic return, toast stacks: a small, satisfying overshoot. */
  springResponsive: { type: "spring", stiffness: 320, damping: 24, mass: 0.7 } as Transition,
  /** Cursor-follow smoothing defaults for useSpring. */
  springSoft: { type: "spring", stiffness: 150, damping: 22, mass: 0.9 } as Transition,
  /** Color and opacity changes. */
  easeSoft: { duration: 0.32, ease: [0.22, 1, 0.36, 1] } as Transition,
  /** Fast property changes, and the stand-in for movement when reduced motion is on. */
  easeFast: { duration: 0.2, ease: [0.2, 0, 0, 1] } as Transition,
};

/** Stagger for lists that reveal one item after another. */
export const stagger = { children: 0.04, max: 0.3 };

/**
 * Pick a transition that respects prefers-reduced-motion: movement becomes a short fade.
 *   const reduce = useReducedMotion();
 *   <motion.div transition={pick(reduce, motionTransitions.springGentle)} />
 */
export function pick(reduce: boolean | null, t: Transition): Transition {
  return reduce ? motionTransitions.easeFast : t;
}
