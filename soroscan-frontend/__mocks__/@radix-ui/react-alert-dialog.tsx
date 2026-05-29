import React from 'react';

export const Root = ({ children, open, onOpenChange, defaultOpen }: any) => {
  const [isOpen, setIsOpen] = React.useState(open ?? defaultOpen ?? false);
  
  React.useEffect(() => {
    if (open !== undefined) {
      setIsOpen(open);
    }
  }, [open]);

  const handleOpenChange = React.useCallback((newOpen: boolean) => {
    setIsOpen(newOpen);
    onOpenChange?.(newOpen);
  }, [onOpenChange]);

  const contextValue = React.useMemo(() => ({
    open: isOpen,
    onOpenChange: handleOpenChange,
  }), [isOpen, handleOpenChange]);

  return React.createElement(
    AlertDialogContext.Provider,
    { value: contextValue },
    children
  );
};

const AlertDialogContext = React.createContext<any>(null);

export const Trigger = React.forwardRef(({ children, onClick, ...props }: any, ref: any) => {
  const context = React.useContext(AlertDialogContext);
  
  const handleClick = (e: any) => {
    onClick?.(e);
    context?.onOpenChange?.(!context.open);
  };

  return React.createElement('button', { 
    ref, 
    onClick: handleClick,
    ...props 
  }, children);
});
Trigger.displayName = 'AlertDialogTrigger';

export const Portal = ({ children }: any) => {
  const context = React.useContext(AlertDialogContext);
  
  if (!context?.open) {
    return null;
  }
  
  return React.createElement('div', { 'data-radix-portal': true }, children);
};

export const Overlay = React.forwardRef(({ children, ...props }: any, ref: any) => {
  const context = React.useContext(AlertDialogContext);
  
  if (!context?.open) {
    return null;
  }
  
  return React.createElement('div', { 
    ref, 
    'data-radix-overlay': true,
    'data-state': context?.open ? 'open' : 'closed',
    ...props 
  }, children);
});
Overlay.displayName = 'AlertDialogOverlay';

export const Content = React.forwardRef(({ children, ...props }: any, ref: any) => {
  const context = React.useContext(AlertDialogContext);
  
  if (!context?.open) {
    return null;
  }

  return React.createElement(
    'div',
    { 
      ref, 
      role: 'alertdialog',
      'aria-modal': true,
      'data-state': 'open',
      ...props 
    },
    children
  );
});
Content.displayName = 'AlertDialogContent';

export const Title = React.forwardRef(({ children, ...props }: any, ref: any) => 
  React.createElement('h2', { ref, ...props }, children)
);
Title.displayName = 'AlertDialogTitle';

export const Description = React.forwardRef(({ children, ...props }: any, ref: any) => 
  React.createElement('p', { ref, ...props }, children)
);
Description.displayName = 'AlertDialogDescription';

export const Action = React.forwardRef(({ children, onClick, ...props }: any, ref: any) => {
  const context = React.useContext(AlertDialogContext);
  
  const handleClick = (e: any) => {
    onClick?.(e);
    context?.onOpenChange?.(false);
  };

  return React.createElement('button', { ref, onClick: handleClick, ...props }, children);
});
Action.displayName = 'AlertDialogAction';

export const Cancel = React.forwardRef(({ children, onClick, ...props }: any, ref: any) => {
  const context = React.useContext(AlertDialogContext);
  
  const handleClick = (e: any) => {
    onClick?.(e);
    context?.onOpenChange?.(false);
  };

  return React.createElement('button', { ref, onClick: handleClick, ...props }, children);
});
Cancel.displayName = 'AlertDialogCancel';
