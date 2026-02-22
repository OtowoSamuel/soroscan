import * as React from "react"
import { cn } from "@/lib/utils"

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string;
  showScanline?: boolean;
}

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, title, showScanline = true, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "relative border-terminal border-terminal-green bg-terminal-black p-1 font-terminal-mono group overflow-hidden",
          className
        )}
        {...props}
      >
        {/* Box-drawing corners */}
        <div className="absolute top-0 left-0 w-2 h-2 border-t-2 border-l-2 border-terminal-green z-20" />
        <div className="absolute top-0 right-0 w-2 h-2 border-t-2 border-r-2 border-terminal-green z-20" />
        <div className="absolute bottom-0 left-0 w-2 h-2 border-b-2 border-l-2 border-terminal-green z-20" />
        <div className="absolute bottom-0 right-0 w-2 h-2 border-b-2 border-r-2 border-terminal-green z-20" />

        {/* Card Header/Title */}
        {title && (
          <div className="bg-terminal-green text-terminal-black px-2 py-0.5 text-xs font-bold mb-1 flex justify-between items-center">
            <span>{title}</span>
            <span className="opacity-50">[REV. 01]</span>
          </div>
        )}

        <div className="relative z-10 p-4 border border-terminal-green/30">
          {children}
        </div>

        {/* Scanline Effect */}
        {showScanline && (
          <div className="absolute inset-0 bg-linear-to-b from-transparent via-terminal-green/5 to-transparent -translate-y-full group-hover:animate-[scan_3s_linear_infinite] pointer-events-none opacity-20 z-0" />
        )}
        
        {/* Subtle grid background */}
        <div className="absolute inset-0 bg-[radial-gradient(var(--color-terminal-green)_0.5px,transparent_0.5px)] [background-size:16px_16px] opacity-[0.03] pointer-events-none" />
      </div>
    )
  }
)
Card.displayName = "Card"

export { Card }
