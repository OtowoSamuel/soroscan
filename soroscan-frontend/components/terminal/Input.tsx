import * as React from "react"
import { cn } from "@/lib/utils"

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
    label?: string;
  }

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, label, ...props }, ref) => {
    return (
      <div className="w-full space-y-1 group">
        {label && (
          <label className="text-xs font-terminal-mono text-terminal-cyan uppercase tracking-wider block ml-1">
            {label}
          </label>
        )}
        <div className="relative flex items-center">
          <span className="absolute left-3 text-terminal-green font-terminal-mono group-focus-within:animate-pulse">
            &gt;
          </span>
          <input
            type={type}
            className={cn(
              "flex h-10 w-full bg-terminal-black border-terminal border-terminal-gray/30 px-8 py-2 text-sm font-terminal-mono text-terminal-green ring-offset-terminal-black file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-terminal-gray/50 focus-visible:outline-none focus-visible:border-terminal-green focus-visible:shadow-glow-green/20 transition-all disabled:cursor-not-allowed disabled:opacity-50",
              className
            )}
            ref={ref}
            {...props}
          />
          {/* Active status indicator */}
          <div className="absolute right-3 w-2 h-2 rounded-full border border-terminal-green/30 group-focus-within:bg-terminal-green group-focus-within:shadow-glow-green transition-all" />
        </div>
      </div>
    )
  }
)
Input.displayName = "Input"

export { Input }
