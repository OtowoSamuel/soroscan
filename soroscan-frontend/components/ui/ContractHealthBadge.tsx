/**
 * Contract Health Badge Component
 * ──────────────────────────────────────────────────────────────────────────────
 * Visual status badges for contract health indicators in SoroScan explorer.
 * 
 * Features:
 * - Four distinct health states: Healthy, Degraded, Paused, Error
 * - Animated pulse dots for active states
 * - Terminal-themed color scheme with exact hex values
 * - Tooltip integration for degraded status explanations
 * - Multiple size variants and display modes
 * - Full accessibility support (WCAG 2.1 AA compliant)
 * - Consistent with SoroScan terminal design system
 */
"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { 
  CheckCircle, 
  AlertTriangle, 
  Pause, 
  XCircle, 
  Activity
} from "lucide-react";
import { cn } from "@/lib/utils";
import { 
  useStatusAnimation,
  type AnimationType,
  type AnimationContext 
} from "@/lib/status-animations";
import {
  useDegradedStatusTooltip,
  TooltipUtils
} from "@/hooks/useDegradedStatusTooltip";
import { type DegradationContext } from "@/lib/tooltip-content-guidelines";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export type ContractHealthStatus = "healthy" | "degraded" | "paused" | "error" | "offline";

/**
 * Health Status Configuration with exact color specifications
 */
export const HEALTH_STATUS_CONFIG = {
  healthy: {
    label: "Healthy",
    description: "Contract is operating normally with all systems functional",
    colors: {
      primary: "#00e5ff", // terminal-green
      background: "rgba(0, 229, 255, 0.1)", // 10% opacity
      border: "rgba(0, 229, 255, 0.3)", // 30% opacity
      glow: "0 0 16px rgba(0, 229, 255, 0.45), 0 0 4px rgba(0, 229, 255, 0.35)"
    },
    icon: CheckCircle,
    animate: true,
    severity: "success"
  },
  degraded: {
    label: "Degraded", 
    description: "Contract experiencing performance issues or partial functionality loss",
    colors: {
      primary: "#ffaa00", // terminal-warning
      background: "rgba(255, 170, 0, 0.1)",
      border: "rgba(255, 170, 0, 0.3)",
      glow: "0 0 16px rgba(255, 170, 0, 0.4), 0 0 4px rgba(255, 170, 0, 0.3)"
    },
    icon: AlertTriangle,
    animate: true,
    severity: "warning"
  },
  paused: {
    label: "Paused",
    description: "Contract operations temporarily suspended",
    colors: {
      primary: "#38bdf8", // terminal-cyan  
      background: "rgba(56, 189, 248, 0.1)",
      border: "rgba(56, 189, 248, 0.3)",
      glow: "0 0 16px rgba(56, 189, 248, 0.45), 0 0 4px rgba(56, 189, 248, 0.35)"
    },
    icon: Pause,
    animate: false,
    severity: "info"
  },
  error: {
    label: "Error",
    description: "Contract has encountered critical errors and is non-functional",
    colors: {
      primary: "#ff3366", // terminal-danger
      background: "rgba(255, 51, 102, 0.1)",
      border: "rgba(255, 51, 102, 0.3)", 
      glow: "0 0 16px rgba(255, 51, 102, 0.4), 0 0 4px rgba(255, 51, 102, 0.3)"
    },
    icon: XCircle,
    animate: false,
    severity: "error"
  },
  offline: {
    label: "Offline",
    description: "Contract is currently offline or unreachable",
    colors: {
      primary: "#94a3b8", // terminal-gray / slate-400
      background: "rgba(148, 163, 184, 0.1)",
      border: "rgba(148, 163, 184, 0.3)",
      glow: "0 0 16px rgba(148, 163, 184, 0.4), 0 0 4px rgba(148, 163, 184, 0.3)"
    },
    icon: XCircle,
    animate: false,
    severity: "error"
  }
} as const;

export const STATUS_BACKGROUND_CLASSES: Record<ContractHealthStatus, string> = {
  healthy: "bg-terminal-green/10 border-terminal-green/30 text-terminal-green status-healthy",
  degraded: "bg-terminal-warning/10 border-terminal-warning/30 text-terminal-warning status-degraded",
  paused: "bg-terminal-cyan/10 border-terminal-cyan/30 text-terminal-cyan status-paused",
  error: "bg-terminal-danger/10 border-terminal-danger/30 text-terminal-danger status-error",
  offline: "bg-terminal-gray/10 border-terminal-gray/30 text-terminal-gray status-offline",
};

const healthBadgeVariants = cva(
  [
    "inline-flex items-center gap-2 font-terminal-mono font-semibold uppercase tracking-wider",
    "border transition-all duration-300 ease-standard",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2",
    "select-none cursor-default"
  ],
  {
    variants: {
      variant: {
        default: "rounded-full",
        compact: "rounded-sm gap-1.5",
        pill: "rounded-full px-4 py-2",
        square: "rounded-sm"
      },
      size: {
        sm: "h-5 px-2 py-0.5 text-xs",
        md: "h-6 px-3 py-1 text-xs", 
        lg: "h-8 px-4 py-1.5 text-sm"
      },
      glow: {
        none: "",
        subtle: "shadow-sm",
        moderate: "", // Applied via CSS custom properties
        intense: "" // Applied via CSS custom properties
      }
    },
    defaultVariants: {
      variant: "default",
      size: "md", 
      glow: "subtle"
    }
  }
);

const statusDotVariants = cva(
  ["inline-block rounded-full shrink-0 transition-all duration-300"],
  {
    variants: {
      size: {
        sm: "w-1.5 h-1.5",
        md: "w-2 h-2", 
        lg: "w-2.5 h-2.5"
      }
    },
    defaultVariants: {
      size: "md"
    }
  }
);

export interface ContractHealthBadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof healthBadgeVariants> {
  /** The health status to display */
  status: ContractHealthStatus;
  /** Custom label to override default */
  label?: string;
  /** Show only the status dot without text */
  dotOnly?: boolean;
  /** Show status icon instead of/alongside dot */
  showIcon?: boolean;
  /** Additional metrics to display */
  metrics?: {
    eventCount?: number;
    uptime?: string;
    lastActivity?: string;
  };
  /** Degradation context for detailed tooltip content */
  degradationContext?: DegradationContext;
  /** Custom tooltip content override */
  tooltipContent?: string;
  /** Disable tooltip completely */
  disableTooltip?: boolean;
  /** Animation context for appropriate animation intensity */
  animationContext?: AnimationContext;
  /** Disable animations */
  disableAnimation?: boolean;
  /** Additional context for screen readers */
  "aria-label"?: string;
}

const ContractHealthBadge = React.forwardRef<HTMLSpanElement, ContractHealthBadgeProps>(
  ({ 
    className,
    variant,
    size,
    glow,
    status,
    label,
    dotOnly = false,
    showIcon = false,
    metrics,
    degradationContext,
    tooltipContent,
    disableTooltip = false,
    animationContext = "dashboard",
    disableAnimation = false,
    "aria-label": ariaLabel,
    style,
    ...props
  }, ref) => {
    const config = HEALTH_STATUS_CONFIG[status as keyof typeof HEALTH_STATUS_CONFIG] || HEALTH_STATUS_CONFIG.error;
    const displayLabel = label ?? config.label;
    const Icon = config.icon;
    
    // Animation setup
    const animationType: AnimationType = status === "healthy" || status === "degraded" 
      ? status 
      : "static";
    
    const { elementRef, animationClasses, animationStyles } = useStatusAnimation(
      disableAnimation ? "static" : animationType,
      "normal",
      animationContext
    );
    const setBadgeRef = React.useCallback((node: HTMLSpanElement | null) => {
      elementRef.current = node;
      if (typeof ref === "function") {
        ref(node);
      } else if (ref) {
        ref.current = node;
      }
    }, [elementRef, ref]);

    // Tooltip content setup
    const tooltipState = useDegradedStatusTooltip(
      status === "degraded" ? degradationContext || null : null,
      {
        uiContext: animationContext === "contract-list" ? "contractList" : "dashboard",
        refreshInterval: status === "degraded" ? 30000 : 0, // Refresh every 30s for degraded status
      }
    );

    // Determine tooltip content
    const finalTooltipContent = React.useMemo(() => {
      if (disableTooltip) return "";
      
      if (tooltipContent) return tooltipContent;
      
      if (status === "degraded" && degradationContext) {
        return tooltipState.content || TooltipUtils.getHealthStatusTooltip(status, degradationContext);
      }
      
      return TooltipUtils.getHealthStatusTooltip(status);
    }, [status, tooltipContent, degradationContext, tooltipState.content, disableTooltip]);
    
    const accessibleLabel = ariaLabel ?? `Contract health: ${displayLabel}`;

    const hasTooltip = !disableTooltip && Boolean(finalTooltipContent);

    // Dynamic styles for colors and glow effects
    const dynamicStyles: React.CSSProperties = {
      ...style,
      color: config.colors.primary,
      backgroundColor: config.colors.background,
      borderColor: config.colors.border,
      ...(glow === "moderate" && {
        boxShadow: `0 0 8px ${config.colors.border}`
      }),
      ...(glow === "intense" && {
        boxShadow: config.colors.glow
      })
    };

    // Combine animation styles with dot styles
    const dotStyles: React.CSSProperties = {
      backgroundColor: config.colors.primary,
      ...animationStyles
    };

    const badgeContent = (
      <span
        ref={setBadgeRef}
        role="status"
        aria-label={accessibleLabel}
        tabIndex={hasTooltip ? 0 : undefined}
        className={cn(
          healthBadgeVariants({ variant, size, glow }),
          STATUS_BACKGROUND_CLASSES[status as ContractHealthStatus] || STATUS_BACKGROUND_CLASSES.error,
          animationClasses,
          className
        )}
        style={dynamicStyles}
        {...props}
      >
        {/* Status Dot */}
        {!showIcon && (
          <span
            aria-hidden="true"
            className={cn(
              statusDotVariants({ size }),
              animationClasses
            )}
            style={dotStyles}
          />
        )}

        {/* Status Icon */}
        {showIcon && Icon && (
          <Icon
            aria-hidden="true"
            size={size === "sm" ? 12 : size === "lg" ? 16 : 14}
            className="shrink-0"
            style={{ color: config.colors.primary }}
          />
        )}

        {/* Status Label */}
        {!dotOnly && (
          <span className="font-medium">
            {displayLabel}
          </span>
        )}

        {/* Additional Metrics */}
        {metrics && !dotOnly && (
          <span className="ml-2 flex items-center gap-2 text-xs opacity-75">
            {metrics.eventCount && (
              <span className="flex items-center gap-1">
                <Activity size={10} />
                {metrics.eventCount > 1000 
                  ? `${(metrics.eventCount / 1000).toFixed(1)}k`
                  : metrics.eventCount
                }
              </span>
            )}
            {metrics.uptime && (
              <span>{metrics.uptime}</span>
            )}
          </span>
        )}

        {/* Loading indicator for tooltip updates */}
        {status === "degraded" && tooltipState.isLoading && (
          <span className="ml-1 animate-spin">
            <Activity size={10} />
          </span>
        )}
      </span>
    );

    // Return with or without tooltip
    if (!hasTooltip) {
      return badgeContent;
    }

    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            {badgeContent}
          </TooltipTrigger>
          <TooltipContent 
            side="top"
            className="max-w-sm font-terminal-mono text-xs"
            sideOffset={4}
          >
            <div className="whitespace-pre-wrap">
              {finalTooltipContent}
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }
);

ContractHealthBadge.displayName = "ContractHealthBadge";

export { ContractHealthBadge, healthBadgeVariants };

/**
 * Preset configurations for common use cases
 */
export const HealthBadgePresets = {
  contractList: {
    variant: "default" as const,
    size: "md" as const,
    glow: "subtle" as const
  },
  contractDetail: {
    variant: "pill" as const,
    size: "lg" as const,
    glow: "moderate" as const,
    showIcon: true
  },
  compactView: {
    variant: "compact" as const,
    size: "sm" as const,
    dotOnly: true
  },
  dashboard: {
    variant: "square" as const,
    size: "md" as const,
    glow: "moderate" as const
  }
} as const;
