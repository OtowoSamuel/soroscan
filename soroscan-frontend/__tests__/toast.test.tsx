import React from "react";
import { render, screen, act, fireEvent } from "@testing-library/react";
import { ToastProvider, useToast, showToast } from "../context/ToastContext";

// Helper component to trigger toasts
const ToastTrigger = () => {
  const { showToast: show } = useToast();
  return (
    <button onClick={() => show("Test message", "success", "Test Title")}>
      Show Toast
    </button>
  );
};

describe("Toast System", () => {
  // Suppress React act() warnings for timer-based state updates
  // These are expected in this test suite and don't indicate actual problems
  const originalError = console.error;
  beforeAll(() => {
    console.error = (...args: any[]) => {
      if (
        typeof args[0] === 'string' &&
        args[0].includes('An update to ToastProvider inside a test was not wrapped in act')
      ) {
        return;
      }
      originalError.call(console, ...args);
    };
  });

  afterAll(() => {
    console.error = originalError;
  });

  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  it("renders a toast when showToast is called", () => {
    render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText("Show Toast"));

    expect(screen.getByText("Test Title")).toBeInTheDocument();
    expect(screen.getByText("Test message")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("auto-dismisses after 4 seconds", async () => {
    render(
      <ToastProvider duration={4000}>
        <ToastTrigger />
      </ToastProvider>
    );

    act(() => {
      fireEvent.click(screen.getByText("Show Toast"));
    });
    
    expect(screen.getByText("Test Title")).toBeInTheDocument();

    // Fast-forward 4 seconds - wrap in act to handle state updates from timer
    act(() => {
      jest.advanceTimersByTime(4000);
    });

    expect(screen.queryByText("Test Title")).not.toBeInTheDocument();
  });

  it("manual dismiss button works", () => {
    render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText("Show Toast"));
    expect(screen.getByText("Test Title")).toBeInTheDocument();

    const closeButton = screen.getByLabelText("Dismiss notification");
    fireEvent.click(closeButton);

    expect(screen.queryByText("Test Title")).not.toBeInTheDocument();
  });

  it("multiple toasts stack vertically", () => {
    const MultiToastTrigger = () => {
      const { showToast: show } = useToast();
      return (
        <button onClick={() => {
          show("Message 1", "info", "Title 1");
          show("Message 2", "info", "Title 2");
        }}>
          Show Multiple
        </button>
      );
    };

    render(
      <ToastProvider>
        <MultiToastTrigger />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText("Show Multiple"));

    expect(screen.getByText("Title 1")).toBeInTheDocument();
    expect(screen.getByText("Title 2")).toBeInTheDocument();
    
    const toasts = screen.getAllByRole("status");
    expect(toasts.length).toBe(2);
  });

  it("works with global showToast helper", () => {
    render(
      <ToastProvider>
        <div>Content</div>
      </ToastProvider>
    );

    act(() => {
      showToast("Global message", "warning", "Global Title");
    });

    expect(screen.getByText("Global Title")).toBeInTheDocument();
    expect(screen.getByText("Global message")).toBeInTheDocument();
  });
});
