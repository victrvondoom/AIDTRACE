"use client";

// Hosts an existing page module inside the workspace without changing the address bar. The page believes it is at its original route: this host supplies
// its pathname, route params and search params, and replaces the router with one that navigates the workspace. Links are intercepted for the same reason.
// Async server pages (assets, documents, briefs, off-boarding) are ordinary async functions over client-callable APIs, so they are awaited here.
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { PathParamsContext, PathnameContext, ReadonlyURLSearchParams, SearchParamsContext } from "next/dist/shared/lib/hooks-client-context.shared-runtime";
import { Component, Suspense, use, useEffect, useMemo, useState, type ComponentType, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@/components/ui";
import { resolveRoute, type LegacyRoute } from "./legacy-routes";

type PageProps = Record<string, unknown>;
// One import promise per page, shared by every mount, so React's `use()` suspends once and a re-open is instant.
const modules = new Map<string, ReturnType<LegacyRoute["load"]>>();
function loadModule(route: LegacyRoute) {
  let promise = modules.get(route.pattern);
  if (!promise) { promise = route.load(); modules.set(route.pattern, promise); }
  return promise;
}

/** A client page: suspends until its module has loaded, then renders its default export with the route's props. */
function ClientPage({ route, params, query }: { route: LegacyRoute; params: Record<string, string>; query: Record<string, string> }) {
  const Page = use(loadModule(route)).default as ComponentType<PageProps>;
  return <Page params={Promise.resolve(params)} searchParams={Promise.resolve(query)} />;
}

const isNotFound = (e: unknown) => {
  const x = e as { digest?: string; message?: string } | null;
  return Boolean(x && ((typeof x.digest === "string" && x.digest.includes("404")) || x.message === "NEXT_NOT_FOUND"));
};

class PageBoundary extends Component<{ children: ReactNode; label: string }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, info: ErrorInfo) { if (!isNotFound(error)) console.error("extension page crashed", this.props.label, error, info.componentStack); }
  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (isNotFound(error)) return <p role="status" className="p-6 text-caption text-muted">That record was not found.</p>;
    return (
      <div role="alert" className="m-4 border-l-2 border-danger bg-surface p-4 text-caption">
        <p className="font-semibold text-danger">{this.props.label} could not be shown.</p>
        <p className="mt-1 text-muted">{error.message}</p>
        <Button className="mt-3" onClick={() => this.setState({ error: null })}>Try again</Button>
      </div>
    );
  }
}

/** Awaits an async server page in the browser and renders what it returns. */
function ServerPage({ route, params, query, pathKey }: { route: LegacyRoute; params: Record<string, string>; query: Record<string, string>; pathKey: string }) {
  const [state, setState] = useState<{ key: string; element?: ReactNode; error?: Error }>({ key: "" });
  useEffect(() => {
    let live = true;
    (async () => {
      const mod = await route.load();
      const element = await (mod.default as unknown as (p: PageProps) => Promise<ReactNode>)({ params: Promise.resolve(params), searchParams: Promise.resolve(query) });
      if (live) setState({ key: pathKey, element });
    })().catch((error: unknown) => { if (live) setState({ key: pathKey, error: error instanceof Error ? error : new Error("The page failed to load.") }); });
    return () => { live = false; };
  }, [route, params, query, pathKey]);
  if (state.key === pathKey && state.error) throw state.error;
  if (state.key !== pathKey) return <p role="status" className="p-6 text-caption text-muted">Loading…</p>;
  return <>{state.element}</>;
}

export interface RouteHostProps {
  /** The legacy path to show, e.g. "/assets/EQ-101?tab=documents". */
  path: string;
  /** Called for every link click or router push/replace; the owner decides which extension shows it. */
  onNavigate: (href: string, replace?: boolean) => void;
  onBack: () => void;
}

export function LegacyRouteHost({ path, onNavigate, onBack }: RouteHostProps) {
  const resolved = useMemo(() => resolveRoute(path), [path]);
  const [nonce, setNonce] = useState(0);
  const router = useMemo(() => ({
    push: (href: string) => onNavigate(href), replace: (href: string) => onNavigate(href, true), back: onBack, forward: () => {}, refresh: () => setNonce((n) => n + 1), prefetch: () => {},
  }), [onNavigate, onBack]);
  const pathname = resolved ? resolved.path.split("?")[0] : path.split("?")[0];
  const searchParams = useMemo(() => new ReadonlyURLSearchParams(new URLSearchParams(resolved?.query ?? {})), [resolved]);

  function interceptLinks(e: React.MouseEvent) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = (e.target as HTMLElement).closest("a");
    if (!a) return;
    const href = a.getAttribute("href");
    if (!href || href.startsWith("#") || href.startsWith("//") || /^[a-z][a-z0-9+.-]*:/i.test(href) || a.target === "_blank" || a.hasAttribute("download")) return;
    if (href.startsWith("/")) { e.preventDefault(); e.stopPropagation(); onNavigate(href); }
  }

  if (!resolved) return <p role="status" className="p-6 text-caption text-muted">“{pathname}” is not part of the workspace.</p>;
  const { route, params, query } = resolved;
  return (
    <AppRouterContext.Provider value={router as unknown as React.ContextType<typeof AppRouterContext>}>
      <PathnameContext.Provider value={pathname}>
        <PathParamsContext.Provider value={params}>
          <SearchParamsContext.Provider value={searchParams}>
            <div className="aidtrace-ext" onClickCapture={interceptLinks} data-testid="aidtrace-route-host" data-route={route.pattern}>
              <PageBoundary key={`${resolved.path}#${nonce}`} label={route.pattern}>
                {!route.serverPage ? (
                  <Suspense fallback={<p role="status" className="p-6 text-caption text-muted">Loading…</p>}>
                    <ClientPage route={route} params={params} query={query} />
                  </Suspense>
                ) : <ServerPage route={route} params={params} query={query} pathKey={`${resolved.path}#${nonce}`} />}
              </PageBoundary>
            </div>
          </SearchParamsContext.Provider>
        </PathParamsContext.Provider>
      </PathnameContext.Provider>
    </AppRouterContext.Provider>
  );
}
