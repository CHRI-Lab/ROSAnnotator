// Isolated hook tests with persistent refs and explicit renders; timers/effects
// are excluded so pending network requests can be advanced deterministically.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function harness() {
  const refs = [];
  let cursor = 0;
  const writes = [];
  const module = { exports: {} };
  const filename = path.join(__dirname, '../src/components/Autosave/useAutosave.ts');
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  vm.runInNewContext(source, {
    module, exports: module.exports, console: { warn() {} },
    require(name) {
      if (name === 'react') return {
        useRef(value) { return refs[cursor++] ||= { current: value }; },
        useCallback(callback) { return callback; },
        useEffect() {},
      };
      return {
        buildAutosaveRequestBody: (options) => ({
          ...options.scope, axes: options.axes, saved_at: 'now',
        }),
        postAutosave: (body) => new Promise((resolve, reject) => {
          writes.push({ body, resolve, reject });
        }),
      };
    },
  });
  return {
    writes,
    render(axes) {
      cursor = 0;
      return module.exports.useAutosave({
        enabled: true, bagFileName: 'test.bag', hasUnsavedEdits: true, axes,
        scope: { manifest_id: 'manifest', chunk_index: 2 },
      });
    },
  };
}

test('navigation flush waits for a pending save, then saves newer edits', async () => {
  const h = harness();
  let hook = h.render([{ id: 1 }]);
  const background = hook.flush();
  hook = h.render([{ id: 1 }, { id: 2 }]);
  let navigated = false;
  const navigation = hook.flush().then(() => { navigated = true; });
  assert.equal(h.writes.length, 1);
  assert.equal(navigated, false);
  h.writes[0].resolve();
  await background;
  assert.equal(h.writes.length, 2);
  assert.equal(navigated, false);
  assert.equal(h.writes[1].body.axes.length, 2);
  assert.equal(h.writes[1].body.chunk_index, 2);
  h.writes[1].resolve();
  await navigation;
  assert.equal(navigated, true);
});

test('failed save rejects navigation and permits retry', async () => {
  const h = harness();
  const hook = h.render([{ id: 1 }]);
  const first = hook.flush();
  h.writes[0].reject(new Error('offline'));
  await assert.rejects(first, /offline/);
  const retry = hook.flush();
  assert.equal(h.writes.length, 2);
  h.writes[1].resolve();
  await retry;
});

test('a failed pending background request also rejects the waiting flush', async () => {
  const h = harness();
  const hook = h.render([{ id: 1 }]);
  const background = hook.flush();
  const navigation = hook.flush();
  h.writes[0].reject(new Error('offline'));
  await Promise.all([
    assert.rejects(background, /offline/), assert.rejects(navigation, /offline/),
  ]);
});

test('concurrent flushes serialize and do not rewrite unchanged state', async () => {
  const h = harness();
  const hook = h.render([]);
  const first = hook.flush();
  const second = hook.flush();
  h.writes[0].resolve();
  await Promise.all([first, second]);
  await hook.flush();
  assert.equal(h.writes.length, 1);
});
