import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { createServer } from 'vite';

test('serves chunks created after startup with byte ranges and real 404s', async () => {
  const root = await mkdtemp(resolve(tmpdir(), 'processed-media-'));
  let server;
  try {
    await mkdir(resolve(root, 'public/processed'), { recursive: true });
    server = await createServer({ configFile: resolve('vite.config.ts'), root,
      server: { host: '127.0.0.1', port: 0, open: false }, logLevel: 'silent' });
    await server.listen();
    const base = `http://127.0.0.1:${server.httpServer.address().port}/processed`;
    for (const chunk of ['0000', '0001']) {
      const directory = resolve(root, 'public/processed/chunks', chunk);
      await mkdir(directory, { recursive: true });
      const bytes = Buffer.from(`video bytes for ${chunk}`);
      await writeFile(resolve(directory, 'output.mp4'), bytes);
      const response = await fetch(`${base}/chunks/${chunk}/output.mp4`,
        { headers: { Range: 'bytes=0-3' } });
      assert.equal(response.status, 206);
      assert.match(response.headers.get('content-type'), /video\/mp4/);
      assert.equal(response.headers.get('content-range'), `bytes 0-3/${bytes.length}`);
      assert.equal(await response.text(), 'vide');
    }
    const missing = await fetch(`${base}/missing.mp4`);
    assert.equal(missing.status, 404);
    assert.equal(await missing.text(), 'Processed media not found');
  } finally {
    await server?.close();
    await rm(root, { recursive: true, force: true });
  }
});
