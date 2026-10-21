"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ThemeToggle } from "@/components/theme-toggle";
import { getMe, login } from "@/lib/auth";

import { Icon } from "@/components/icon";
import { Button } from "@/components/ui";
import { roleHome } from "@/components/use-role";

// The one-click demo signs in as the read-only `demo` user. Both values are baked into the bundle,
// so they are public by design: they must only ever be that account's credentials. Unset = no button.
const DEMO_EMAIL = process.env.NEXT_PUBLIC_DEMO_EMAIL;
const DEMO_PASSWORD = process.env.NEXT_PUBLIC_DEMO_PASSWORD;
const HAS_DEMO_CREDENTIALS = Boolean(DEMO_EMAIL && DEMO_PASSWORD);

function workspacePath(role?: string) {
  if (role === "demo") return roleHome("demo");
  return role === "field_worker" ? "/briefs" : "/hub";
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Deliberately no "already signed in → skip to workspace" auto-redirect here — every
  // visit to /login shows the sign-in form, even with a valid stored token. Otherwise a
  // leftover session from earlier testing silently swaps the page mid-view, which is
  // exactly the wrong thing to have happen while presenting.

  // Real login → POST /auth/login (Supabase). Stores tokens, then routes directly in.
  async function doLogin(em: string, pw: string) {
    setError(null);
    setBusy(true);
    try {
      await login(em, pw);
      const user = await getMe();
      const requestedDestination = new URLSearchParams(window.location.search).get("next");
      router.push(requestedDestination === "field-voice" && user?.role === "field_worker" ? "/field/voice" : workspacePath(user?.role));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
      setBusy(false);
    }
  }

  function signIn(e: React.FormEvent) {
    e.preventDefault();
    void doLogin(email, password);
  }

  // One-click demo → if credentials are configured, signs into the real demo account.
  // Otherwise bypasses auth entirely and navigates straight to the dashboard.
  // The AppShell's auth flow defaults to engineer role when no token exists and strict
  // auth is off, so the user sees the full application without needing a running backend.
  function tryDemo() {
    if (HAS_DEMO_CREDENTIALS && DEMO_EMAIL && DEMO_PASSWORD) {
      void doLogin(DEMO_EMAIL, DEMO_PASSWORD);
    } else {
      setBusy(true);
      router.push("/hub");
    }
  }

  return (
    <main className="relative grid min-h-dvh place-items-center bg-canvas px-5 py-16">
      <title>AIDTRACE: Sign in</title>
      <Link href="/" aria-label="Back to landing page" className="absolute left-5 top-5 grid size-10 place-items-center border border-line bg-surface text-muted transition-colors hover:border-[color-mix(in_srgb,var(--accent)_45%,var(--line))] hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
        <Icon name="caret-left" className="size-4" />
      </Link>
      <div className="absolute right-5 top-5">
        <ThemeToggle />
      </div>

      <div
        data-testid="login-workspace"
        className="grid w-full max-w-5xl overflow-hidden border border-line bg-surface lg:min-h-[620px] lg:grid-cols-[minmax(0,1fr)_minmax(360px,0.72fr)]"
      >
        {/* Permanently dark, like the nav rail and the landing's dark bands:
            `sidebar-scope` remaps the tokens, so this panel does not invert with the theme. */}
        <section
          data-testid="login-context"
          className="sidebar-scope relative hidden p-10 lg:flex lg:flex-col lg:justify-between"
        >
          <div>
            <p className="inline-flex bg-accent px-2.5 py-1 text-label font-semibold uppercase tracking-[0.08em] text-on-accent">
              Supply chain risk intelligence
            </p>
            <h2 className="display mt-5 max-w-lg text-display text-balance text-ink">
              Enter the workspace with the context your role needs.
            </h2>
            <p className="mt-5 max-w-md text-body leading-relaxed text-muted text-pretty">
              Every finding carries its source, its independent support and the date it was
              last verified. Sign-in decides where you land and what you can open.
            </p>
          </div>

          {/* Was a fake skeleton mock — grey placeholder bars say nothing. This says what
              each role actually gets, which is also what `routeAllowed` enforces. */}
          <div className="mesh stagger mt-10">
            {[
              { icon: "squares-four", title: "Procurement leads", desc: "See which sourcing decisions no longer stand on current evidence." },
              { icon: "scales", title: "Risk investigators", desc: "Trace any claim from a supplier to its source and the decisions that rest on it." },
              { icon: "waveform", title: "Field teams", desc: "Multilingual voice notes and deviation flags, sized for a phone on site." },
            ].map((row) => (
              <div key={row.title} className="flex items-start gap-3 bg-surface px-4 py-3.5">
                <Icon name={row.icon as "squares-four"} className="mt-0.5 size-[18px] shrink-0 text-accent" />
                <span className="min-w-0">
                  <span className="block text-body font-medium text-ink">{row.title}</span>
                  <span className="mt-0.5 block text-caption leading-relaxed text-muted">{row.desc}</span>
                </span>
              </div>
            ))}
          </div>
        </section>

        <section data-testid="login-form-panel" className="flex items-center justify-center border-line px-5 py-10 sm:px-10 lg:border-l">
          <div className="w-full max-w-sm">
            <Image src="/logo.png" alt="AIDTRACE" width={40} height={40} priority className="size-10 object-cover" />
            <h1 className="display mt-6 text-display text-ink sm:text-hero">Sign in to AIDTRACE</h1>
            <p className="mt-2 text-body text-muted">Know when a supplier decision is no longer safe.</p>

            <form onSubmit={signIn} className="mt-8 flex flex-col gap-4">
              <label className="flex flex-col gap-1.5">
                <span className="text-label font-semibold uppercase tracking-[0.08em] text-muted">Email</span>
                <input
                  type="email"
                  name="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="min-h-11 border border-line bg-canvas px-3.5 text-sm text-ink outline-none transition-colors placeholder:text-muted/60 hover:border-[color-mix(in_srgb,var(--accent)_40%,var(--line))] focus-visible:border-accent focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-accent"
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-label font-semibold uppercase tracking-[0.08em] text-muted">Password</span>
                <input
                  type="password"
                  name="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="min-h-11 border border-line bg-canvas px-3.5 text-sm text-ink outline-none transition-colors placeholder:text-muted/60 hover:border-[color-mix(in_srgb,var(--accent)_40%,var(--line))] focus-visible:border-accent focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-accent"
                />
              </label>
              {error && (
                <p className="border border-[color-mix(in_srgb,var(--danger)_35%,var(--line))] bg-[color-mix(in_srgb,var(--danger)_8%,var(--surface))] px-3 py-2 text-caption text-danger">
                  {error}
                </p>
              )}
              <Button type="submit" variant="primary" disabled={busy} className="mt-1 min-h-11 w-full text-sm font-medium">
                {busy ? "Signing in…" : "Sign in"}
                {!busy && <span aria-hidden="true">›</span>}
              </Button>
              <Button
                type="button"
                id="demo-sign-in"
                onClick={tryDemo}
                disabled={busy}
                className="min-h-11 w-full border border-accent/30 bg-[color-mix(in_srgb,var(--accent)_8%,var(--surface))] text-sm font-medium text-accent transition-all hover:bg-[color-mix(in_srgb,var(--accent)_15%,var(--surface))] hover:border-accent/50"
              >
                <Icon name="sparkle" className="size-4" />
                {busy ? "Entering demo…" : "Explore the live demo"}
              </Button>
            </form>
          </div>
        </section>
      </div>
    </main>
  );
}

