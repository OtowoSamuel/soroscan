import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import {
  Modal,
  ModalContent,
  ModalTrigger,
  ModalTitle,
} from "../components/ui/modal";
import "@testing-library/jest-dom";

describe("Modal Component", () => {
  const TestModal = () => (
    <Modal>
      <ModalTrigger data-testid="trigger">Open Modal</ModalTrigger>
      <ModalContent>
        <ModalTitle>Test Title</ModalTitle>
        <button data-testid="inside-btn">Inside Button</button>
      </ModalContent>
    </Modal>
  );

  it("should display the modal when trigger is clicked", async () => {
    render(<TestModal />);
    const trigger = screen.getByTestId("trigger");
    
    await act(async () => {
      fireEvent.click(trigger);
    });

    expect(screen.getByText("Test Title")).toBeInTheDocument();
  });

  it("should close when the escape key is pressed", async () => {
    render(<TestModal />);
    
    await act(async () => {
      fireEvent.click(screen.getByTestId("trigger"));
    });

    expect(screen.getByText("Test Title")).toBeInTheDocument();

    await act(async () => {
      fireEvent.keyDown(document.activeElement || document.body, {
        key: "Escape",
        code: "Escape",
        keyCode: 27,
        charCode: 27,
      });
    });

    await waitFor(
      () => {
        expect(screen.queryByText("Test Title")).not.toBeInTheDocument();
      },
      { timeout: 2000 },
    );
  });

  it("should NOT close when the overlay is clicked (as per requirements)", async () => {
    render(<TestModal />);
    
    await act(async () => {
      fireEvent.click(screen.getByTestId("trigger"));
    });

    const overlay = document.querySelector('[data-state="open"]');
    
    await act(async () => {
      if (overlay) fireEvent.pointerDown(overlay);
    });

    expect(screen.getByText("Test Title")).toBeInTheDocument();
  });

  it("should trap focus inside the modal", async () => {
    render(<TestModal />);
    
    await act(async () => {
      fireEvent.click(screen.getByTestId("trigger"));
    });

    const modalContent = screen.getByRole("dialog");
    const insideBtn = screen.getByTestId("inside-btn");

    await waitFor(() => {
      expect(modalContent).toBeInTheDocument();
    });

    await act(async () => {
      insideBtn?.focus();
    });
    
    expect(document.activeElement).toBe(insideBtn);

    const guards = document.querySelectorAll("[data-radix-focus-guard]");
    expect(guards.length).toBeGreaterThan(0);
  });
});
