 "use client";

 import type { ReactNode } from "react";
 import { ToastProvider } from "@/context/ToastContext";

 interface ProvidersProps {
   children: ReactNode;
 }

 export function Providers({ children }: ProvidersProps) {
   return <ToastProvider>{children}</ToastProvider>;
 }

