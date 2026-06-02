import { render, screen } from "@testing-library/react";
import { FullPageLoader } from "../components/ui/FullPageLoader";
import "@testing-library/jest-dom";

describe("FullPageLoader", () => {
  it("renders a centered overlay when loading", () => {
    render(<FullPageLoader isLoading={true} message="Please wait" />);

    const overlay = screen.getByRole("status");
    expect(overlay).toBeInTheDocument();
    expect(overlay).toHaveClass("fixed inset-0");
    expect(screen.getAllByText("Please wait").length).toBeGreaterThanOrEqual(1);
  });

  it("does not render when not loading", () => {
    render(<FullPageLoader isLoading={false} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
