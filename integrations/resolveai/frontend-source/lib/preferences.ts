export const PREF_KEYS = {
  notificationsLive: "proxy:pref-notifications-live",
  notificationsPollMs: "proxy:pref-notifications-poll-ms",
  kgDefaultTab: "proxy:pref-kg-default-tab",
  newAnalysisDefaultDomain: "proxy:pref-new-analysis-domain",
  // Optional, user-supplied. There is no auth/user profile to derive a name
  // from yet, so the dashboard greeting stays name-less unless someone sets
  // this in Settings -- never a hardcoded name, which would greet every
  // visitor as whoever the developer happened to be.
  displayName: "proxy:pref-display-name",
} as const;

export function getPref(key: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  return window.localStorage.getItem(key) ?? fallback;
}

export function setPref(key: string, value: string) {
  window.localStorage.setItem(key, value);
}
