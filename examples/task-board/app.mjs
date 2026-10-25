// Runs from an isolated consumer with installed packages, never source SDK imports.
import { createClient } from '@supabase/supabase-js';
import { createCaptureFetch, createJsonFileSink } from '@rls-doctor/capture-sdk';
import { readdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

async function main() {
  const origin = process.env.RLS_DOCTOR_LOCAL_API_URL;
  const key = process.env.RLS_DOCTOR_LOCAL_ANON_KEY;
  const token = process.env.RLS_DOCTOR_TEST_TOKEN;
  if (origin !== 'http://127.0.0.1:56321' || !key ||
      process.env.RLS_DOCTOR_APPROVE_SAMPLE !== '1') throw new Error('SAMPLE_APPROVAL');
  const expected = JSON.parse(process.env.RLS_DOCTOR_SAMPLE_IDS ?? 'null');
  if (!Array.isArray(expected)) throw new Error('SAMPLE_EXPECTATION');
  const directory = './captures';
  const fileSink = createJsonFileSink({directory});
  const writes = [];
  const wrapped = createCaptureFetch(fetch, {
    enabled: true, allowedOrigin: origin, resources: ['tasks'], maxEvents: 1,
    sink: event => { const write = fileSink(event); writes.push(write); return write; },
  });
  const client = createClient(origin, key, {
    db: {schema: 'task_board'},
    global: {fetch: wrapped, headers: token ? {Authorization: `Bearer ${token}`} : {}},
    auth: {persistSession: false, autoRefreshToken: false, detectSessionInUrl: false},
  });
  // A real application reads the response. The SDK must leave it usable.
  const result = await client.from('tasks').select('id,title,state', {count: 'exact'});
  if (result.error || !Array.isArray(result.data)) throw new Error('SAMPLE_QUERY');
  const actual = result.data.map(task => task.id).sort();
  if (JSON.stringify(actual) !== JSON.stringify([...expected].sort()) ||
      result.count !== expected.length) throw new Error('SAMPLE_ISOLATION');
  await new Promise(resolve => setImmediate(resolve));
  await Promise.all(writes);
  wrapped.stop();
  const files = await readdir(directory);
  if (files.length !== 1 || writes.length !== 1) throw new Error('SAMPLE_CAPTURE_COUNT');
  const eventFile = resolve(directory, files[0]);
  const serialized = await readFile(eventFile, 'utf8');
  if ([key, token, 'SYNTHETIC_TASK_'].some(value => value && serialized.includes(value)))
    throw new Error('SAMPLE_CAPTURE_PRIVACY');
  // Neither rows nor raw application errors are printed.
  process.stdout.write(JSON.stringify({result: 'PASS', row_count: actual.length, event_file: eventFile}));
}
main().catch(() => { console.error('Sample app check failed; private details suppressed.'); process.exitCode = 3; });
