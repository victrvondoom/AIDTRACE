"use client";

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import { Icon } from "@/components/icon";
import { greenchainDemo, greenchainHealth } from "@/lib/lab-api";
import type { ManufacturerResult } from "@/lib/greenchain/api";

import { useLiveQuery } from "@/lib/use-live-query";

type Message = { from: "guide" | "you"; text: string };
const GUIDE_STEPS = [
  { title: "Define what you need", text: "Start with the product, required quantity, destination, and any certifications. The current GreenChain scenario is illustrative, so treat it as a walkthrough until you connect your supplier catalog.", href: "/hub", action: "Open workspace" },
  { title: "Compare suppliers", text: "GreenChain ranks candidate suppliers using manufacturing, transport, grid, certification, and climate signals. Review the inputs and evidence before choosing a supplier.", href: "/hub", action: "Explore GreenChain" },
  { title: "Build a sourcing shortlist", text: "Save candidates for a quote request, then confirm availability, lead time, quantity breaks, and commercial terms with the supplier.", href: "/projects", action: "Review project records" },
  { title: "Pay after terms are confirmed", text: "Payment is not enabled here yet. Once a live catalog, merchant account, and signed payment confirmation flow are connected, checkout can use hosted Stripe Checkout. No funds move in this workspace today.", href: "#payment-gateway", action: "Gateway readiness" },
];

export default function ProcurementPage() {
  const [transport, setTransport] = useState("sea");
  const [search, setSearch] = useState("");
  const query = useCallback(async () => {
    const demo = await greenchainDemo(transport);
    return demo;
  }, [transport]);
  const supplierQuery = useLiveQuery(query);
  const healthQuery = useLiveQuery(greenchainHealth);
  const suppliers = useMemo(() => (supplierQuery.data?.results ?? []) as unknown as ManufacturerResult[], [supplierQuery.data]);
  const visibleSuppliers = suppliers.filter((supplier) => `${supplier.name} ${supplier.country} ${(supplier.certifications ?? []).join(" ")}`.toLowerCase().includes(search.toLowerCase()));
  const loading = supplierQuery.loading;
  const error = supplierQuery.error;
  const [selected, setSelected] = useState<string[]>([]);
  const [step, setStep] = useState(0);
  const [messages, setMessages] = useState<Message[]>([{ from: "guide", text: "I can walk you from supplier discovery to a purchase-ready request. What are you trying to do?" }]);
  const [question, setQuestion] = useState("");

  const selectedSuppliers = useMemo(() => suppliers.filter((supplier) => selected.includes(supplier.name)), [suppliers, selected]);
  function toggleSupplier(name: string) {
    setSelected((current) => current.includes(name) ? current.filter((item) => item !== name) : [...current, name]);
  }
  function askGuide(value = question) {
    const prompt = value.trim();
    if (!prompt) return;
    const lower = prompt.toLowerCase();
    const answer = lower.includes("pay") || lower.includes("payment") || lower.includes("checkout")
      ? GUIDE_STEPS[3].text
      : lower.includes("supplier") || lower.includes("compare") || lower.includes("greenchain")
        ? `${suppliers.length} candidates are loaded for ${supplierQuery.data?.transport_mode ?? transport} transport. ${selected.length} are shortlisted. ${suppliers[0] ? `The first ranked candidate is ${suppliers[0].name}; review its evidence and emissions before choosing.` : "Refresh supplier data to compare candidates."} ${healthQuery.error ? "Discovery readiness could not be checked." : `Discovery status: ${healthQuery.data?.live_discovery ?? "checking"}.`}`
        : lower.includes("buy") || lower.includes("order") || lower.includes("quote")
          ? `${selected.length ? `Your shortlist has ${selected.length} candidates: ${selected.join(", ")}. Download the quote brief to review them.` : "Select supplier candidates to start a quote request."} ${GUIDE_STEPS[2].text}`
          : "Begin with the need, compare candidates, create a shortlist, and confirm a supplier quote before any payment. Use the steps below to open each workspace. I only describe actions the connected product can actually perform.";
    setMessages((current) => [...current, { from: "you", text: prompt }, { from: "guide", text: answer }]);
    setQuestion("");
  }
  function downloadRequest() {
    const body = ["AIDTRACE · Procurement quote request", "Status: DRAFT — illustrative supplier candidates; confirm identity, availability, price and terms directly.", `Created: ${new Date().toISOString()}`, "", ...selectedSuppliers.map((supplier) => `- ${supplier.name} | ${supplier.city ?? "Location unknown"}, ${supplier.country} | ranking #${supplier.rank} | ${supplier.env_rating} | certifications: ${supplier.certifications?.join(", ") || "not listed"}`)].join("\n");
    const url = URL.createObjectURL(new Blob([body], { type: "text/plain;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "aidtrace-quote-request-draft.txt"; anchor.click(); URL.revokeObjectURL(url);
  }

  return (
    <div className="mx-auto max-w-[1380px] space-y-7">
      <header className="relative overflow-hidden border border-line bg-surface">
        <div className="absolute inset-y-0 right-0 w-1/2 bg-[radial-gradient(ellipse_at_top_right,color-mix(in_srgb,var(--accent)_18%,transparent),transparent_65%)]" />
        <div className="relative grid gap-7 p-6 sm:p-9 lg:grid-cols-[1fr_auto] lg:items-end">
          <div className="max-w-3xl">
            <p className="flex items-center gap-2 text-micro font-bold uppercase tracking-[0.16em] text-accent"><Icon name="truck" size={15} /> AIDTRACE · centralized sourcing</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">From supplier signal to purchase-ready brief.</h1>
            <p className="mt-3 max-w-2xl text-body leading-relaxed text-muted">Compare supply risk, build a shortlist, and let the guide move with you through the project. Procurement decisions stay attached to evidence and commercial terms.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a href="#supplier-network" className="inline-flex items-center gap-2 bg-accent px-4 py-2.5 text-sm font-semibold text-on-accent">Explore suppliers <Icon name="caret-right" size={16} /></a>
            <a href="#project-guide" className="inline-flex items-center gap-2 border border-line bg-surface px-4 py-2.5 text-sm font-semibold text-ink"><Icon name="chat-centered-text" size={16} /> Ask project guide</a>
          </div>
        </div>
        <div className="relative grid grid-cols-2 border-t border-line sm:grid-cols-4">
          {["Discover", "Compare", "Shortlist", "Confirm & pay"].map((label, index) => <div key={label} className="flex items-center gap-2 border-r border-line px-4 py-3 text-caption last:border-r-0"><span className={`grid size-6 place-items-center rounded-full text-micro font-bold ${index <= (selected.length ? 2 : suppliers.length ? 1 : 0) ? "bg-accent-soft text-accent" : "bg-surface-2 text-muted"}`}>{index + 1}</span><span className="font-medium">{label}</span></div>)}
        </div>
      </header>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section id="supplier-network" className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-micro font-bold uppercase tracking-widest text-muted">Supplier network</p><h2 className="mt-1 text-xl font-semibold">Shortlist candidates</h2></div><div className="text-right text-caption text-muted">{supplierQuery.data?.notice ?? "Loading scenario provenance"}</div></div>
          <div className="flex flex-wrap items-center gap-3 border border-line bg-surface p-3">
            <label className="text-caption">Transport <select aria-label="Transport mode" value={transport} onChange={(event) => setTransport(event.target.value)} className="ml-2 border border-line bg-surface p-2">{["sea", "air", "rail", "road"].map((mode) => <option key={mode} value={mode}>{mode}</option>)}</select></label>
            <input aria-label="Filter suppliers" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Filter name, country, certification" className="min-w-0 flex-1 border border-line bg-surface p-2 text-caption" />
            <button type="button" disabled={supplierQuery.refreshing} onClick={() => void supplierQuery.refresh()} className="border border-line px-3 py-2 text-caption disabled:opacity-50">{supplierQuery.refreshing ? "Refreshing?" : "Refresh suppliers"}</button>
            <p role="status" className="w-full text-micro text-muted">{supplierQuery.updatedAt ? `Showing ${supplierQuery.data?.transport_mode} scenario ? updated ${new Date(supplierQuery.updatedAt).toLocaleTimeString()} ? ${visibleSuppliers.length} matching candidates` : "Waiting for supplier data"}</p>
          </div>
          {error && <div role="alert" className="border border-danger/30 bg-danger/5 p-4 text-sm text-danger">{error} <Link href="/hub" className="underline">Open GreenChain workspace</Link></div>}
          {loading && <div className="grid gap-3 md:grid-cols-2"><div className="h-44 animate-pulse bg-surface-2" /><div className="h-44 animate-pulse bg-surface-2" /></div>}
          {!loading && <div className="grid gap-3 md:grid-cols-2">{visibleSuppliers.map((supplier) => {
            const chosen = selected.includes(supplier.name);
            return <article key={supplier.name} className={`border p-5 transition-colors ${chosen ? "border-accent bg-accent-soft/30" : "border-line bg-surface"}`}>
              <div className="flex items-start justify-between gap-3"><div><p className="text-micro font-semibold uppercase tracking-wider text-muted">Rank #{supplier.rank} · {supplier.env_rating}</p><h3 className="mt-1 text-lg font-semibold">{supplier.name}</h3><p className="mt-1 text-caption text-muted">{[supplier.city, supplier.country].filter(Boolean).join(", ")}</p></div><span className="grid size-10 place-items-center border border-line bg-surface text-accent"><Icon name="cube" size={19} /></span></div>
              <div className="mt-4 grid grid-cols-2 gap-3 border-y border-line py-3 text-caption"><div><span className="block text-micro uppercase tracking-wider text-muted">Footprint estimate</span><strong className="mt-1 block tabular">{supplier.scores?.total_tco2e?.toFixed(1) ?? "—"} tCO₂e</strong></div><div><span className="block text-micro uppercase tracking-wider text-muted">Disclosure</span><strong className="mt-1 block capitalize">{supplier.disclosure_status}</strong></div></div>
              <div className="mt-3 flex min-h-6 flex-wrap gap-1.5">{(supplier.certifications ?? []).slice(0, 3).map((cert) => <span key={cert} className="border border-line px-2 py-1 text-micro text-muted">{cert}</span>)}{!supplier.certifications?.length && <span className="text-caption text-muted">No certifications listed</span>}</div>
              <button type="button" onClick={() => toggleSupplier(supplier.name)} className={`mt-4 w-full border px-3 py-2 text-sm font-semibold transition-colors ${chosen ? "border-accent bg-accent text-on-accent" : "border-line text-ink hover:border-accent"}`}>{chosen ? "Added to shortlist" : "Add to shortlist"}</button>
            </article>;
          })}</div>}
          {!loading && visibleSuppliers.length === 0 && <p className="p-4 text-caption text-muted">No suppliers match the current filter.</p>}
          <p className="border-l-2 border-caution bg-caution/5 px-4 py-3 text-caption leading-relaxed text-muted">Candidate scores are decision support, not supplier verification or a quote. This scenario contains no live stock, contracted prices, or delivery commitments.</p>
        </section>

        <aside className="space-y-4">
          <section id="payment-gateway" className="border border-line bg-surface p-5">
            <div className="flex items-center justify-between"><div><p className="text-micro font-bold uppercase tracking-wider text-muted">Sourcing desk</p><h2 className="mt-1 text-lg font-semibold">Your shortlist</h2></div><span className="grid size-8 place-items-center rounded-full bg-accent-soft text-sm font-bold text-accent">{selected.length}</span></div>
            {selected.length ? <ul className="mt-4 space-y-2">{selectedSuppliers.map((supplier) => <li key={supplier.name} className="flex items-center justify-between gap-2 border-b border-line pb-2 text-sm"><span className="truncate">{supplier.name}</span><button type="button" onClick={() => toggleSupplier(supplier.name)} aria-label={`Remove ${supplier.name}`} className="text-caption text-muted hover:text-danger">Remove</button></li>)}</ul> : <p className="mt-4 border border-dashed border-line p-4 text-caption leading-relaxed text-muted">Add supplier candidates here. Review the ranking and evidence before sending a quote request.</p>}
            <button type="button" onClick={downloadRequest} disabled={!selectedSuppliers.length || Boolean(error) || supplierQuery.refreshing} className="mt-4 w-full bg-ink px-4 py-2.5 text-sm font-semibold text-surface disabled:cursor-not-allowed disabled:opacity-40">Download quote brief</button>
            <p className="mt-2 text-center text-micro text-muted">Draft only · no supplier message is sent</p>
          </section>
          <section className="border border-line bg-surface p-5">
            <div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-full bg-surface-2 text-accent">$</span><div><p className="text-micro font-bold uppercase tracking-wider text-muted">Payment gateway</p><h3 className="font-semibold">Not connected</h3></div></div>
            <p className="mt-3 text-caption leading-relaxed text-muted">Stripe Checkout is the planned hosted checkout path. It can be enabled after live product prices, merchant credentials, webhook verification, and order storage are configured.</p>
            <div className="mt-3 flex items-center gap-2 border border-caution/30 bg-caution/5 px-3 py-2 text-caption text-caution"><Icon name="warning" size={15} /> Checkout unavailable · no charge can be made</div>
          </section>
          <section className="border border-line bg-surface p-5">
            <p className="text-micro font-bold uppercase tracking-wider text-muted">Project map</p><div className="mt-3 space-y-2">{GUIDE_STEPS.map((item, index) => <button type="button" key={item.title} onClick={() => setStep(index)} className={`flex w-full items-center gap-3 border p-3 text-left transition-colors ${step === index ? "border-accent bg-accent-soft/30" : "border-line hover:bg-surface-2"}`}><span className="grid size-7 shrink-0 place-items-center rounded-full bg-surface-2 text-caption font-bold">{index + 1}</span><span className="text-sm font-medium">{item.title}</span><Icon name="caret-right" className="ml-auto size-4 text-muted" /></button>)}</div>
            <p className="mt-3 text-caption leading-relaxed text-muted">{GUIDE_STEPS[step].text}</p><Link href={GUIDE_STEPS[step].href} className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-accent">{GUIDE_STEPS[step].action} <Icon name="caret-right" size={15} /></Link>
          </section>
        </aside>
      </div>

      <section id="project-guide" className="grid gap-5 border border-line bg-surface p-5 sm:p-7 lg:grid-cols-[1fr_1.1fr]">
        <div><p className="flex items-center gap-2 text-micro font-bold uppercase tracking-widest text-accent"><Icon name="chat-centered-text" size={16} /> Project guide · always in context</p><h2 className="mt-2 text-2xl font-semibold">Ask your way through the workflow.</h2><p className="mt-2 max-w-lg text-sm leading-relaxed text-muted">A practical project bot that points to the right workspace, explains what each step can do, and keeps unsupported actions visible. Ask about suppliers, buying, quotes, or payment.</p><div className="mt-4 flex flex-wrap gap-2">{["How do I compare suppliers?", "Can I buy now?", "What happens before payment?"].map((prompt) => <button key={prompt} type="button" onClick={() => askGuide(prompt)} className="border border-line px-3 py-2 text-caption text-muted hover:border-accent hover:text-ink">{prompt}</button>)}</div></div>
        <div className="flex min-h-[310px] flex-col border border-line bg-canvas">
          <div className="flex items-center justify-between border-b border-line px-4 py-3"><span className="flex items-center gap-2 text-sm font-semibold"><span className="size-2 rounded-full bg-positive" /> AIDTRACE Guide</span><span className="text-micro uppercase tracking-widest text-muted">Project navigation</span></div>
          <div className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">{messages.map((message, index) => <div key={`${message.from}-${index}`} className={`max-w-[90%] ${message.from === "you" ? "ml-auto" : ""}`}><p className={`px-3 py-2.5 text-sm leading-relaxed ${message.from === "you" ? "bg-accent text-on-accent" : "border border-line bg-surface text-ink"}`}>{message.text}</p></div>)}</div>
          <form onSubmit={(event) => { event.preventDefault(); askGuide(); }} className="flex gap-2 border-t border-line p-3"><label htmlFor="guide-question" className="sr-only">Ask the project guide</label><input id="guide-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about sourcing, quotes, or payment…" className="min-w-0 flex-1 border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent"/><button type="submit" className="grid size-10 shrink-0 place-items-center bg-accent text-on-accent" aria-label="Send question"><Icon name="caret-right" size={18} /></button></form>
        </div>
      </section>
    </div>
  );
}
