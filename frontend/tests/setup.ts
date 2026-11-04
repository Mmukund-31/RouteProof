import "fake-indexeddb/auto";
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import React from "react";

afterEach(() => cleanup());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/",
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...p }: { href: string; children: React.ReactNode }) => React.createElement("a", { href, ...p }, children),
}));
// jsdom has no layout engine; Recharts' ResponsiveContainer would render nothing.
vi.mock("recharts", () => {
  const Stub = ({ children }: { children?: React.ReactNode }) => React.createElement("div", { "data-chart": true }, children);
  return { ResponsiveContainer: Stub, BarChart: Stub, Bar: Stub, XAxis: Stub, YAxis: Stub, CartesianGrid: Stub, Tooltip: Stub, Legend: Stub };
});
