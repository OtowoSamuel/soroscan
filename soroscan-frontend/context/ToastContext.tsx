 "use client";

 import React, {
   createContext,
   useCallback,
   useContext,
   useEffect,
   useMemo,
   useState,
   type ReactNode,
 } from "react";

 import {
  CheckCircle2,
  AlertCircle,
  Info,
  AlertTriangle,
  X,
} from "lucide-react";

type ToastType = "success" | "error" | "info" | "warning";

 interface Toast {
  id: string;
  title?: string;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  showToast: (message: string, type: ToastType, title?: string) => void;
  dismissToast: (id: string) => void;
}

interface ToastProviderProps {
  children: ReactNode;
  position?: "top-right" | "bottom-right";
  /** Auto-dismiss duration in milliseconds */
  duration?: number;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

/**
 * Module-level dispatcher used by the global showToast() helper.
 * This gets wired up when a ToastProvider mounts.
 */
let dispatchToast: ((message: string, type: ToastType, title?: string) => void) | null = null;

export function ToastProvider({
  children,
  position = "bottom-right",
  duration = 4000,
}: ToastProviderProps) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismissToast = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, type: ToastType, title?: string) => {
      const id =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

      setToasts((current) => [
        // Newest toast on top
        { id, message, type, title },
        ...current,
      ]);

      // Schedule auto-dismiss
      const timer = window.setTimeout(() => {
        setToasts((current) => current.filter((toast) => toast.id !== id));
      }, duration);

      // Return cleanup function (though we can't easily use it here)
      return () => window.clearTimeout(timer);
    },
    [duration],
  );

   useEffect(() => {
     dispatchToast = showToast;
     return () => {
       if (dispatchToast === showToast) {
         dispatchToast = null;
       }
     };
   }, [showToast]);

   const value = useMemo<ToastContextValue>(
     () => ({
       showToast,
       dismissToast,
     }),
     [showToast, dismissToast],
   );

   const positionClasses =
     position === "bottom-right"
       ? "bottom-4 right-4"
       : "top-4 right-4";

   return (
     <ToastContext.Provider value={value}>
       {children}
       <div
         className={`pointer-events-none fixed z-50 flex max-h-screen w-full max-w-sm flex-col gap-3 ${positionClasses}`}
         aria-live="polite"
         aria-atomic="true"
       >
         {toasts.map((toast) => (
           <ToastItem
             key={toast.id}
             toast={toast}
             onDismiss={() => dismissToast(toast.id)}
           />
         ))}
       </div>
     </ToastContext.Provider>
   );
 }

 export function useToast(): ToastContextValue {
   const context = useContext(ToastContext);
   if (!context) {
     throw new Error("useToast must be used within a ToastProvider");
   }
   return context;
 }

 /**
 * Global helper that delegates to the nearest mounted ToastProvider.
 *
 * Example:
 *   showToast("Event exported!", "success", "Export Successful");
 */
export function showToast(message: string, type: ToastType, title?: string): void {
  if (!dispatchToast) {
    if (process.env.NODE_ENV !== "production") {
      console.warn(
        "ToastProvider is not mounted; cannot show toast:",
        message,
      );
    }
    return;
  }
  dispatchToast(message, type, title);
}

 interface ToastItemProps {
   toast: Toast;
   onDismiss: () => void;
 }

 function ToastItem({ toast, onDismiss }: ToastItemProps) {
  const { type, message, title } = toast;

  const isError = type === "error";
  const Icon =
    type === "success"
      ? CheckCircle2
      : type === "error"
        ? AlertCircle
        : type === "warning"
          ? AlertTriangle
          : Info;

  const role = isError ? "alert" : "status";

  const typeClasses =
    type === "success"
      ? "border-terminal-green text-terminal-green shadow-[var(--shadow-glow-green)]"
      : type === "error"
        ? "border-terminal-danger text-terminal-danger shadow-[var(--shadow-glow-danger)]"
        : type === "warning"
          ? "border-terminal-warning text-terminal-warning shadow-[0_0_18px_rgba(255,170,0,0.45)]"
          : "border-terminal-cyan text-terminal-cyan shadow-[var(--shadow-glow-cyan)]";

  return (
    <div
      role={role}
      className={`pointer-events-auto relative flex items-start gap-3 border-l-4 bg-terminal-black/95 px-4 py-3 font-terminal-mono text-sm ${typeClasses}`}
    >
      {/* Box-drawing style frame */}
      <div className="absolute inset-0 border border-terminal-green/20" aria-hidden="true" />

      <div className="mt-0.5 flex-shrink-0" aria-hidden="true">
        <Icon className="h-5 w-5" />
      </div>
      <div className="flex-1 space-y-1">
        {title && (
          <h4 className="font-bold leading-none tracking-tight text-foreground">
            {title}
          </h4>
        )}
        <p className="leading-snug text-foreground/90">{message}</p>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        className="ml-2 inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-sm border border-terminal-green/40 text-terminal-green/80 transition hover:border-terminal-green hover:text-terminal-green focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-terminal-cyan"
        aria-label="Dismiss notification"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}

