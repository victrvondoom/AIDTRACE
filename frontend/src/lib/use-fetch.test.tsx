import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Fetched } from "@/lib/api";
import { useFetch } from "./use-fetch";

describe("useFetch state transitions", () => {
  it("refreshes without flashing loading and stops after unmount", async () => {
    vi.useFakeTimers();
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(false);
    const fn = vi.fn().mockResolvedValue({ data: 42, source: "live" });
    try {
      const { result, unmount } = renderHook(() => useFetch(fn, [], 15000));
      await act(async () => { await Promise.resolve(); });
      expect(result.current.status).toBe("live");
      await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
      expect(fn).toHaveBeenCalledTimes(2);
      expect(result.current.status).toBe("live");
      unmount();
      await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
      expect(fn).toHaveBeenCalledTimes(2);
    } finally {
      hidden.mockRestore();
      vi.useRealTimers();
    }
  });
  it("starts loading, resolves live source to 'live'", async () => {
    const fn = () => Promise.resolve<Fetched<number>>({ data: 42, source: "live" });
    const { result } = renderHook(() => useFetch(fn));

    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("live"));
    if (result.current.status !== "live") throw new Error("unreachable");
    expect(result.current.data).toBe(42);
  });

  // The old "maps a demo source to error" test is gone with the thing it described: fetchers
  // no longer return fixtures on failure, they throw, and `DataSource` has a single member so
  // a fallback cannot be reintroduced without a type error. The throw path is covered below.

  it("catches a throw as 'error'; retry re-runs the fetcher", async () => {
    let calls = 0;
    const fn = (): Promise<Fetched<string>> => {
      calls += 1;
      return calls === 1 ? Promise.reject(new Error("boom")) : Promise.resolve({ data: "ok", source: "live" });
    };
    const { result } = renderHook(() => useFetch(fn));

    await waitFor(() => expect(result.current.status).toBe("error"));
    const state = result.current;
    if (state.status !== "error") throw new Error("unreachable");
    expect(state.error.message).toBe("boom");

    act(() => state.retry());
    await waitFor(() => expect(result.current.status).toBe("live"));
    expect(calls).toBe(2);
  });
});


describe("live refresh policy", () => {
  it("refreshes by default, pauses while hidden, and resumes on focus", async () => {
    vi.useFakeTimers();
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(false);
    const fn = vi.fn().mockResolvedValue({ data: 1, source: "live" });
    const { result, unmount } = renderHook(() => useFetch(fn));
    try {
      await act(async () => {});
      fn.mockResolvedValue({ data: 2, source: "live" });
      await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
      expect(result.current).toEqual({ status: "live", data: 2 });
      hidden.mockReturnValue(true);
      await act(async () => { await vi.advanceTimersByTimeAsync(90000); });
      expect(fn).toHaveBeenCalledTimes(2);
      hidden.mockReturnValue(false);
      await act(async () => { window.dispatchEvent(new Event("focus")); });
      expect(fn).toHaveBeenCalledTimes(3);
    } finally { unmount(); hidden.mockRestore(); vi.useRealTimers(); }
  });

  it("does not overlap requests and restarts after reconnecting", async () => {
    vi.useFakeTimers();
    const online = vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
    let resolve!: (value: Fetched<number>) => void;
    const fn = vi.fn().mockImplementation(() => new Promise<Fetched<number>>((r) => { resolve = r; }));
    const { unmount } = renderHook(() => useFetch(fn));
    try {
      await act(async () => { window.dispatchEvent(new Event("focus")); await vi.advanceTimersByTimeAsync(60000); });
      expect(fn).toHaveBeenCalledTimes(1);
      await act(async () => { resolve({ data: 1, source: "live" }); });
      online.mockReturnValue(false);
      await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
      expect(fn).toHaveBeenCalledTimes(1);
      online.mockReturnValue(true);
      await act(async () => { window.dispatchEvent(new Event("online")); });
      expect(fn).toHaveBeenCalledTimes(2);
    } finally { unmount(); online.mockRestore(); vi.useRealTimers(); }
  });

  it("keeps explicit one-shot reads opt-out and ignores old dependency results", async () => {
    let resolveOld!: (value: Fetched<number>) => void;
    const old = new Promise<Fetched<number>>((resolve) => { resolveOld = resolve; });
    const fn = vi.fn().mockReturnValueOnce(old).mockResolvedValue({ data: 2, source: "live" });
    const { result, rerender, unmount } = renderHook(({ id }) => useFetch(fn, [id], 0), { initialProps: { id: 1 } });
    rerender({ id: 2 });
    await waitFor(() => expect(result.current).toEqual({ status: "live", data: 2 }));
    await act(async () => { resolveOld({ data: 1, source: "live" }); window.dispatchEvent(new Event("focus")); });
    expect(result.current).toEqual({ status: "live", data: 2 });
    expect(fn).toHaveBeenCalledTimes(2);
    unmount();
  });
});
