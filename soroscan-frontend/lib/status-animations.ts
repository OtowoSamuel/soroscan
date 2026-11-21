/**
 * Status Pulse Animation Utilities
 * ──────────────────────────────────────────────────────────────────────────────
 * TypeScript utilities for managing status pulse dot animations.
 * 
 * Provides:
 * - Animation configuration constants
 * - Programmatic animation control
 * - Performance optimization utilities
 * - Accessibility-aware animation management
 * - Tailwind status badge color configurations
 */

import * as React from "react";

export type AnimationType =
  | "healthy"
  | "degraded"
  | "processing"
  | "heartbeat"
  | "static";

export type AnimationIntensity = "subtle" | "normal" | "urgent";

export type AnimationContext =
  | "contract-list"
  | "dashboard"
  | "detail-view"
  | "compact"
  | "notification";

/**
 * Status Badge Color Mappings
 * Updated degraded status from yellow-400 to amber-500 palette for better visual hierarchy.
 */
export const STATUS_BADGE_STYLES: Record<AnimationType, string> = {
  healthy: "bg-green-100 text-green-700 border border-green-500",
  degraded: "bg-amber-100 text-amber-700 border border-amber-500",
  processing: "bg-blue-100 text-blue-700 border border-blue-500",
  heartbeat: "bg-red-100 text-red-700 border border-red-500",
  static: "bg-gray-100 text-gray-700 border border-gray-500"
};

/**
 * Animation Timing Specifications
 */
export const ANIMATION_TIMINGS = {
  healthy: {
    subtle: 3000,    // 3s - Very gentle for background elements
    normal: 2000,    // 2s - Standard breathing pulse
    urgent: 1500,    // 1.5s - Faster for active monitoring
  },
  degraded: {
    subtle: 2500,    // 2.5s - Gentle warning
    normal: 1800,    // 1.8s - Standard attention-seeking
    urgent: 1200,    // 1.2s - Urgent attention needed
  },
  processing: {
    subtle: 2200,    // 2.2s - Background processing
    normal: 1500,    // 1.5s - Active processing
    urgent: 1000,    // 1s - High priority processing
  },
  heartbeat: {
    subtle: 3000,    // 3s - Gentle double-pulse
    normal: 2500,    // 2.5s - Standard heartbeat
    urgent: 2000,    // 2s - Urgent heartbeat pattern
  }
} as const;

/**
 * Context-specific animation configurations
 */
export const ANIMATION_CONTEXTS = {
  "contract-list": {
    intensity: "subtle" as const,
    enableGlow: false,
    pauseOnHover: false,
  },
  "dashboard": {
    intensity: "normal" as const,
    enableGlow: true,
    pauseOnHover: false,
  },
  "detail-view": {
    intensity: "normal" as const,
    enableGlow: true,
    pauseOnHover: true,
  },
  "compact": {
    intensity: "subtle" as const,
    enableGlow: false,
    pauseOnHover: false,
  },
  "notification": {
    intensity: "urgent" as const,
    enableGlow: true,
    pauseOnHover: false,
  }
} as const;

/**
 * CSS class name builders for animations
 */
export function getAnimationClasses(
  type: AnimationType,
  intensity: AnimationIntensity = "normal",
  context?: AnimationContext,
  size?: "sm" | "md" | "lg"
): string {
  const classes: string[] = [];

  // Base animation class
  if (type === "static") {
    return ""; // No animation classes
  }

  const baseClass = `status-pulse-${type}`;
  const intensityModifier = intensity !== "normal" ? `-${intensity}` : "";

  classes.push(`${baseClass}${intensityModifier}`);

  // Add size-specific class if provided
  if (size) {
    classes.push(`status-dot-${size}`);
  }

  // Add context-specific class if provided
  if (context) {
    classes.push(context);
  }

  return classes.join(" ");
}

/**
 * Generate CSS custom properties for dynamic animation control
 */
export function getAnimationStyles(
  type: AnimationType,
  intensity: AnimationIntensity = "normal",
  customDuration?: number
): React.CSSProperties {
  if (type === "static") {
    return {};
  }

  const duration = customDuration || ANIMATION_TIMINGS[type]?.[intensity] || 2000;

  return {
    "--animation-duration": `${duration}ms`,
    animationDuration: `${duration}ms`,
  } as React.CSSProperties;
}

/**
 * Animation Performance Utilities
 */
export class AnimationManager {
  private static observers = new Map<Element, IntersectionObserver>();

  /**
   * Optimize animations by pausing when elements are not visible
   */
  static observeElement(element: Element): void {
    if (this.observers.has(element)) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const target = entry.target as HTMLElement;
          target.dataset.visible = entry.isIntersecting.toString();

          if (!entry.isIntersecting) {
            target.style.animationPlayState = "paused";
          } else {
            target.style.animationPlayState = "running";
          }
        });
      },
      {
        rootMargin: "50px", // Start animation slightly before element is visible
        threshold: 0.1,
      }
    );

    observer.observe(element);
    this.observers.set(element, observer);
  }

  /**
   * Clean up intersection observer
   */
  static unobserveElement(element: Element): void {
    const observer = this.observers.get(element);
    if (observer) {
      observer.unobserve(element);
      observer.disconnect();
      this.observers.delete(element);
    }
  }

  /**
   * Check if user prefers reduced motion
   */
  static shouldReduceMotion(): boolean {
    if (typeof window === "undefined") return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  /**
   * Pause all animations globally (useful for performance debugging)
   */
  static pauseAllAnimations(): void {
    document.documentElement.style.setProperty("--global-animation-play-state", "paused");
  }

  /**
   * Resume all animations globally
   */
  static resumeAllAnimations(): void {
    document.documentElement.style.setProperty("--global-animation-play-state", "running");
  }
}

/**
 * React Hook for managing status animations
 */
export function useStatusAnimation(
  type: AnimationType,
  intensity: AnimationIntensity = "normal",
  context?: AnimationContext
) {
  const [isPaused, setIsPaused] = React.useState(false);
  const elementRef = React.useRef<HTMLElement>(null);

  React.useEffect(() => {
    const element = elementRef.current;
    if (!element) return;

    // Set up intersection observer for performance optimization
    AnimationManager.observeElement(element);

    return () => {
      if (element) {
        AnimationManager.unobserveElement(element);
      }
    };
  }, []);

  const animationClasses = React.useMemo(() => {
    if (AnimationManager.shouldReduceMotion() || isPaused) {
      return "";
    }

    const contextConfig = context ? ANIMATION_CONTEXTS[context] : { intensity: "normal" as const };
    const effectiveIntensity = contextConfig.intensity || intensity;

    return getAnimationClasses(type, effectiveIntensity, context);
  }, [type, intensity, context, isPaused]);

  const animationStyles = React.useMemo(() => {
    if (AnimationManager.shouldReduceMotion() || isPaused) {
      return {};
    }

    const contextConfig = context ? ANIMATION_CONTEXTS[context] : { intensity: "normal" as const };
    const effectiveIntensity = contextConfig.intensity || intensity;

    return getAnimationStyles(type, effectiveIntensity);
  }, [type, intensity, context, isPaused]);

  return {
    elementRef,
    animationClasses,
    animationStyles,
    badgeClasses: STATUS_BADGE_STYLES[type],
    isVisible: true,
    isPaused,
    pauseAnimation: () => setIsPaused(true),
    resumeAnimation: () => setIsPaused(false),
    toggleAnimation: () => setIsPaused(prev => !prev),
  };
}

/**
 * Animation presets for common use cases
 */
export const ANIMATION_PRESETS = {
  contractListHealthy: {
    type: "healthy" as const,
    intensity: "subtle" as const,
    context: "contract-list" as const,
  },
  contractListDegraded: {
    type: "degraded" as const,
    intensity: "subtle" as const,
    context: "contract-list" as const,
  },
  dashboardHealthy: {
    type: "healthy" as const,
    intensity: "normal" as const,
    context: "dashboard" as const,
  },
  dashboardDegraded: {
    type: "degraded" as const,
    intensity: "normal" as const,
    context: "dashboard" as const,
  },
  detailViewHealthy: {
    type: "healthy" as const,
    intensity: "normal" as const,
    context: "detail-view" as const,
  },
  detailViewDegraded: {
    type: "degraded" as const,
    intensity: "urgent" as const,
    context: "detail-view" as const,
  },
  processingState: {
    type: "processing" as const,
    intensity: "normal" as const,
    context: "dashboard" as const,
  },
  criticalAlert: {
    type: "heartbeat" as const,
    intensity: "urgent" as const,
    context: "notification" as const,
  },
} as const;