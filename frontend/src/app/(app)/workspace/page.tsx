import { Suspense } from "react";
import { CapabilityDirectory } from "@/components/capability-directory";
import { ButtonLink, PageHeader } from "@/components/ui";

export default function WorkspacePage() {
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader title="All AIDTRACE Features" lede="Every AIDTRACE workspace, specialist tool and intelligence integration in one place." actions={<ButtonLink href="/overview">Back to Overview</ButtonLink>} />
      <Suspense fallback={<p className="mt-8 text-body text-muted">Loading feature directory…</p>}><CapabilityDirectory /></Suspense>
    </div>
  );
}
