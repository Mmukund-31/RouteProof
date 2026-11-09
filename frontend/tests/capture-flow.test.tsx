import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { t } from "@/lib/i18n";

const compress = vi.fn();
vi.mock("@/lib/compress", () => ({ compressImage: (...a: unknown[]) => compress(...a) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));
const put = vi.fn();
vi.mock("@/lib/offline-db", () => ({ captureDb: { put: (...a: unknown[]) => put(...a), all: async () => [] } }));
vi.mock("@/lib/sync", () => ({ flushQueue: vi.fn().mockResolvedValue(undefined), retryCapture: vi.fn() }));

let driverState = { lang: "hi" as const, online: true, captures: [] as unknown[] };
vi.mock("@/hooks/use-driver", () => ({
  useDriver: () => ({ ...driverState, tr: (k: Parameters<typeof t>[1]) => t(driverState.lang, k) }),
}));

function geo(code: number | null) {
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: {
      getCurrentPosition: (ok: PositionCallback, fail: PositionErrorCallback) => code === null
        ? ok({ coords: { latitude: 19.8, longitude: 75.3, accuracy: 12 } } as GeolocationPosition)
        : fail({ code, PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 } as GeolocationPositionError),
    },
  });
}

beforeEach(() => {
  driverState = { lang: "hi", online: true, captures: [] };
  compress.mockResolvedValue({ blob: new Blob([new Uint8Array(120 * 1024)]), withinLimit: true, attempts: 1, dim: 1600, quality: 0.8 });
  put.mockResolvedValue(undefined);
  URL.createObjectURL = vi.fn(() => "blob:x");
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => vi.clearAllMocks());

async function capture(container: HTMLElement) {
  const input = container.querySelector('[data-testid="file"]') as HTMLInputElement;
  await act(async () => { fireEvent.change(input, { target: { files: [new File(["x"], "p.jpg", { type: "image/jpeg" })] } }); });
}

describe("driver capture flow", () => {
  it("one dominant camera action and no text inputs anywhere", async () => {
    const { CaptureFlow } = await import("@/components/driver/capture-flow");
    const { container } = render(<CaptureFlow tripId="t1" tripRef="TRP-1" lr="LR-1" destination="Indore" podStatus="PENDING" retakesRemaining={2} refreshStatus={vi.fn()} />);
    expect(screen.getByTestId("camera")).toHaveAccessibleName(t("hi", "takePhoto"));
    expect(container.querySelectorAll('input:not([type="file"]), textarea, select')).toHaveLength(0);
  });

  it("GPS denied: says so, and makes clear the photo is still saved and sent", async () => {
    geo(1);
    const { CaptureFlow } = await import("@/components/driver/capture-flow");
    const { container } = render(<CaptureFlow tripId="t1" tripRef="TRP-1" lr="LR-1" destination="Indore" podStatus="PENDING" retakesRemaining={2} refreshStatus={vi.fn()} />);
    await capture(container);
    const s = await screen.findByTestId("gps-status");
    expect(s).toHaveAttribute("data-state", "permission_denied");
    expect(s).toHaveTextContent(t("hi", "locationDenied"));
    await act(async () => { fireEvent.click(screen.getByTestId("send")); });
    expect(put.mock.calls[0][0]).toMatchObject({ locationStatus: "permission_denied", userId: "u1", latitude: undefined });
  });

  it("GPS unavailable and timeout are reported distinctly from a denial", async () => {
    geo(3);
    const { CaptureFlow } = await import("@/components/driver/capture-flow");
    const { container } = render(<CaptureFlow tripId="t1" tripRef="TRP-1" lr="LR-1" destination="Indore" podStatus="PENDING" retakesRemaining={2} refreshStatus={vi.fn()} />);
    await capture(container);
    expect(await screen.findByTestId("gps-status")).toHaveAttribute("data-state", "timeout");
    expect(screen.getByTestId("gps-status")).toHaveTextContent(t("hi", "locationUnavailable"));
  });

  it("flags a photo that could not be compressed under 300 KB but still lets the driver send it", async () => {
    geo(null);
    compress.mockResolvedValue({ blob: new Blob([new Uint8Array(400 * 1024)]), withinLimit: false, attempts: 6, dim: 640, quality: 0.4 });
    const { CaptureFlow } = await import("@/components/driver/capture-flow");
    const { container } = render(<CaptureFlow tripId="t1" tripRef="TRP-1" lr="LR-1" destination="Indore" podStatus="PENDING" retakesRemaining={2} refreshStatus={vi.fn()} />);
    await capture(container);
    expect(await screen.findByTestId("oversize")).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByTestId("send")); });
    expect(put.mock.calls[0][0]).toMatchObject({ oversize: true, locationStatus: "captured" });
  });

  it("phone storage full: explains it instead of losing the photo silently", async () => {
    geo(null);
    put.mockRejectedValue(new DOMException("full", "QuotaExceededError"));
    const { CaptureFlow } = await import("@/components/driver/capture-flow");
    const { container } = render(<CaptureFlow tripId="t1" tripRef="TRP-1" lr="LR-1" destination="Indore" podStatus="PENDING" retakesRemaining={2} refreshStatus={vi.fn()} />);
    await capture(container);
    await act(async () => { fireEvent.click(screen.getByTestId("send")); });
    expect(await screen.findByRole("alert")).toHaveTextContent(/storage is full/i);
    expect(screen.getByTestId("send")).toBeInTheDocument(); // the photo is still on screen to retry
  });

  it("large green success state and a distinct amber retake state", async () => {
    const { CaptureFlow } = await import("@/components/driver/capture-flow");
    const { rerender } = render(<CaptureFlow tripId="t1" tripRef="TRP-1" lr="LR-1" destination="Indore" podStatus="VERIFIED" retakesRemaining={2} refreshStatus={vi.fn()} />);
    const card = screen.getByTestId("status-card");
    expect(card).toHaveAttribute("data-state", "verified");
    expect(card.className).toContain("bg-teal");
    expect(card).toHaveTextContent(t("hi", "sentOk"));
    rerender(<CaptureFlow tripId="t1" tripRef="TRP-1" lr="LR-1" destination="Indore" podStatus="RETAKE_REQUESTED" retakesRemaining={1} refreshStatus={vi.fn()} />);
    expect(screen.getByTestId("retake-banner").className).toContain("bg-amber");
    expect(screen.getByTestId("camera")).toBeInTheDocument();
  });

  it("speaks the action and the outcome as full sentences in the driver's language", async () => {
    const said: string[] = [];
    (window as unknown as { speechSynthesis: unknown }).speechSynthesis = { getVoices: () => [{ lang: "hi-IN" }], speak: (u: { text: string }) => said.push(u.text), cancel: vi.fn() };
    (globalThis as unknown as { SpeechSynthesisUtterance: unknown }).SpeechSynthesisUtterance = class { lang = ""; voice = null; constructor(public text: string) {} };
    const { CaptureFlow } = await import("@/components/driver/capture-flow");
    const { rerender } = render(<CaptureFlow tripId="t1" tripRef="TRP-1" lr="LR-1" destination="Indore" podStatus="PENDING" retakesRemaining={2} refreshStatus={vi.fn()} />);
    await waitFor(() => expect(said).toContain(t("hi", "sayTakePhoto")));
    rerender(<CaptureFlow tripId="t1" tripRef="TRP-1" lr="LR-1" destination="Indore" podStatus="VERIFIED" retakesRemaining={2} refreshStatus={vi.fn()} />);
    await waitFor(() => expect(said).toContain(t("hi", "sayVerified")));
    delete (window as unknown as { speechSynthesis?: unknown }).speechSynthesis;
  });
});

describe("client POD view page", () => {
  it("shows only what the link returns and fetches without credentials", async () => {
    const f = vi.fn().mockImplementation(async () => new Response(JSON.stringify({
      client: "Company D", label: "Nov H1", scope: "trips", billing_cycle: null, expires_at: "2026-11-20T00:00:00Z", note: "Read-only",
      trips: [{ trip_id: "a", trip_reference: "TRP-A", lr_number: "LR-A", delivery_date: "2026-11-02", destination: "Indore", pod_status: "VERIFIED", pod_reference: "POD-TRP-A-A1", pod_verified_at: "2026-11-03T00:00:00Z", has_image: true },
        { trip_id: "b", trip_reference: "TRP-B", lr_number: "LR-B", delivery_date: null, destination: "Pune", pod_status: "PENDING", pod_reference: null, pod_verified_at: null, has_image: false }],
    }), { status: 200 }));
    vi.stubGlobal("fetch", f);
    const { default: Page } = await import("@/app/view/[token]/page");
    await act(async () => { render(<Page params={Promise.resolve({ token: "tok" })} />); });
    expect(await screen.findByText("TRP-A")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "View POD" })).toHaveLength(1);
    expect(f.mock.calls[0][1]).toMatchObject({ credentials: "omit" });
    vi.unstubAllGlobals();
  });

  it("explains an expired link", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 410 })));
    const { default: Page } = await import("@/app/view/[token]/page");
    await act(async () => { render(<Page params={Promise.resolve({ token: "old" })} />); });
    expect(await screen.findByTestId("client-view-error")).toHaveTextContent(/expired/);
    vi.unstubAllGlobals();
  });
});
