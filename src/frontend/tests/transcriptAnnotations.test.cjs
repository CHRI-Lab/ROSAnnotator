const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadModule(file, requireModule = name => { throw new Error(`Unexpected import: ${name}`); }, globals = {}) {
  const module = { exports: {} };
  const source = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src', file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  vm.runInNewContext(source, { module, exports: module.exports, require: requireModule, ...globals });
  return module.exports;
}

const helpers = loadModule('components/Timeline/transcriptAnnotations.ts');
const convert = helpers.convertTranscriptToAnnotations;
const plain = value => JSON.parse(JSON.stringify(value));
const segment = (speaker = 'SPEAKER_00', start = 1, end = 2, text = 'Hello') => ({
  speaker_label: speaker, start_time: start, end_time: end, text,
});

test('conversion groups and sorts transcript blocks by speaker using timeline-local timestamps', () => {
  const segments = [segment('SPEAKER_00', 8, 9, 'Later'), segment('SPEAKER_01'), segment()];
  const before = plain(segments);
  const result = convert([], segments, 30, 4);
  assert.equal(result.addedAxes, 2);
  assert.equal(result.addedBlocks, 3);
  assert.deepEqual(plain(result.axes[0]), {
    id: 4, type: 'Type-in', axisName: 'SPEAKER_00', blocks: [
      { start: 1, end: 2, text: 'Hello' }, { start: 8, end: 9, text: 'Later' },
    ],
  });
  assert.equal(result.axes[1].id, 5);
  assert.equal(result.nextAxisId, 6);
  assert.deepEqual(segments, before);
});

test('conversion preserves existing edits and skips matching names regardless of case, whitespace or type', () => {
  const axes = [{ id: 50, axisName: ' speaker_00 ', type: 'select', blocks: [{ start: 1, end: 2, text: 'Edited' }] }];
  const before = plain(axes);
  const result = convert(axes, [segment(), segment('SPEAKER_00', 5, 6), segment('SPEAKER_01')], 30, 1);
  assert.equal(result.skippedSpeakers, 1);
  assert.equal(result.addedAxes, 1);
  assert.equal(result.axes[0], axes[0]);
  assert.equal(result.axes[1].id, 51);
  assert.deepEqual(axes, before);
});

test('repeated conversion and conversion after saved annotations reload do not duplicate or restore edited blocks', () => {
  const segments = [segment(), segment('SPEAKER_00', 3, 4), segment('SPEAKER_01')];
  const first = convert([], segments, 30, 1);
  const reloaded = plain(first.axes);
  reloaded[0].id = 90;
  reloaded[0].blocks[0].text = 'Manual edit';
  reloaded[0].blocks.pop();
  const second = convert(reloaded, segments, 30, 100);
  assert.equal(second.axes, reloaded);
  assert.equal(second.addedBlocks, 0);
  assert.equal(second.skippedSpeakers, 2);
  assert.equal(second.axes[0].blocks.length, 1);
  assert.equal(second.axes[0].blocks[0].text, 'Manual edit');
});

test('duplicate segments and normalized speaker names do not create duplicate axes or blocks', () => {
  const result = convert([], [segment(), segment(' speaker_00 '), segment('', 5, 6)], 30, 1);
  assert.equal(result.addedAxes, 2);
  assert.equal(result.addedBlocks, 2);
  assert.equal(result.axes[1].axisName, 'Unknown Speaker');
});

test('invalid and out-of-range timestamps are reported without creating empty axes', () => {
  const invalid = [segment('A', -1, 2), segment('B', 5, 4), segment('C', 2, 31), segment('D', NaN, 3), segment('E', 1, Infinity)];
  const result = convert([], [...invalid, segment('F', 0, 30)], 30, 1);
  assert.equal(result.skippedSegments, 5);
  assert.equal(result.addedAxes, 1);
  assert.equal(result.axes[0].axisName, 'F');
  for (const duration of [0, -1, NaN, Infinity]) {
    assert.equal(convert([], [segment()], duration, 1).addedAxes, 0);
  }
});

test('empty transcripts leave annotations unchanged', () => {
  const axes = [{ id: 4, axisName: 'Notes', type: 'Type-in', blocks: [] }];
  assert.equal(convert(axes, [], 30, 5).axes, axes);
});

test('conversion fills an empty speaker axis from another chunk without changing its ID or duplicating the axis', () => {
  const axes = [{ id: 8, axisName: 'SPEAKER_00', type: 'type-in', shortcutKey: 'S', blocks: [] }];
  const result = convert(axes, [segment()], 30, 10);
  assert.equal(result.addedAxes, 0);
  assert.equal(result.reusedAxes, 1);
  assert.equal(result.addedBlocks, 1);
  assert.equal(result.axes.length, 1);
  assert.equal(result.axes[0].id, 8);
  assert.equal(result.axes[0].shortcutKey, 'S');
  assert.equal(axes[0].blocks.length, 0);
  assert.equal(result.axes[0].blocks[0].start, 1);
  assert.equal(convert(result.axes, [segment()], 30, 10).addedBlocks, 0);
});

test('conversion skips an empty codebook axis and ambiguous duplicate names', () => {
  const codebook = [{ id: 1, axisName: 'SPEAKER_00', type: 'select', blocks: [] }];
  const duplicateNames = [...codebook, { id: 2, axisName: 'speaker_00', type: 'Type-in', blocks: [] }];
  for (const axes of [codebook, duplicateNames]) {
    const result = convert(axes, [segment()], 30, 10);
    assert.equal(result.axes, axes);
    assert.equal(result.skippedSpeakers, 1);
    assert.equal(result.addedBlocks, 0);
  }
});

// Render Timeline with hooks and child UI components stubbed: execute its real
// load effects and button handler without an audio service or a browser.
function timelineHarness(speakerData) {
  const effects = [];
  const noop = () => {};
  const context = { axes: [], setAxes(value) { context.axes = typeof value === 'function' ? value(context.axes) : value; } };
  const react = {
    useState: value => [value, noop], useRef: value => ({ current: value }),
    useCallback: callback => callback, useContext: () => context,
    useEffect: callback => effects.push(callback),
  };
  const timeline = loadModule('components/Timeline/Timeline.tsx', name => {
    if (name === './transcriptAnnotations') return helpers;
    if (name === 'react') return { ...react, default: react };
    if (name === 'react/jsx-runtime') return { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
    if (name === '@mui/system') return { styled: () => () => 'styled' };
    if (name.endsWith('/useAutosave')) return { default: () => ({ markSynced: noop, flush: noop }) };
    return new Proxy({}, { get: (_, key) => key });
  }, { window: { addEventListener: noop, removeEventListener: noop }, console: { log: noop } }).default;
  const props = { duration: 30, played: 0, booklist: {}, annotationData: null, speakerData };
  const tree = timeline(props);
  effects.forEach(effect => effect());
  function findButton(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) return node.map(findButton).find(Boolean);
    if (node.type === 'Button' && node.props.children === 'Convert Transcript to Annotations') return node;
    return findButton(node.props?.children);
  }
  return { context, button: () => findButton(timeline(props)), initialButton: findButton(tree) };
}

test('loading a transcript creates no annotations until the conversion button is clicked', () => {
  const h = timelineHarness([segment()]);
  assert.equal(h.context.axes.length, 0);
  assert.equal(h.initialButton.props.disabled, false);
  h.button().props.onClick();
  assert.equal(h.context.axes.length, 1);
  assert.equal(h.context.axes[0].blocks[0].text, 'Hello');
  h.button().props.onClick();
  assert.equal(h.context.axes.length, 1);
  assert.equal(h.context.axes[0].blocks.length, 1);
});

test('conversion button is disabled without transcript segments', () => {
  const h = timelineHarness([]);
  assert.equal(h.initialButton.props.disabled, true);
  h.initialButton.props.onClick();
  assert.equal(h.context.axes.length, 0);
});
