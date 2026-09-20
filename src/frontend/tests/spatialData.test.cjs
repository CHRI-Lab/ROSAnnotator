const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const ts = require('typescript');
const mod = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.resolve(__dirname, '../src/components/FrontEndWorkspace/spatialData.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, { module: mod, exports: mod.exports });
const { nearestSample, boundedSamples, motionBounds } = mod.exports;
const samples = [1, 2, 3].map(seconds => ({ seconds, bag_seconds: seconds+10 }));
test('shared time selects exact or nearest sample with deterministic tie and tolerance', () => {
  assert.equal(nearestSample(samples, 2, 0), samples[1]);
  assert.equal(nearestSample(samples, 1.5, 0.5), samples[0]);
  assert.equal(nearestSample(samples, 1.8, 0.5), samples[1]);
  assert.equal(nearestSample(samples, 1.5, 0.1), undefined);
});
test('entities are hidden before and after their sample lifetime', () => {
  for (const t of [0.9, 3.1]) assert.equal(nearestSample(samples, t, Infinity), undefined);
  assert.equal(nearestSample([], 1, 1), undefined);
});
test('offset entities independently follow one shared playback time', () => {
  const shifted = samples.map(s => ({ ...s, seconds: s.seconds+0.2 }));
  assert.equal(nearestSample(samples, 2.1, 0.5).seconds, 2);
  assert.equal(nearestSample(shifted, 2.1, 0.5).seconds, 2.2);
});
test('bounded rendering preserves endpoints', () => {
  const result = boundedSamples(Array.from({ length: 10000 }, (_, i) => i), 250);
  assert.equal(result.length, 250); assert.equal(result[0], 0); assert.equal(result.at(-1), 9999);
});
test('motion axes use equal metric scale even for vertical or stationary paths', () => {
  for (const points of [[[3, 3, 0]], [[0, -5, 0], [0, 8, 0]]]) {
    const [xmin, xmax, ymin, ymax] = motionBounds([{ samples: points.map(position => ({ position })) }]);
    assert.ok(xmax > xmin); assert.ok(ymax > ymin);
    assert.ok(Math.abs((xmax-xmin)-(ymax-ymin)) < 1e-9);
  }
});
