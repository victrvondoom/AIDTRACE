"use client";

import { SourceLibrary } from "@/features/sources/source-library";

// Compatibility route: the library itself lives in the Intelligence Hub feature host.
export default function SourcesPage() {
  return <SourceLibrary />;
}
