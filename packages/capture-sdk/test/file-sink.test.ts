import { chmod, lstat, mkdtemp, readFile, readdir, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { createJsonFileSink } from "../src/index.js";
import type { DiagnosticEvent } from "../src/index.js";

const directories: string[] = [];
const event = (number = 1): DiagnosticEvent => ({
  schema_version: "1.0", event_id: `00000000-0000-4000-8000-${number.toString().padStart(12, "0")}`,
  timestamp: "2026-10-23T00:00:00.000Z", duration_ms: 2,
  request: { method: "GET", api: "rest", resource: "documents", filters: [{ column: "owner_id", operator: "eq" }] },
  response: { status: 200, row_count: null, error_kind: null },
  context: { authorization_present: true, apikey_present: false },
});
const temporary = async (): Promise<string> => {
  const directory = await mkdtemp(join(tmpdir(), "rls-doctor-capture-"));
  directories.push(directory);
  return directory;
};
afterEach(async () => { await Promise.all(directories.splice(0).map((directory) => rm(directory, { recursive: true, force: true }))); });

describe("bounded local JSON sink", () => {
  it("writes schema fields only to exclusive private files and does not mutate its event", async () => {
    const directory = join(await temporary(), "captures");
    const original = { ...event(), body: "DO_NOT_WRITE_RAW_BODY", token: "DO_NOT_WRITE_TOKEN" };
    await createJsonFileSink({ directory })(original);
    const paths = await readdir(directory);
    expect(paths).toEqual([`${original.event_id}.json`]);
    const output = await readFile(join(directory, paths[0] ?? "missing"), "utf8");
    expect(JSON.parse(output)).toEqual(event());
    expect(output).not.toContain("DO_NOT_WRITE");
    expect(original.body).toBe("DO_NOT_WRITE_RAW_BODY");
    if (process.platform !== "win32") {
      expect((await lstat(directory)).mode & 0o777).toBe(0o700);
      expect((await lstat(join(directory, paths[0] ?? "missing"))).mode & 0o777).toBe(0o600);
    }
  });

  it("bounds queued calls even before the first write completes", async () => {
    const directory = join(await temporary(), "captures");
    const sink = createJsonFileSink({ directory, maxEvents: 2 });
    const writes = Array.from({ length: 5 }, (_, index) => Promise.resolve(sink(event(index + 1))));
    const results = await Promise.allSettled(writes);
    expect(results.filter((result) => result.status === "fulfilled")).toHaveLength(2);
    expect(results.filter((result) => result.status === "rejected")).toHaveLength(3);
    expect(await readdir(directory)).toHaveLength(2);
  });

  it("counts existing files and bytes toward the configured directory bounds", async () => {
    const directory = await temporary();
    await writeFile(join(directory, "existing.json"), "{}", { mode: 0o600 });
    await expect(createJsonFileSink({ directory, maxEvents: 1 })(event())).rejects.toThrow("safety limits");
    await expect(createJsonFileSink({ directory, maxBytes: 2 })(event())).rejects.toThrow("limit reached");
    expect(await readdir(directory)).toEqual(["existing.json"]);
  });

  it("refuses to overwrite an existing event file and can write another event afterward", async () => {
    const directory = await temporary();
    const path = join(directory, `${event().event_id}.json`);
    await writeFile(path, "original contents", { mode: 0o600 });
    const sink = createJsonFileSink({ directory });
    await expect(sink(event())).rejects.toThrow("safety limits");
    await sink(event(2));
    expect(await readFile(path, "utf8")).toBe("original contents");
    expect(await readdir(directory)).toHaveLength(2);
  });

  it("refuses event-file symlinks and directory junctions without modifying their target", async () => {
    const directory = await temporary();
    const target = join(directory, "target.txt");
    await writeFile(target, "unchanged", { mode: 0o600 });
    const captures = join(directory, "captures");
    const actualDirectory = join(directory, "actual");
    // Directory junctions work on standard Windows installations without developer mode.
    await createJsonFileSink({ directory: actualDirectory })(event(3));
    await symlink(actualDirectory, captures, process.platform === "win32" ? "junction" : "dir");
    await expect(createJsonFileSink({ directory: captures })(event())).rejects.toThrow("safety limits");
    expect(await readdir(actualDirectory)).toHaveLength(1);
    expect(await readFile(target, "utf8")).toBe("unchanged");
    // File symlinks may require developer privileges on Windows; junction rejection is checked above.
    if (process.platform !== "win32") {
      const fileDirectory = join(directory, "files");
      await createJsonFileSink({ directory: fileDirectory })(event(3));
      await symlink(target, join(fileDirectory, `${event().event_id}.json`));
      await expect(createJsonFileSink({ directory: fileDirectory })(event())).rejects.toThrow("safety limits");
      expect(await readFile(target, "utf8")).toBe("unchanged");
    }
  });

  it("refuses a world-readable sink directory on POSIX", async () => {
    if (process.platform === "win32") return;
    const directory = await temporary();
    await chmod(directory, 0o755);
    await expect(createJsonFileSink({ directory })(event())).rejects.toThrow("safety limits");
  });

  it("rejects invalid metadata and returns sanitized errors for sensitive directory names", async () => {
    const root = await temporary();
    const directory = join(root, "PRIVATE_DIRECTORY_VALUE");
    await writeFile(directory, "not a directory");
    let errorMessage = "";
    try { await createJsonFileSink({ directory })(event()); }
    catch (error: unknown) { errorMessage = error instanceof Error ? error.message : ""; }
    expect(errorMessage).toBe("Capture sink could not persist the event within its safety limits.");
    expect(errorMessage).not.toContain("PRIVATE_DIRECTORY_VALUE");
    const invalid = { ...event(), event_id: "../raw-secret" };
    await expect(createJsonFileSink({ directory: join(root, "safe") })(invalid)).rejects.toThrow("schema v1");
    await expect(createJsonFileSink({ directory: join(root, "safe") })({ ...event(), request: { ...event().request, resource: "raw.secret" } })).rejects.toThrow("schema v1");
  });

  it.each(["2026-02-30T00:00:00.000Z", "2026-13-01T00:00:00.000Z", "2026-10-23T25:00:00.000Z"])("rejects impossible caller-built date %s", async (timestamp) => {
    const directory = join(await temporary(), "captures");
    await expect(createJsonFileSink({ directory })({ ...event(), timestamp })).rejects.toThrow("schema v1");
  });
});
