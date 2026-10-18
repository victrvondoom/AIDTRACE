"use client";

import { GraphLabWorkspace } from "@/features/graph-lab/graph-lab-workspace";

// Compatibility route: the workspace itself lives in the Intelligence Hub feature host.
export default function GraphLabPage() {
  return <GraphLabWorkspace />;
}
