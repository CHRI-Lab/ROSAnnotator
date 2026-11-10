const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadHelpers() {
  const module = { exports: {} };
  const filename = path.join(__dirname, '../src/components/Chatbox/timeRange.ts');
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  vm.runInNewContext(source, { module, exports: module.exports });
  return module.exports;
}

test('accepts a chunk-relative time range', () => {
  const { validateChunkTimeRange } = loadHelpers();
  const result = validateChunkTimeRange('00:10', '00:25', 60);
  assert.deepEqual(JSON.parse(JSON.stringify(result.range)), { start: 10, end: 25 });
  assert.equal(result.error, '');
});

test('rejects malformed, reversed, empty, and out-of-chunk ranges', () => {
  const { validateChunkTimeRange } = loadHelpers();
  for (const [start, end] of [
    ['bad', '00:20'],
    ['00:20', '00:10'],
    ['00:10', '00:10'],
    ['00:00', '01:01'],
  ]) {
    const result = validateChunkTimeRange(start, end, 60);
    assert.equal(result.range, null);
    assert.ok(result.error);
  }
});
