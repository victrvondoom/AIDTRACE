import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// next/font/google is compiled away by the Next toolchain; under plain vitest
// it has no loader, so stand in with the shape the page consumes.
vi.mock("./landing-fonts", () => ({
  instrumentSans: { variable: "--font-instrument" },
  dmSans: { variable: "--font-dm" },
}));

import Home from "./page";

describe("Home", () => {
  afterEach(cleanup);

  it("shows the public AIDTRACE landing page instead of redirecting visitors", () => {
    render(<Home />);

    expect(screen.getByRole("heading", { level: 1, name: /connected intelligence/i })).toBeInTheDocument();

    // One way in: the header CTA.
    const workspaceLinks = screen.getAllByRole("link", { name: /open workspace/i });
    expect(workspaceLinks).toHaveLength(1);
    for (const link of workspaceLinks) expect(link).toHaveAttribute("href", "/login");
    expect(screen.queryByRole("link", { name: /sign in/i })).not.toBeInTheDocument();

    // The Watch Demo link has been removed from the landing page.
    expect(screen.queryByRole("link", { name: /watch.*demo/i })).not.toBeInTheDocument();

    // …and the path into the page itself is still there, unchanged.
    expect(screen.getByRole("link", { name: /explore how it works/i })).toHaveAttribute("href", "#how");
  });

  // Readers who did not already know the domain could not tell what AIDTRACE was.
  // The problem and the worked scenario are the fix, so they are load-bearing:
  // if either is dropped the page goes back to answering a question nobody asked.
  it("states the problem and walks one scenario before it makes a product claim", () => {
    render(<Home />);

    const problem = document.getElementById("problem") as HTMLElement;
    expect(problem).toBeInTheDocument();
    // The problem section explains fragmented information and changing evidence
    expect(problem).toHaveTextContent(/the information exists/i);
    expect(problem).toHaveTextContent(/fragmented information/i);
    expect(problem).toHaveTextContent(/changing evidence/i);

    const how = document.getElementById("how") as HTMLElement;
    expect(how).toBeInTheDocument();
    // Five numbered steps, ending on the review.
    expect(within(how).getAllByRole("listitem")).toHaveLength(5);
    expect(how).toHaveTextContent(/follow the falkordb relationships/i);
    expect(how).toHaveTextContent(/hold the action and retain the history/i);

    // Both must precede the first capability claim in document order.
    const capabilities = document.getElementById("capabilities") as HTMLElement;
    expect(problem.compareDocumentPosition(how)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(how.compareDocumentPosition(capabilities)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  // The capability tabs carry the product copy, and the cross-cutting rows under
  // them state the rest once. A separate coverage section restated all of it, so
  // it was removed — this guards the coverage itself rather than that section.
  it("covers each capability tab and the cross-cutting rows beneath them", () => {
    render(<Home />);

    for (const tab of ["Connected sources", "Evidence answers", "Connected risk", "Governed findings", "Proactive context"]) {
      expect(screen.getByRole("button", { name: tab })).toBeInTheDocument();
    }

    const panel = document.getElementById("capability-panel") as HTMLElement;

    fireEvent.click(screen.getByRole("button", { name: "Connected risk" }));
    expect(panel).toHaveTextContent(/trace a risk back to the record/i);

    // Scanned-document OCR is claimed here.
    fireEvent.click(screen.getByRole("button", { name: "Connected sources" }));
    expect(panel).toHaveTextContent(/start with the source record/i);
    expect(panel).toHaveTextContent(/OCR/);

    // The governance tab says what a finding rests on.
    fireEvent.click(screen.getByRole("button", { name: "Governed findings" }));
    expect(panel).toHaveTextContent(/see what supports a finding/i);
    expect(panel).toHaveTextContent(/current decision revision/i);

    // The cross-cutting work that has no screen of its own is stated once, in the
    // capability list under the tabs.
    const section = document.getElementById("capabilities") as HTMLElement;
    expect(section).toHaveTextContent(/impact analysis/i);
    expect(section).toHaveTextContent(/evidence drift/i);
    expect(section).toHaveTextContent(/persistent agent memory/i);

    // And it does not restate what a tab already says.
    expect(section).not.toHaveTextContent(/computer vision for p&ids/i);

    // And both sections that duplicated the tabs are gone. Nothing may link to
    // them either: a nav cell pointing at a removed anchor is a dead click.
    expect(document.getElementById("scope")).toBeNull();
    expect(document.getElementById("platform")).toBeNull();
    expect(document.querySelector('a[href="#platform"]')).toBeNull();
  });

  it("quotes the measured benchmark figures, including the answer-quality range", () => {
    render(<Home />);

    // benchmark/RESULTS.md is explicit that uncertainty must be quoted rather
    // than a single flattering number, and that grading is deterministic.
    // The chart shows a point estimate, so the interval must still be
    // disclosed in the caption rather than quietly dropped.
    expect(screen.getByText("87%")).toBeInTheDocument();
    expect(screen.getByText("40/46")).toBeInTheDocument();
    // Two: the retrieval and provenance chart bars. KG linkage is quoted
    // document-centric (90%), not as a third 100% — see status.md on why the
    // asset-centric cut isn't trustworthy to publish as-is.
    expect(screen.getAllByText("100%")).toHaveLength(2);
    expect(screen.getByText("18 / 20")).toBeInTheDocument();
    expect(screen.getByText("6 / 6")).toBeInTheDocument();
    // Scoped to the <p>: a bare regex also matches every ancestor's textContent.
    expect(screen.getByText(/figures below come from an industrial question-answering benchmark/i, { selector: "p" })).toBeInTheDocument();
    // Said once on the chart's own sub-label, and explained once in the filled cell
    // at the foot of the section. It used to be in the section intro as well, which
    // made that cell a repeat rather than the explanation.
    expect(screen.getAllByText(/graded by fixed rules/i, { selector: "p" })).toHaveLength(1);
    expect(screen.getByText(/fixed rules, never another model/i)).toBeInTheDocument();
    // The spread is carried by the chart itself, not rounded away in prose.
    expect(screen.getByText("40/46")).toBeInTheDocument();
    expect(screen.getByText(/95% confidence: 74 to 94/i)).toBeInTheDocument();
    // What the chart cannot show: which model answered, and why the misses understate it.
    expect(screen.getByText(/no fallback provider/i, { selector: "p" })).toBeInTheDocument();
    // The other harnesses are on the page too, with their real figures.
    expect(screen.getByText("13 / 13")).toBeInTheDocument();
    expect(screen.getByText("0 unsafe")).toBeInTheDocument();
    expect(screen.getByText("F1 0.912")).toBeInTheDocument();
    expect(screen.getByText("F1 0.805")).toBeInTheDocument();
    expect(screen.getByText("−19.9%")).toBeInTheDocument();
    expect(screen.getByText("0% errors")).toBeInTheDocument();
    expect(screen.getByText("No leak signal")).toBeInTheDocument();

    // No invented operational metrics.
    expect(screen.queryByText("98.4%")).not.toBeInTheDocument();
    expect(screen.queryByText("99.9%")).not.toBeInTheDocument();
  });

  it("names the six Evidence Drift checkpoints in the dependency path", () => {
    render(<Home />);

    // Scoped to <code>: the same words can appear in the surrounding prose.
    for (const property of ["source_version", "changed_claim", "dependent_memory", "decision_revision", "prior_approval", "action_state"]) {
      expect(screen.getByText(property, { selector: "code" })).toBeInTheDocument();
    }
  });

  it("swaps the capability panel when another capability is selected", () => {
    render(<Home />);

    const panel = document.getElementById("capability-panel") as HTMLElement;
    expect(within(panel).getByRole("heading", { name: /context arrives before a decision/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "New observations" }));

    expect(within(panel).getByRole("heading", { name: /capture what people observe/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New observations" })).toHaveAttribute("aria-pressed", "true");
  });

  it("swaps the audience panel when another audience is selected", () => {
    render(<Home />);

    const panel = document.getElementById("audience-panel") as HTMLElement;
    expect(panel).toHaveTextContent(/supply chain intelligence/i);

    fireEvent.click(screen.getByRole("button", { name: "CyberFlow" }));

    expect(panel).toHaveTextContent(/cybersecurity intelligence/i);
  });

  // The Graph Hacks banner names the event and track this build was made for. Its
  // link must land on a real section, and its label must not be the header's
  // "Open workspace", which the first test counts as the only one.
  it("names the Graph Hacks track in a banner that links to the Track 01 extension", () => {
    render(<Home />);

    const banner = screen.getByRole("region", { name: /built for graph hacks/i });
    expect(banner).toHaveTextContent(/graph hacks · track 01/i);
    expect(banner).toHaveTextContent(/agents that act on connected data/i);
    expect(within(banner).getByRole("link", { name: /see the track 01 extension/i })).toHaveAttribute("href", "#field");
    expect(document.getElementById("field")).toBeInTheDocument();
  });

  it("renders the FAQ as native disclosure elements so it works without JS", () => {
    const { container } = render(<Home />);

    // One category's questions at a time; the first answer starts open.
    const disclosures = container.querySelectorAll("details");
    expect(disclosures).toHaveLength(3);
    expect(disclosures[0].querySelector("summary")).toHaveTextContent(/what does aidtrace do/i);
    expect(disclosures[0]).toHaveAttribute("open");
  });

  it("switches the FAQ answers when another category is chosen", () => {
    render(<Home />);

    const answers = document.getElementById("faq-answers") as HTMLElement;
    expect(answers).toHaveTextContent(/what does aidtrace do/i);

    const faqSection = document.getElementById("faq") as HTMLElement;
    fireEvent.click(within(faqSection).getByRole("button", { name: "Evidence" }));

    expect(answers).toHaveTextContent(/can i trace a conclusion/i);
    expect(answers).not.toHaveTextContent(/what does aidtrace do/i);
  });

  it("keeps every footer link pointed at a real destination", () => {
    const { container } = render(<Home />);

    const hrefs = [...container.querySelectorAll("footer a")].map((a) => a.getAttribute("href"));
    expect(hrefs.length).toBeGreaterThan(0);
    const allowedExternal = [
      "https://github.com/kr7shnasomani/kairos",
      "https://drive.google.com/file/d/18ZO95MckNtESg-Z2ruRBNnKq6JyB57rP/view?usp=drive_link",
    ];
    for (const href of hrefs) {
      const ok = href === "/login" || href === "/docs" || href === "/" || href === "/hub" || href?.startsWith("#") || allowedExternal.includes(href ?? "");
      expect(ok, `unexpected footer href: ${href}`).toBe(true);
    }
    // Every external link opens safely.
    for (const a of container.querySelectorAll('footer a[target="_blank"]')) {
      expect(a.getAttribute("rel")).toMatch(/noreferrer/);
    }
  });
});
