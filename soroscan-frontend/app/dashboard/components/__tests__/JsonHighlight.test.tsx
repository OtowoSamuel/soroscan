import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { JsonHighlight } from "../JsonHighlight";

describe("JsonHighlight", () => {
  const sampleData = {
    name: "test",
    count: 42,
    active: true,
    value: null,
  };

  beforeEach(() => {
    // Mock clipboard API
    Object.assign(navigator, {
      clipboard: {
        writeText: jest.fn(() => Promise.resolve()),
      },
    });
  });

  it("renders JSON data with syntax highlighting", () => {
    render(<JsonHighlight data={sampleData} />);
    
    // Check that JSON content is rendered
    expect(screen.getByText(/"name"/)).toBeInTheDocument();
    expect(screen.getByText(/"test"/)).toBeInTheDocument();
    expect(screen.getByText(/42/)).toBeInTheDocument();
    expect(screen.getByText(/true/)).toBeInTheDocument();
    expect(screen.getByText(/null/)).toBeInTheDocument();
  });

  it("applies dark theme by default", () => {
    const { container } = render(<JsonHighlight data={sampleData} />);
    const pre = container.querySelector("pre");
    
    expect(pre).toHaveStyle({
      background: "rgba(0, 0, 0, 0.3)",
    });
  });

  it("applies light theme when specified", () => {
    const { container } = render(<JsonHighlight data={sampleData} theme="light" />);
    const pre = container.querySelector("pre");
    
    expect(pre).toHaveStyle({
      background: "rgba(255, 255, 255, 0.95)",
    });
  });

  it("copies JSON to clipboard when copy button is clicked", async () => {
    render(<JsonHighlight data={sampleData} />);
    
    const copyButton = screen.getByRole("button", { name: /copy/i });
    fireEvent.click(copyButton);
    
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        JSON.stringify(sampleData, null, 2)
      );
    });
    
    // Check that button text changes to "Copied!"
    expect(screen.getByText(/✓ Copied!/)).toBeInTheDocument();
  });

  it("resets copy button text after 2 seconds", async () => {
    jest.useFakeTimers();
    render(<JsonHighlight data={sampleData} />);
    
    const copyButton = screen.getByRole("button", { name: /copy/i });
    fireEvent.click(copyButton);
    
    await waitFor(() => {
      expect(screen.getByText(/✓ Copied!/)).toBeInTheDocument();
    });
    
    // Fast-forward 2 seconds
    jest.advanceTimersByTime(2000);
    
    await waitFor(() => {
      expect(screen.getByText(/📋 Copy/)).toBeInTheDocument();
    });
    
    jest.useRealTimers();
  });

  it("respects custom maxHeight prop", () => {
    const { container } = render(
      <JsonHighlight data={sampleData} maxHeight="500px" />
    );
    const pre = container.querySelector("pre");
    
    expect(pre).toHaveStyle({
      maxHeight: "500px",
    });
  });

  it("handles complex nested objects", () => {
    const complexData = {
      user: {
        name: "Alice",
        age: 30,
        tags: ["admin", "developer"],
      },
      metadata: {
        created: "2024-01-01",
        updated: null,
      },
    };
    
    render(<JsonHighlight data={complexData} />);
    
    // Check that nested structure is rendered
    expect(screen.getByText(/"user"/)).toBeInTheDocument();
    expect(screen.getByText(/"Alice"/)).toBeInTheDocument();
    expect(screen.getByText(/"admin"/)).toBeInTheDocument();
  });

  it("handles clipboard copy errors gracefully", async () => {
    const consoleError = jest.spyOn(console, "error").mockImplementation();
    Object.assign(navigator, {
      clipboard: {
        writeText: jest.fn(() => Promise.reject(new Error("Clipboard error"))),
      },
    });
    
    render(<JsonHighlight data={sampleData} />);
    
    const copyButton = screen.getByRole("button", { name: /copy/i });
    fireEvent.click(copyButton);
    
    await waitFor(() => {
      expect(consoleError).toHaveBeenCalledWith(
        "Failed to copy:",
        expect.any(Error)
      );
    });
    
    consoleError.mockRestore();
  });
});
