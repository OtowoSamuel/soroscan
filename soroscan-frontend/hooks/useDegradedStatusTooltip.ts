/**
 * Degraded Status Tooltip Hook
 * ──────────────────────────────────────────────────────────────────────────────
 * React hook for managing dynamic tooltip content for degraded contract status.
 * 
 * Features:
 * - Real-time tooltip content generation
 * - Context-aware content formatting
 * - Auto-refresh for time-sensitive information
 * - Performance optimization with memoization
 * - Integration with monitoring systems
 */

import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  DegradationContext,
  DegradationType,
  DEGRADATION_CONTENT_TEMPLATES,
  generateDegradedTooltipContent,
  generateAccessibleTooltipContent,
  formatTooltipForContext,
  validateTooltipContent,
  TOOLTIP_CONTENT_GUIDELINES,
  COMMON_DEGRADATION_SCENARIOS
} from '@/lib/tooltip-content-guidelines';

export interface TooltipContentOptions {
  /** UI context for appropriate content formatting */
  uiContext?: keyof typeof TOOLTIP_CONTENT_GUIDELINES;
  /** Whether to use accessible format for screen readers */
  accessibleFormat?: boolean;
  /** Auto-refresh interval in milliseconds (0 to disable) */
  refreshInterval?: number;
  /** Custom content override */
  customContent?: string;
  /** Whether to validate content before returning */
  validateContent?: boolean;
}

export interface TooltipContentState {
  /** Generated tooltip content */
  content: string;
  /** Whether content is currently loading/updating */
  isLoading: boolean;
  /** Content validation results */
  validation?: {
    isValid: boolean;
    errors: string[];
    warnings: string[];
  };
  /** Timestamp of last content update */
  lastUpdated: Date;
}

/**
 * Hook for managing degraded status tooltip content
 */
export function useDegradedStatusTooltip(
  degradationContext: DegradationContext | null,
  options: TooltipContentOptions = {}
): TooltipContentState & {
  /** Manually refresh tooltip content */
  refresh: () => void;
  /** Update degradation context */
  updateContext: (context: DegradationContext) => void;
} {
  const {
    uiContext = 'dashboard',
    accessibleFormat = false,
    refreshInterval = 0,
    customContent,
    validateContent = true
  } = options;

  const [isLoading, setIsLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(new Date());
  const [currentContext, setCurrentContext] = useState(degradationContext);

  useEffect(() => {
    setCurrentContext(degradationContext);
  }, [degradationContext]);

  // Generate tooltip content
  const content = useMemo(() => {
    if (customContent) {
      return customContent;
    }

    if (!currentContext) {
      return '';
    }

    try {
      if (accessibleFormat) {
        return generateAccessibleTooltipContent(currentContext);
      }

      return formatTooltipForContext(currentContext, uiContext);
    } catch (error) {
      console.warn('Error generating tooltip content:', error);
      return 'Contract experiencing performance issues';
    }
  }, [currentContext, uiContext, accessibleFormat, customContent]);

  // Validate content if enabled
  const validation = useMemo(() => {
    if (!validateContent || !content) {
      return undefined;
    }

    return validateTooltipContent(content);
  }, [content, validateContent]);

  // Manual refresh function
  const refresh = useCallback(() => {
    setIsLoading(true);
    setLastUpdated(new Date());
    
    // Simulate async content update (e.g., fetching fresh metrics)
    setTimeout(() => {
      setIsLoading(false);
    }, 100);
  }, []);

  // Update degradation context
  const updateContext = useCallback((context: DegradationContext) => {
    setCurrentContext(context);
    setIsLoading(true);
    setLastUpdated(new Date());
    
    // The context update will trigger content regeneration via the useMemo
    setTimeout(() => {
      setIsLoading(false);
    }, 50);
  }, []);

  // Auto-refresh effect
  useEffect(() => {
    if (refreshInterval <= 0) return;

    const interval = setInterval(() => {
      refresh();
    }, refreshInterval);

    return () => clearInterval(interval);
  }, [refreshInterval, refresh]);

  return {
    content,
    isLoading,
    validation,
    lastUpdated,
    refresh,
    updateContext
  };
}

/**
 * Hook for common degradation scenarios
 */
export function useCommonDegradationTooltips() {
  const scenarios = useMemo(() => {
    return Object.entries(COMMON_DEGRADATION_SCENARIOS).reduce(
      (acc, [key, context]) => {
        acc[key as keyof typeof COMMON_DEGRADATION_SCENARIOS] = {
          brief: formatTooltipForContext(context, 'contractList'),
          detailed: formatTooltipForContext(context, 'contractDetail'),
          accessible: generateAccessibleTooltipContent(context)
        };
        return acc;
      },
      {} as Record<keyof typeof COMMON_DEGRADATION_SCENARIOS, {
        brief: string;
        detailed: string;
        accessible: string;
      }>
    );
  }, []);

  return scenarios;
}

/**
 * Hook for monitoring tooltip performance and usage analytics
 */
export function useTooltipAnalytics() {
  const [metrics, setMetrics] = useState({
    tooltipShows: 0,
    averageViewTime: 0,
    mostViewedTypes: new Map<DegradationType, number>(),
    contentErrors: 0
  });

  const trackTooltipShow = useCallback((type: DegradationType) => {
    setMetrics(prev => ({
      ...prev,
      tooltipShows: prev.tooltipShows + 1,
      mostViewedTypes: new Map(prev.mostViewedTypes).set(
        type, 
        (prev.mostViewedTypes.get(type) || 0) + 1
      )
    }));
  }, []);

  const trackContentError = useCallback(() => {
    setMetrics(prev => ({
      ...prev,
      contentErrors: prev.contentErrors + 1
    }));
  }, []);

  const trackViewTime = useCallback((duration: number) => {
    setMetrics(prev => ({
      ...prev,
      averageViewTime: (prev.averageViewTime + duration) / 2
    }));
  }, []);

  return {
    metrics,
    trackTooltipShow,
    trackContentError,
    trackViewTime
  };
}

/**
 * Utility functions for tooltip content management
 */
export const TooltipUtils = {
  /**
   * Get appropriate tooltip for contract health status
   */
  getHealthStatusTooltip: (
    status: 'healthy' | 'degraded' | 'paused' | 'error' | 'offline',
    context?: Partial<DegradationContext>
  ): string => {
    switch (status) {
      case 'healthy':
        return 'Contract is operating normally with all systems functional';
      
      case 'paused':
        return 'Contract operations are temporarily suspended';
      
      case 'error':
        return 'Contract has encountered critical errors and is non-functional';

      case 'offline':
        return 'Contract is currently offline or unreachable';
      
      case 'degraded':
        if (context) {
          return generateDegradedTooltipContent(context as DegradationContext);
        }
        return 'Contract is experiencing performance issues or reduced functionality';
      
      default:
        return 'Contract status unknown';
    }
  },

  /**
   * Format tooltip for specific screen readers
   */
  formatForScreenReader: (content: string): string => {
    return content
      .replace(/\*\*/g, '') // Remove markdown bold
      .replace(/\n+/g, '. ') // Convert line breaks to periods
      .replace(/•/g, '') // Remove bullet points
      .replace(/\s+/g, ' ') // Normalize whitespace
      .trim();
  },

  /**
   * Truncate tooltip content for mobile displays
   */
  truncateForMobile: (content: string, maxLength: number = 80): string => {
    if (content.length <= maxLength) {
      return content;
    }

    const truncated = content.substring(0, maxLength - 3);
    const lastSpace = truncated.lastIndexOf(' ');
    
    return (lastSpace > maxLength * 0.7 ? truncated.substring(0, lastSpace) : truncated) + '...';
  },

  /**
   * Extract key information for compact displays
   */
  getCompactSummary: (context: DegradationContext): string => {
    const template = DEGRADATION_CONTENT_TEMPLATES[context.type];
    let summary = template?.title || 'Degraded';

    if (context.details?.errorRate) {
      summary += ` (${context.details.errorRate}% errors)`;
    } else if (context.details?.responseTime) {
      summary += ` (${context.details.responseTime}ms)`;
    }

    if (context.autoRecoveryActive) {
      summary += ' - Auto-recovering';
    }

    return summary;
  }
};