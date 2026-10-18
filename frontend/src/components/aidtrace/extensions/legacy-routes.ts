// Every legacy page that has been migrated into the workspace, as data. The route host renders these modules unchanged inside /hub: it supplies the path,
// params and search params the page expects and turns every link or router call into an in-workspace navigation, so the address bar never changes.
import type { ComponentType } from "react";

export type PageModule = { default: ComponentType<Record<string, unknown>> | ((props: Record<string, unknown>) => unknown) };

export interface LegacyRoute {
  /** The original Next.js route, with :param segments. */
  pattern: string;
  /** The extension that owns this page (see registry.tsx). */
  extension: string;
  load: () => Promise<PageModule>;
  /** Async server components: they fetch before rendering, so the host awaits them in the browser instead of mounting them. */
  serverPage?: boolean;
}

const page = (p: Promise<unknown>) => p as Promise<PageModule>;

// Specific patterns precede parameterised ones so "/assets/register" is never read as an asset id.
export const LEGACY_ROUTES: LegacyRoute[] = [
  // Supply Chain Intelligence
  { pattern: "/assets", extension: "supplier-registry", serverPage: true, load: () => page(import("@/app/(app)/assets/page")) },
  { pattern: "/assets/register", extension: "supplier-registry", load: () => page(import("@/app/(app)/assets/register/page")) },
  { pattern: "/assets/bootstrap", extension: "supplier-registry", load: () => page(import("@/app/(app)/assets/bootstrap/page")) },
  { pattern: "/assets/:id", extension: "supplier-registry", serverPage: true, load: () => page(import("@/app/(app)/assets/[id]/page")) },
  // Investigation & Intelligence
  { pattern: "/copilot", extension: "assistant", load: () => page(import("@/app/(app)/copilot/page")) },
  { pattern: "/rca", extension: "rca", load: () => page(import("@/app/(app)/rca/page")) },
  { pattern: "/graph", extension: "connected-graph", load: () => page(import("@/app/(app)/graph/page")) },
  { pattern: "/events", extension: "events", load: () => page(import("@/app/(app)/events/page")) },
  { pattern: "/events/:id", extension: "events", load: () => page(import("@/app/(app)/events/[id]/page")) },
  { pattern: "/overview/cross-site", extension: "events", load: () => page(import("@/app/(app)/overview/cross-site/page")) },
  // Evidence & Knowledge
  { pattern: "/documents", extension: "evidence-vault", serverPage: true, load: () => page(import("@/app/(app)/documents/page")) },
  { pattern: "/documents/ingest", extension: "evidence-vault", load: () => page(import("@/app/(app)/documents/ingest/page")) },
  { pattern: "/documents/compare", extension: "evidence-vault", load: () => page(import("@/app/(app)/documents/compare/page")) },
  { pattern: "/documents/:id/topology", extension: "evidence-vault", load: () => page(import("@/app/(app)/documents/[id]/topology/page")) },
  { pattern: "/documents/:id", extension: "evidence-vault", serverPage: true, load: () => page(import("@/app/(app)/documents/[id]/page")) },
  { pattern: "/overview/coverage", extension: "coverage", load: () => page(import("@/app/(app)/overview/coverage/page")) },
  { pattern: "/offboarding", extension: "knowledge-transfer", serverPage: true, load: () => page(import("@/app/(app)/(desktop)/offboarding/page")) },
  { pattern: "/offboarding/:sessionId", extension: "knowledge-transfer", load: () => page(import("@/app/(app)/(desktop)/offboarding/[sessionId]/page")) },
  { pattern: "/projects", extension: "projects", load: () => page(import("@/app/(app)/projects/page")) },
  { pattern: "/field/voice", extension: "field-capture", load: () => page(import("@/app/(app)/field/voice/page")) },
  { pattern: "/field/voice/:workOrderId", extension: "field-capture", load: () => page(import("@/app/(app)/field/voice/[workOrderId]/page")) },
  { pattern: "/field/deviation", extension: "field-capture", load: () => page(import("@/app/(app)/field/deviation/page")) },
  { pattern: "/field/elicitation/:workOrderId", extension: "field-capture", load: () => page(import("@/app/(app)/field/elicitation/[workOrderId]/page")) },
  // Decision Governance
  { pattern: "/governance", extension: "governance", load: () => page(import("@/app/(app)/governance/page")) },
  { pattern: "/governance/conflicts", extension: "governance", load: () => page(import("@/app/(app)/governance/conflicts/page")) },
  { pattern: "/governance/conflicts/:id", extension: "governance", load: () => page(import("@/app/(app)/governance/conflicts/[id]/page")) },
  { pattern: "/governance/quarantine", extension: "governance", load: () => page(import("@/app/(app)/governance/quarantine/page")) },
  { pattern: "/governance/moc", extension: "governance", load: () => page(import("@/app/(app)/governance/moc/page")) },
  { pattern: "/governance/moc/:id", extension: "governance", load: () => page(import("@/app/(app)/governance/moc/[id]/page")) },
  { pattern: "/governance/sla", extension: "governance", load: () => page(import("@/app/(app)/governance/sla/page")) },
  { pattern: "/governance/circuit-breaker", extension: "governance", load: () => page(import("@/app/(app)/governance/circuit-breaker/page")) },
  { pattern: "/governance/model-gate", extension: "governance", load: () => page(import("@/app/(app)/governance/model-gate/page")) },
  { pattern: "/governance/push-volume-gate", extension: "governance", load: () => page(import("@/app/(app)/governance/push-volume-gate/page")) },
  { pattern: "/governance/timestamp-drift", extension: "governance", load: () => page(import("@/app/(app)/governance/timestamp-drift/page")) },
  { pattern: "/audit", extension: "audit", load: () => page(import("@/app/(app)/audit/page")) },
  { pattern: "/compliance", extension: "compliance", load: () => page(import("@/app/(app)/compliance/page")) },
  { pattern: "/compliance/audit-pack", extension: "compliance", load: () => page(import("@/app/(app)/compliance/audit-pack/page")) },
  { pattern: "/compliance/nonconformance", extension: "compliance", load: () => page(import("@/app/(app)/compliance/nonconformance/page")) },
  { pattern: "/briefs", extension: "notices", serverPage: true, load: () => page(import("@/app/(app)/briefs/page")) },
  { pattern: "/briefs/:id", extension: "notices", serverPage: true, load: () => page(import("@/app/(app)/briefs/[id]/page")) },
  // Specialist engines and platform
  { pattern: "/system-health", extension: "system-health", load: () => page(import("@/app/(app)/system-health/page")) },
];

export interface ResolvedRoute { route: LegacyRoute; params: Record<string, string>; query: Record<string, string>; path: string }

/** Match "/assets/ABC-1?tab=x" against the table. Returns null for anything that is not a migrated page, so callers can say so instead of navigating. */
export function resolveRoute(href: string): ResolvedRoute | null {
  const [rawPath, rawQuery = ""] = href.split("#")[0].split("?");
  const path = rawPath.length > 1 ? rawPath.replace(/\/+$/, "") : rawPath;
  const segs = path.split("/").filter(Boolean);
  for (const route of LEGACY_ROUTES) {
    const pat = route.pattern.split("/").filter(Boolean);
    if (pat.length !== segs.length) continue;
    const params: Record<string, string> = {};
    const ok = pat.every((p, i) => (p.startsWith(":") ? ((params[p.slice(1)] = decodeURIComponent(segs[i])), true) : p === segs[i]));
    if (ok) {
      const query: Record<string, string> = {};
      new URLSearchParams(rawQuery).forEach((v, k) => { query[k] = v; });
      return { route, params, query, path: rawQuery ? `${path}?${rawQuery}` : path };
    }
  }
  return null;
}

/** The extension that owns a path, or null. */
export const extensionForPath = (href: string) => resolveRoute(href)?.route.extension ?? null;
