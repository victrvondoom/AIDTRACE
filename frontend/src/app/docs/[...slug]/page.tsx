import { redirect } from "next/navigation";
import { listDocs } from "@/lib/docs";

type Params = { slug: string[] };

export const dynamicParams = false;

export function generateStaticParams(): Params[] {
  return listDocs().map((d) => ({ slug: d.slug.split("/") }));
}

export default function DocPage() {
  redirect("/");
}

