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

 type ToastType = "success" | "error" | "info" | "warning";

 interface Toast {
   id: string;
   message: string;
   type: ToastType;
 }

 interface ToastContextValue {
   showToast: (message: string, type: ToastType) => void;
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
 let dispatchToast: ((message: string, type: ToastType) => void) | null = null;

 export function ToastProvider({
   children,
   position = "top-right",
   duration = 5000,
 }: ToastProviderProps) {
   const [toasts, setToasts] = useState<Toast[]>([]);

   const dismissToast = useCallback((id: string) => {
     setToasts((current) => current.filter((toast) => toast.id !== id));
   }, []);

   const showToast = useCallback(
     (message: string, type: ToastType) => {
       const id =
         typeof crypto !== "undefined" && "randomUUID" in crypto
           ? crypto.randomUUID()
           : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

       setToasts((current) => [
         // Newest toast on top
         { id, message, type },
         ...current,
       ]);

       window.setTimeout(() => {
         dismissToast(id);
       }, duration);
     },
     [dismissToast, duration],
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
  *   showToast("Event exported!", "success");
  */
 export function showToast(message: string, type: ToastType): void {
   if (!dispatchToast) {
     if (process.env.NODE_ENV !== "production") {
       // eslint-disable-next-line no-console
       console.warn(
         "ToastProvider is not mounted; cannot show toast:",
         message,
       );
     }
     return;
   }
   dispatchToast(message, type);
 }

 interface ToastItemProps {
   toast: Toast;
   onDismiss: () => void;
 }

 function ToastItem({ toast, onDismiss }: ToastItemProps) {
   const { type, message } = toast;

   const isError = type === "error";
   const icon =
     type === "success"
       ? "✓"
       : type === "error"
         ? "✗"
         : type === "warning"
           ? "⚠"
           : "i";

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

       <div className="mt-[2px] text-base" aria-hidden="true">
         {icon}
       </div>
       <div className="flex-1 space-y-1">
         <p className="leading-snug text-foreground">{message}</p>
       </div>
       <button
         type="button"
         onClick={onDismiss}
         className="ml-2 inline-flex h-5 w-5 items-center justify-center rounded-sm border border-terminal-green/40 text-xs text-terminal-green/80 transition hover:border-terminal-green hover:text-terminal-green focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-terminal-cyan"
         aria-label="Dismiss notification"
       >
         ×
       </button>
     </div>
   );
 }

