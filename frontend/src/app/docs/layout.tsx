import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "AIDTRACE",
  description: "AIDTRACE connected intelligence platform.",
};

export default function DocsLayout() {
  redirect("/");
}

