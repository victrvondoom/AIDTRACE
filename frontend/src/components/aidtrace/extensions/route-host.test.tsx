import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Three real legacy routes with their page modules replaced by small stand-ins: a client page that reads every navigation hook, an async server page, and a
// server page whose record does not exist.
vi.mock("@/app/(app)/events/[id]/page", async () => {
  const nav = await import("next/navigation");
  const { default: Link } = await import("next/link");
  return { default: function EventPage() {
    const pathname = nav.usePathname(); const params = nav.useParams(); const search = nav.useSearchParams(); const router = nav.useRouter();
    return (<div><span data-testid="pathname">{pathname}</span><span data-testid="id">{String(params.id)}</span><span data-testid="tab">{search.get("tab")}</span>
      <Link href="/documents/D-1">open document</Link><a href="https://example.com/out">external</a><a href="#section">same page</a>
      <button onClick={() => router.push("/rca")}>push</button><button onClick={() => router.back()}>back</button></div>);
  } };
});
vi.mock("@/app/(app)/briefs/[id]/page", () => ({ default: async function BriefPage({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <p>brief {id} loaded</p>; } }));
vi.mock("@/app/(app)/assets/[id]/page", () => ({ default: async function AssetPage(): Promise<never> { throw Object.assign(new Error("NEXT_NOT_FOUND"), { digest: "NEXT_HTTP_ERROR_FALLBACK;404" }); } }));

import { LegacyRouteHost } from "./route-host";

// A page that suspends on first mount needs the render itself awaited inside act().
const mount = (ui: React.ReactElement) => act(async () => { render(ui); });

describe("LegacyRouteHost", () => {
  afterEach(cleanup);

  it("gives a client page its original pathname, params and search params", async () => {
    await mount(<LegacyRouteHost path="/events/EV-42?tab=sources" onNavigate={() => {}} onBack={() => {}} />);
    expect(await screen.findByTestId("pathname")).toHaveTextContent("/events/EV-42");
    expect(screen.getByTestId("id")).toHaveTextContent("EV-42");
    expect(screen.getByTestId("tab")).toHaveTextContent("sources");
  });

  it("turns link clicks and router calls into workspace navigation, never a page load", async () => {
    const onNavigate = vi.fn(); const onBack = vi.fn();
    await mount(<LegacyRouteHost path="/events/EV-42" onNavigate={onNavigate} onBack={onBack} />);
    fireEvent.click(await screen.findByText("open document"));
    expect(onNavigate).toHaveBeenCalledWith("/documents/D-1");
    fireEvent.click(screen.getByText("push"));
    expect(onNavigate).toHaveBeenCalledWith("/rca");
    fireEvent.click(screen.getByText("back"));
    expect(onBack).toHaveBeenCalled();
    expect(window.location.pathname).toBe("/");
  });

  it("leaves external and in-page anchor links alone", async () => {
    const onNavigate = vi.fn();
    await mount(<LegacyRouteHost path="/events/EV-42" onNavigate={onNavigate} onBack={() => {}} />);
    const external = await screen.findByText("external");
    expect(fireEvent.click(external)).toBe(true); // not default-prevented
    fireEvent.click(screen.getByText("same page"));
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it("awaits an async server page and renders what it returns", async () => {
    render(<LegacyRouteHost path="/briefs/B-7" onNavigate={() => {}} onBack={() => {}} />);
    expect(await screen.findByText("brief B-7 loaded")).toBeInTheDocument();
  });

  it("shows a calm not-found state, not a crash, for a missing record", async () => {
    render(<LegacyRouteHost path="/assets/NOPE" onNavigate={() => {}} onBack={() => {}} />);
    expect(await screen.findByText("That record was not found.")).toBeInTheDocument();
  });

  it("says so for a path that is not a migrated page", () => {
    render(<LegacyRouteHost path="/definitely/not/here" onNavigate={() => {}} onBack={() => {}} />);
    expect(screen.getByText(/is not part of the workspace/)).toBeInTheDocument();
  });

  it("re-renders with the new route when the path changes", async () => {
    const { rerender } = render(<LegacyRouteHost path="/briefs/B-1" onNavigate={() => {}} onBack={() => {}} />);
    await screen.findByText("brief B-1 loaded");
    rerender(<LegacyRouteHost path="/briefs/B-2" onNavigate={() => {}} onBack={() => {}} />);
    await waitFor(() => expect(screen.getByText("brief B-2 loaded")).toBeInTheDocument());
  });
});
