"use client";

import dynamic from "next/dynamic";
import { PageHeader } from "@/components/ui";

const SourceLibrary = dynamic(
  () => import("@/features/sources/source-library").then((m) => m.SourceLibrary),
  {
    loading: () => (
      <p role="status" className="p-6 text-caption text-muted">
        Loading capabilities registry…
      </p>
    ),
    ssr: false,
  }
);

export default function CapabilitiesPage() {
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Capability Workbench · 98 Repository Registry"
        lede="Audited Track 01 research leads, extracted README capabilities, licensing analysis, and native integrations inside AIDTRACE."
      />
      <div className="mt-6">
        <SourceLibrary />
      </div>
    </div>
  );
}
