import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { pod, trip } from "./fixtures";

const login = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ user: null, loading: false, login, logout: vi.fn() }),
  homeFor: (r: string) => (r === "driver" ? "/driver" : "/dashboard"),
}));
vi.mock("@/components/auth-image", () => ({ ImageViewer: () => <div data-testid="viewer" /> }));

const toast = { success: vi.fn(), error: vi.fn(), info: vi.fn() };
vi.mock("@/components/ui/toast", async (orig) => ({ ...(await orig<object>()), useToast: () => toast }));

const api = vi.hoisted(() => ({
  options: vi.fn(), metrics: vi.fn(), recent: vi.fn(), missing: vi.fn(), trips: vi.fn(), review: vi.fn(), billingQueue: vi.fn(), createExport: vi.fn(), exports: vi.fn(),
  markInvoiced: vi.fn(),
}));
vi.mock("@/services", () => ({ services: api }));
const downloadFile = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<object>()), downloadFile }));

beforeEach(() => { vi.clearAllMocks(); api.exports.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 }); api.options.mockResolvedValue({ clients: [{ id: "c1", name: "Company D", code: "CMPD" }], branches: ["Pune"], billing_cycles: ["2026-11-H1"], data_source: "demo" }); });

describe("Login", () => {
  it("submits credentials and shows server errors", async () => {
    const { default: LoginPage } = await import("@/app/login/page");
    login.mockRejectedValueOnce(new Error("Incorrect email or password"));
    render(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Email"), "billing@routeproof.demo");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(login).toHaveBeenCalledWith("billing@routeproof.demo", "wrong");
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password");
  });
});

describe("Dashboard", () => {
  it("renders values returned by the backend, with the demo-data label", async () => {
    api.metrics.mockResolvedValue({
      data_source: "demo", total_trips: 37, in_transit: 4, delivered: 33, pods_pending: 9, pods_uploaded: 24, ai_verified: 14, human_verified: 2,
      needs_review: 5, retake_requests: 2, billing_ready: 9, exported: 6, invoiced: 1, trips_without_pod: 12, avg_delivery_to_upload_hours: 49,
      avg_upload_to_billing_ready_hours: 0.8, pods_within_24h_pct: 54.2, aging: [{ bucket: "0-2 days", count: 3, freight: 1 }], branches: [],
      clients: [{ client: "Company D", trips: 12, pending_pod: 4, needs_review: 1, billing_ready: 2, exported: 1, freight_awaiting_pod: 1000 }],
    });
    api.recent.mockResolvedValue({ items: [] });
    api.missing.mockResolvedValue({ items: [{ trip_id: "t9", trip_reference: "TRP-66162", lr_number: "LR-66162", client: "Company B", branch: "Pune",
      days_since_delivery: 12, overdue: true, freight_amount: 41000, pod_state: "PENDING" }], overdue_count: 1, overdue_after_days: 3,
      freight_blocked: 41000, pending_reviews: 0, filters: {} });
    const { default: Dashboard } = await import("@/app/(exec)/dashboard/page");
    render(<Dashboard />);
    expect(await screen.findByText("37")).toBeInTheDocument();
    // the actionable list is on the dashboard itself, not only behind a separate screen
    expect(await screen.findByRole("link", { name: "TRP-66162" })).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-missing")).toHaveTextContent("1 overdue");
    expect(screen.getByText("Seeded demo data")).toBeInTheDocument();
    expect(screen.getByText("14")).toBeInTheDocument();
    expect(screen.getByText("54.2%")).toBeInTheDocument();
    expect(api.metrics).toHaveBeenCalled();
  });

  it("shows an error state with retry when the API fails", async () => {
    api.metrics.mockRejectedValue(new Error("boom"));
    api.recent.mockResolvedValue({ items: [] });
    const { default: Dashboard } = await import("@/app/(exec)/dashboard/page");
    render(<Dashboard />);
    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("Trip search", () => {
  it("queries the backend with the (debounced) search text", async () => {
    api.trips.mockResolvedValue({ items: [trip()], total: 1, page: 1, page_size: 15 });
    const { default: TripsPage } = await import("@/app/(exec)/trips/page");
    render(<TripsPage />);
    expect(await screen.findByText("TRP-66141")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Search trips"), "Indore");
    await waitFor(() => expect(api.trips).toHaveBeenLastCalledWith(expect.objectContaining({ q: "Indore" })), { timeout: 2000 });
  });

  it("shows an empty state", async () => {
    api.trips.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 15 });
    const { default: TripsPage } = await import("@/app/(exec)/trips/page");
    render(<TripsPage />);
    expect(await screen.findByText("No trips match")).toBeInTheDocument();
  });
});

describe("AI verification & human review", () => {
  it("highlights mismatches, low confidence and never claims authenticity", async () => {
    const { PodReview } = await import("@/components/pod-review");
    render(<PodReview pod={pod()} onChanged={vi.fn()} />);
    const qty = screen.getByTestId("row-delivered_quantity");
    expect(within(qty).getByText(/72% confidence · low/)).toBeInTheDocument();
    expect(within(qty).getByText("Delivered 94.0 vs expected 100")).toBeInTheDocument();
    expect(within(screen.getByTestId("row-lr_number")).getByText("98% confidence")).toBeInTheDocument();
    expect(screen.getByText(/does not authenticate them/)).toBeInTheDocument();
    expect(screen.getAllByText("Shortage remark").length).toBeGreaterThanOrEqual(2); // reason badge + field row
    expect(within(screen.getByTestId("row-shortage_detected")).getByText(/Short by 6 cartons/)).toBeInTheDocument();
    expect(screen.getByTestId("viewer")).toBeInTheDocument();
  });

  it("requires a reason for corrections, then submits only the changed fields", async () => {
    api.review.mockResolvedValue(pod({ verification_status: "VERIFIED" }));
    const onChanged = vi.fn();
    const { PodReview } = await import("@/components/pod-review");
    render(<PodReview pod={pod()} onChanged={onChanged} />);
    const input = screen.getByLabelText("Correct Delivered quantity");
    fireEvent.change(input, { target: { value: "96" } });
    await userEvent.click(screen.getByRole("button", { name: /^Approve$/ }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Approve" }));
    expect(toast.error).toHaveBeenCalledWith("Please enter a reason");
    expect(api.review).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText(/Reason \/ note/), "Counted again on delivery note");
    // The POD carries a shortage exception: approving it also needs a recorded rationale.
    await userEvent.click(within(dialog).getByRole("button", { name: "Approve" }));
    expect(toast.error).toHaveBeenCalledWith("Please record why the exception is accepted");
    expect(api.review).not.toHaveBeenCalled();
    expect(within(screen.getByTestId("exception-box")).getByText(/Shortage remark/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Why is this exception accepted/), "Client accepted the shortage");
    await userEvent.click(within(dialog).getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(api.review).toHaveBeenCalledWith("pod-1", { decision: "APPROVE", corrections: { delivered_quantity: 96 },
      correction_reason: "Counted again on delivery note", approval_reason: "Client accepted the shortage" }));
    expect(onChanged).toHaveBeenCalled();
  });

  it("disables retake once the cap is reached", async () => {
    const { PodReview } = await import("@/components/pod-review");
    render(<PodReview pod={pod({ retakes_remaining: 0, retake_count: 2 })} onChanged={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Request retake \(0 left\)/ })).toBeDisabled();
  });

  it("shows corrected values with the preserved AI original in review history", async () => {
    const { PodReview } = await import("@/components/pod-review");
    const p = pod({ verification_status: "VERIFIED", verification_method: "human", effective_values: { ...pod().effective_values, remarks: "Settled" },
      reviews: [{ id: "r1", reviewer_id: "u", decision: "APPROVED", original_values: { remarks: "Short by 6 cartons" }, corrected_values: { remarks: "Settled" }, correction_reason: "Credit note", reviewed_at: "2026-11-03T10:00:00Z" }] });
    render(<PodReview pod={p} onChanged={vi.fn()} />);
    expect(within(screen.getByTestId("row-remarks")).getByText("Corrected")).toBeInTheDocument();
    expect(screen.getByText("Short by 6 cartons", { selector: "span.line-through" })).toBeInTheDocument();
  });
});

describe("Billing export", () => {
  const row = (id: string, ref: string, exported = false) => ({
    id, trip_reference: ref, lr_number: "LR-" + ref, eway_bill_number: "33", client: { id: "c1", name: "Company D" }, destination: "Indore", vehicle: "MH",
    freight_amount: "41200.00", delivery_date: "2026-11-02", billing_cycle: "2026-11-H1", pod_reference: "POD", pod_verified_at: "2026-11-03T00:00:00Z",
    verification_method: "ai", export_status: exported ? "EXPORTED" : "NOT_EXPORTED", billing_status: exported ? "EXPORTED" : "BILLING_READY",
  });

  it("exports selected trips and downloads the CSV", async () => {
    api.billingQueue.mockResolvedValue({ items: [row("t1", "TRP-1")], total: 1, page: 1, page_size: 15, total_freight: "41200.00" });
    api.createExport.mockResolvedValue({ id: "e1", export_reference: "RPX-1", trip_count: 1 });
    const { default: Billing } = await import("@/app/(exec)/billing/page");
    render(<Billing />);
    await userEvent.click(await screen.findByLabelText("Select TRP-1"));
    await userEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /Export & download/ }));
    await waitFor(() => expect(api.createExport).toHaveBeenCalledWith(expect.objectContaining({ trip_ids: ["t1"], reexport: false })));
    expect(downloadFile).toHaveBeenCalledWith("/billing/exports/e1/download", "RPX-1.csv");
  });

  it("forces an explicit reason when re-exporting an already exported trip", async () => {
    api.billingQueue.mockResolvedValue({ items: [row("t2", "TRP-2", true)], total: 1, page: 1, page_size: 15, total_freight: "41200.00" });
    api.createExport.mockResolvedValue({ id: "e2", export_reference: "RPX-2", trip_count: 1 });
    const { default: Billing } = await import("@/app/(exec)/billing/page");
    render(<Billing />);
    await userEvent.click(await screen.findByLabelText("Select TRP-2"));
    await userEvent.click(screen.getByRole("button", { name: "Re-export CSV" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /Export & download/ }));
    expect(toast.error).toHaveBeenCalledWith("Enter a reason to re-export");
    expect(api.createExport).not.toHaveBeenCalled();
    await userEvent.type(within(dialog).getByLabelText("Reason for re-export"), "Import failed");
    await userEvent.click(within(dialog).getByRole("button", { name: /Export & download/ }));
    await waitFor(() => expect(api.createExport).toHaveBeenCalledWith(expect.objectContaining({ reexport: true, reexport_reason: "Import failed" })));
  });

  it("shows an empty state when nothing is billing-ready", async () => {
    api.billingQueue.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 15, total_freight: "0.00" });
    const { default: Billing } = await import("@/app/(exec)/billing/page");
    render(<Billing />);
    expect(await screen.findByText("Nothing is billing-ready")).toBeInTheDocument();
  });
});

describe("Review distinctions", () => {
  it("labels a provider failure as a system error, not a document problem, and shows why GPS is missing", async () => {
    const { PodReview } = await import("@/components/pod-review");
    render(<PodReview pod={pod({ review_reasons: ["AI_ERROR"], review_categories: ["system"], review_priority: "medium",
      latitude: null, longitude: null, location_status: "permission_denied" })} onChanged={vi.fn()} />);
    expect(screen.getByText("System error")).toBeInTheDocument();
    expect(screen.getByText(/system failure, not a problem with the document/)).toBeInTheDocument();
    expect(screen.getByTestId("gps")).toHaveTextContent("Permission denied on device");
  });

  it("distinguishes a POD approved with an accepted exception", async () => {
    const { PodReview } = await import("@/components/pod-review");
    render(<PodReview pod={pod({ verification_status: "VERIFIED", verification_method: "human", approved_exceptions: ["SHORTAGE"],
      reviews: [{ id: "r1", reviewer_id: "u", decision: "APPROVED", original_values: {}, corrected_values: null, correction_reason: null,
        approval_reason: "Client accepted shortage", accepted_exceptions: ["SHORTAGE"], reviewed_at: "2026-11-03T10:00:00Z" }] })} onChanged={vi.fn()} />);
    expect(screen.getByTestId("approved-exception")).toHaveTextContent(/with exception.*Shortage remark.*Client accepted shortage/);
  });
});
