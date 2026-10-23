import { lstat, mkdir, open, opendir, unlink } from "node:fs/promises";
import { join, parse, resolve } from "node:path";
import { boundedInteger, eventSnapshot } from "./event.js";
import type { CaptureSink, JsonFileSinkOptions } from "./types.js";

/** Refuse symlink/junction directory components. Dedicated private directory only. */
async function prepareDirectory(directory: string): Promise<void> {
  const root = parse(directory).root;
  let current = root;
  for (const part of directory.slice(root.length).split(/[\\/]/).filter(Boolean)) {
    current = join(current, part);
    try { await mkdir(current, { mode: 0o700 }); }
    catch (error: unknown) {
      if (!(error instanceof Error && "code" in error && error.code === "EEXIST")) throw error;
    }
    const info = await lstat(current);
    if (info.isSymbolicLink() || !info.isDirectory()) throw new Error();
  }
  const info = await lstat(directory);
  if (process.platform !== "win32" && (info.mode & 0o077) !== 0) throw new Error();
}

/**
 * Write exclusive per-event JSON files, never overwriting existing files or symlinks.
 * POSIX modes are 0700/0600; on Windows the operator controls inherited directory ACLs.
 * A hostile process concurrently replacing directory components is outside this boundary.
 */
export function createJsonFileSink(options: JsonFileSinkOptions): CaptureSink {
  if (typeof options.directory !== "string" || options.directory.trim() === "") {
    throw new TypeError("A dedicated capture directory is required.");
  }
  const directory = resolve(options.directory);
  const maxEvents = boundedInteger(options.maxEvents, 100, 10_000);
  const maxBytes = boundedInteger(options.maxBytes, 1_048_576, 104_857_600);
  let reservedEvents = 0;
  let reservedBytes = 0;
  let storedEvents = 0;
  let storedBytes = 0;
  let initialized = false;
  let queue: Promise<void> = Promise.resolve();
  return (event) => {
    let contents: string;
    let filename: string;
    try {
      const snapshot = eventSnapshot(event);
      contents = `${JSON.stringify(snapshot, null, 2)}\n`;
      filename = `${snapshot.event_id}.json`;
    } catch { return Promise.reject(new Error("Capture event does not match schema v1.")); }
    const bytes = Buffer.byteLength(contents, "utf8");
    if (reservedEvents >= maxEvents || reservedBytes + bytes > maxBytes) {
      return Promise.reject(new Error("Capture sink limit reached."));
    }
    reservedEvents += 1;
    reservedBytes += bytes;
    const task = queue.then(async () => {
      try {
        await prepareDirectory(directory);
        if (!initialized) {
          let existingEvents = 0;
          let existingBytes = 0;
          for await (const entry of await opendir(directory)) {
            const info = await lstat(join(directory, entry.name));
            if (!info.isFile() || info.isSymbolicLink()) throw new Error();
            existingEvents += 1;
            existingBytes += info.size;
            if (existingEvents >= maxEvents || existingBytes + bytes > maxBytes) throw new Error();
          }
          storedEvents = existingEvents;
          storedBytes = existingBytes;
          initialized = true;
        }
        if (storedEvents >= maxEvents || storedBytes + bytes > maxBytes) throw new Error();
        const path = join(directory, filename);
        const file = await open(path, "wx", 0o600);
        try { await file.writeFile(contents, "utf8"); }
        catch (error: unknown) {
          await file.close();
          await unlink(path).catch(() => undefined);
          throw error;
        }
        await file.close();
        storedEvents += 1;
        storedBytes += bytes;
      } catch { throw new Error("Capture sink could not persist the event within its safety limits."); }
    });
    queue = task.catch(() => undefined);
    return task;
  };
}
