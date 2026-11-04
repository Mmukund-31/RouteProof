import { describe, expect, it, vi } from "vitest";
import { t, speak, speechSupported } from "@/lib/i18n";
import { stateFor } from "@/components/driver/ui";
import type { Capture } from "@/lib/offline-db";

const cap = (status: Capture["status"], tripId = "t1"): Capture => ({
  id: "c", tripId, tripRef: "T", lr: "L", status, originalSize: 1, compressedSize: 1, capturedAt: "", retryCount: 0, createdAt: "2026-01-01T00:00:00Z",
});

describe("languages & voice", () => {
  it("has Hindi and Marathi labels for essential driver actions", () => {
    expect(t("hi", "takePhoto")).toBe("रसीद की फोटो लें");
    expect(t("mr", "takePhoto")).toBe("पावतीचा फोटो काढा");
    expect(t("en", "takePhoto")).toBe("Take photo of receipt");
    for (const l of ["hi", "mr"] as const) expect(t(l, "retakeRequired")).not.toBe(t("en", "retakeRequired"));
  });

  it("falls back gracefully (returns false) when speech synthesis is unavailable", () => {
    expect(speechSupported()).toBe(false); // jsdom has no speechSynthesis
    expect(speak("hello", "hi")).toBe(false);
  });

  it("falls back to on-screen text when no Hindi voice is installed", () => {
    const speakFn = vi.fn();
    (window as unknown as { speechSynthesis: unknown }).speechSynthesis = { getVoices: () => [{ lang: "en-US" }], speak: speakFn, cancel: vi.fn() };
    (globalThis as unknown as { SpeechSynthesisUtterance: unknown }).SpeechSynthesisUtterance = class { lang = ""; voice = null; constructor(public text: string) {} };
    expect(speak("नमस्ते", "hi")).toBe(false);
    expect(speakFn).not.toHaveBeenCalled();
    expect(speak("hello", "en")).toBe(true);
    delete (window as unknown as { speechSynthesis?: unknown }).speechSynthesis;
  });
});

describe("driver state mapping", () => {
  it("local queue state wins until the server acknowledges", () => {
    expect(stateFor({ id: "t1", pod_status: "PENDING" }, [], true)).toBe("ready");
    expect(stateFor({ id: "t1", pod_status: "PENDING" }, [cap("PENDING")], true)).toBe("queued");
    expect(stateFor({ id: "t1", pod_status: "PENDING" }, [cap("PENDING")], false)).toBe("waiting");
    expect(stateFor({ id: "t1", pod_status: "PENDING" }, [cap("UPLOADING")], true)).toBe("uploading");
    expect(stateFor({ id: "t1", pod_status: "PENDING" }, [cap("RETRY_REQUIRED")], true)).toBe("retryRequired");
    expect(stateFor({ id: "t1", pod_status: "PENDING" }, [cap("FAILED")], true)).toBe("failed");
  });

  it("maps server statuses to clear driver states", () => {
    expect(stateFor({ id: "t1", pod_status: "VERIFIED" }, [cap("UPLOADED")], true)).toBe("verified");
    expect(stateFor({ id: "t1", pod_status: "RETAKE_REQUESTED" }, [cap("UPLOADED")], true)).toBe("retake");
    expect(stateFor({ id: "t1", pod_status: "NEEDS_REVIEW" }, [], true)).toBe("review");
    expect(stateFor({ id: "t1", pod_status: "AI_PROCESSING" }, [], true)).toBe("processing");
    expect(stateFor({ id: "t1", pod_status: "PENDING" }, [cap("UPLOADED")], true)).toBe("processing");
    expect(stateFor({ id: "t2", pod_status: "PENDING" }, [cap("PENDING", "t1")], true)).toBe("ready"); // other trip's capture ignored
  });
});
