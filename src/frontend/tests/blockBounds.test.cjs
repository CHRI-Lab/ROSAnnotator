const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadBoundsHelpers() {
  const module = { exports: {} };
  const filename = path.join(
    __dirname,
    '../src/components/Timeline/blockBounds.ts',
  );
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  vm.runInNewContext(source, { module, exports: module.exports, require });
  return module.exports;
}

test('blocks are clamped to the visible timeline', () => {
  const { clampBlockToDuration } = loadBoundsHelpers();

  assert.deepEqual(
    JSON.parse(JSON.stringify(clampBlockToDuration(
      { start: -2, end: 15, text: 'wide' },
      10,
    ))),
    { start: 0, end: 10, text: 'wide' },
  );
});

test('clamping retains chunk source metadata', () => {
  const { clampBlockToDuration } = loadBoundsHelpers();

  assert.deepEqual(
    JSON.parse(JSON.stringify(clampBlockToDuration({
      start: 0,
      end: 12,
      text: 'cross-chunk',
      sourceStart: 290,
      sourceEnd: 620,
    }, 10))),
    {
      start: 0,
      end: 10,
      text: 'cross-chunk',
      sourceStart: 290,
      sourceEnd: 620,
    },
  );
});
