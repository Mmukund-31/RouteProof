/** IndexedDB persistence for captured PODs. Keeps the original and the compressed upload artifact as separate blobs. */
export type CaptureStatus = "PENDING" | "UPLOADING" | "UPLOADED" | "FAILED" | "RETRY_REQUIRED";
export type LocationStatus = "captured" | "permission_denied" | "unavailable" | "timeout" | "unsupported";

export interface Capture {
  id: string; // capture UUID, reused as the idempotency key on every retry
  tripId: string;
  tripRef: string;
  lr: string;
  linkToken?: string; // hired-driver flow (no account)
  userId?: string; // driver who captured it; only uploaded while that driver is signed in
  status: CaptureStatus;
  original?: Blob; // full-resolution camera file, kept until the server acknowledges IT (not just the compressed copy)
  originalStatus?: "PENDING" | "UPLOADED" | "FAILED";
  originalAttempts?: number;
  /** Compression could not get under 300 KB; sent anyway and flagged by the server. */
  oversize?: boolean;
  compressed?: Blob; // < 300 KB artifact that is actually uploaded
  originalSize: number;
  compressedSize: number;
  capturedAt: string; // client clock; unverified
  latitude?: number;
  longitude?: number;
  accuracy?: number;
  /** Why there are no coordinates, when there are none: the device said no vs. we could not get a fix. */
  locationStatus?: LocationStatus;
  retryCount: number;
  lastError?: string;
  podId?: string;
  serverStatus?: string;
  createdAt: string;
  ackedAt?: string;
}

const DB = "routeproof";
const STORE = "captures";

function open(): Promise<IDBDatabase> {
  return new Promise((res, rej) => {
    const r = indexedDB.open(DB, 1);
    r.onupgradeneeded = () => {
      const s = r.result.createObjectStore(STORE, { keyPath: "id" });
      s.createIndex("status", "status");
      s.createIndex("tripId", "tripId");
    };
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });
}

async function tx<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open();
  return new Promise<T>((res, rej) => {
    const t = db.transaction(STORE, mode);
    const req = fn(t.objectStore(STORE));
    t.oncomplete = () => { db.close(); res(req.result); };
    t.onerror = () => { db.close(); rej(t.error); };
    t.onabort = () => { db.close(); rej(t.error); };
  });
}

const notify = () => { if (typeof window !== "undefined") window.dispatchEvent(new Event("rp:queue")); };

export const captureDb = {
  async put(c: Capture) { await tx("readwrite", (s) => s.put(c)); notify(); },
  async get(id: string) { return tx<Capture | undefined>("readonly", (s) => s.get(id)); },
  async all(): Promise<Capture[]> {
    const rows = await tx<Capture[]>("readonly", (s) => s.getAll());
    return rows.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  },
  async update(id: string, patch: Partial<Capture>) {
    const cur = await this.get(id);
    if (!cur) return;
    await this.put({ ...cur, ...patch });
  },
  async remove(id: string) { await tx("readwrite", (s) => s.delete(id)); notify(); },
};
