"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { Button, PageHeader } from "@/components/ui";

const Loading = () => (
  <p role="status" className="p-6 text-caption text-muted">
    Loading Track 1 Agent workspace…
  </p>
);

const FraudWorkspace = dynamic(
  () => import("@/components/features/fraud/FraudWorkspace").then((m) => m.FraudWorkspace),
  { loading: Loading, ssr: false }
);

const ConsumerWorkspace = dynamic(
  () => import("@/features/resolveai/consumer-workspace").then((m) => m.ConsumerWorkspace),
  { loading: Loading, ssr: false }
);

export default function Track1Page() {
  const [tab, setTab] = useState<"fraud" | "consumer">("fraud");

  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Track 1 Agent · Connected Data Investigation"
        lede="FalkorDB-native investigation agent: follows multi-hop device and transaction chains, enforces deterministic policy rules, proposes actions, and gates all state mutations through human approval with cryptographic audit receipts."
      />

      <nav aria-label="Track 1 modules" className="mt-6 flex flex-wrap gap-2 border-b border-line pb-3">
        <Button
          variant={tab === "fraud" ? "primary" : "ghost"}
          onClick={() => setTab("fraud")}
          className="min-h-11"
        >
          Fraud Ring Investigation (Baseline)
        </Button>
        <Button
          variant={tab === "consumer" ? "primary" : "ghost"}
          onClick={() => setTab("consumer")}
          className="min-h-11"
        >
          Consumer Remedy & Dispute Resolution
        </Button>
      </nav>

      <div className="mt-6">
        {tab === "fraud" ? <FraudWorkspace /> : <ConsumerWorkspace />}
      </div>
    </div>
  );
}
