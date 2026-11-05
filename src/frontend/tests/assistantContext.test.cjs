const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadHelper() {
  const module = { exports: {} };
  const filename = path.join(__dirname, '../src/pages/Annotator/assistantContext.ts');
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  vm.runInNewContext(source, { module, exports: module.exports, require });
  return module.exports;
}

const segments = [
  { speaker_label: 'A', text: 'Before', start_time: 1, end_time: 4 },
  { speaker_label: 'B', text: 'Crosses start', start_time: 8, end_time: 12 },
  { speaker_label: 'A', text: 'Inside\nrange', start_time: 12, end_time: 14 },
  { speaker_label: 'B', text: 'Starts at end', start_time: 15, end_time: 18 },
];

test('transcript request contains only segments overlapping the selected range', () => {
  const { transcriptForTimeRange } = loadHelper();
  const result = transcriptForTimeRange('full transcript', segments, { start: 10, end: 15 });

  assert.match(result, /Crosses start/);
  assert.match(result, /Inside range/);
  assert.doesNotMatch(result, /Before/);
  assert.doesNotMatch(result, /Starts at end/);
  assert.equal(result, (
    '[00:08] Speaker B: Crosses start [00:12]\n'
    + '[00:12] Speaker A: Inside range [00:14]'
  ));
});

test('no selected range preserves the original transcript', () => {
  const { transcriptForTimeRange } = loadHelper();
  assert.equal(transcriptForTimeRange('full transcript', segments), 'full transcript');
});
