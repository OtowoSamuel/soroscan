import * as React from "react"

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
}

const Modal: React.FC<ModalProps> = ({ isOpen, onClose, title, children }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Dark Overlay */}
      <div 
        className="absolute inset-0 bg-terminal-black/80 backdrop-blur-sm cursor-pointer" 
        onClick={onClose}
      />
      
      {/* Modal Container */}
      <div className="relative w-full max-w-lg border-terminal border-terminal-green bg-terminal-black p-1 shadow-glow-green/30 animate-in zoom-in-95 duration-200">
        {/* Box corners */}
        <div className="absolute top-0 left-0 w-2 h-2 border-t-2 border-l-2 border-terminal-green" />
        <div className="absolute top-0 right-0 w-2 h-2 border-t-2 border-r-2 border-terminal-green" />
        <div className="absolute bottom-0 left-0 w-2 h-2 border-b-2 border-l-2 border-terminal-green" />
        <div className="absolute bottom-0 right-0 w-2 h-2 border-b-2 border-r-2 border-terminal-green" />

        {/* Modal Header */}
        <div className="bg-terminal-green text-terminal-black px-4 py-2 font-terminal-mono font-bold flex justify-between items-center">
          <span>[{title || "MESSAGE"}]</span>
          <button 
            onClick={onClose}
            className="hover:scale-110 transition-transform cursor-pointer"
          >
            [X]
          </button>
        </div>

        {/* Modal Content */}
        <div className="p-6 font-terminal-mono text-terminal-green border border-terminal-green/30 m-1">
          {children}
        </div>

        {/* Modal Footer (Decorative) */}
        <div className="h-4 bg-terminal-green/10 flex items-center px-4 justify-between border-t border-terminal-green/30">
          <div className="text-[10px] text-terminal-green/50">SYSTEM_AUTH_REQUIRED</div>
          <div className="flex gap-2">
             <div className="w-1 h-1 bg-terminal-green animate-pulse" />
             <div className="w-1 h-1 bg-terminal-green animate-pulse delay-75" />
             <div className="w-1 h-1 bg-terminal-green animate-pulse delay-150" />
          </div>
        </div>
      </div>
    </div>
  );
};

export { Modal }
