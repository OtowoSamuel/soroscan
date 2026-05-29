import React from 'react';

// Track open state globally for the mock
let globalOpen = false;
let globalOnOpenChange: ((open: boolean) => void) | null = null;

export const Root = ({ children, open, onOpenChange, defaultOpen }: any) => {
  const [isOpen, setIsOpen] = React.useState(open ?? defaultOpen ?? false);
  
  React.useEffect(() => {
    if (open !== undefined) {
      setIsOpen(open);
      globalOpen = open;
    }
  }, [open]);

  React.useEffect(() => {
    globalOnOpenChange = onOpenChange || null;
  }, [onOpenChange]);

  const handleOpenChange = React.useCallback((newOpen: boolean) => {
    setIsOpen(newOpen);
    globalOpen = newOpen;
    onOpenChange?.(newOpen);
  }, [onOpenChange]);

  // Provide context to children
  const contextValue = React.useMemo(() => ({
    open: isOpen,
    onOpenChange: handleOpenChange,
  }), [isOpen, handleOpenChange]);

  return React.createElement(
    DialogContext.Provider,
    { value: contextValue },
    children
  );
};

const DialogContext = React.createContext<any>(null);

export const Trigger = React.forwardRef(({ children, onClick, ...props }: any, ref: any) => {
  const context = React.useContext(DialogContext);
  
  const handleClick = (e: any) => {
    onClick?.(e);
    context?.onOpenChange?.(!context.open);
  };

  return React.createElement('button', { 
    ref, 
    onClick: handleClick,
    'data-testid': props['data-testid'],
    ...props 
  }, children);
});
Trigger.displayName = 'DialogTrigger';

export const Portal = ({ children }: any) => {
  const context = React.useContext(DialogContext);
  
  if (!context?.open) {
    return null;
  }
  
  return React.createElement('div', { 'data-radix-portal': true }, children);
};

export const Overlay = React.forwardRef(({ children, onClick, ...props }: any, ref: any) => {
  const context = React.useContext(DialogContext);
  
  if (!context?.open) {
    return null;
  }
  
  return React.createElement('div', { 
    ref, 
    'data-radix-overlay': true,
    'data-state': context?.open ? 'open' : 'closed',
    onClick,
    ...props 
  }, children);
});
Overlay.displayName = 'DialogOverlay';

export const Content = React.forwardRef(({ children, onEscapeKeyDown, onPointerDownOutside, ...props }: any, ref: any) => {
  const context = React.useContext(DialogContext);
  
  React.useEffect(() => {
    if (!context?.open) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onEscapeKeyDown?.(e);
        if (!e.defaultPrevented) {
          context?.onOpenChange?.(false);
        }
      }
    };
    
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [context, onEscapeKeyDown]);

  if (!context?.open) {
    return null;
  }

  // Add focus guards to simulate Radix UI's focus trap
  return React.createElement(
    React.Fragment,
    null,
    React.createElement('span', { 'data-radix-focus-guard': true, tabIndex: 0, style: { position: 'fixed' } }),
    React.createElement(
      'div',
      { 
        ref, 
        role: 'dialog',
        'aria-modal': true,
        'data-state': 'open',
        'data-radix-dialog-content': true,
        ...props 
      },
      children
    ),
    React.createElement('span', { 'data-radix-focus-guard': true, tabIndex: 0, style: { position: 'fixed' } })
  );
});
Content.displayName = 'DialogContent';

export const Title = React.forwardRef(({ children, ...props }: any, ref: any) => 
  React.createElement('h2', { ref, ...props }, children)
);
Title.displayName = 'DialogTitle';

export const Description = React.forwardRef(({ children, ...props }: any, ref: any) => 
  React.createElement('p', { ref, ...props }, children)
);
Description.displayName = 'DialogDescription';

export const Close = React.forwardRef(({ children, onClick, ...props }: any, ref: any) => {
  const context = React.useContext(DialogContext);
  
  const handleClick = (e: any) => {
    onClick?.(e);
    context?.onOpenChange?.(false);
  };

  return React.createElement('button', { ref, onClick: handleClick, ...props }, children);
});
Close.displayName = 'DialogClose';

