"use client";

import dynamic from "next/dynamic";

// The workspace reads sessionStorage for the last view and extension, so it renders on the client only.
const AidtraceWorkspace = dynamic(() => import("@/components/aidtrace/workspace").then((m) => m.AidtraceWorkspace), {
  ssr: false,
  loading: () => <p role="status" className="p-6 text-caption text-muted">Opening the AIDTRACE workspace…</p>,
});

export default function HubPage() {
  return <AidtraceWorkspace />;
}
