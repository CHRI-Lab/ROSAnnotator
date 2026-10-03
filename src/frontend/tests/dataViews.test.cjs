const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');

// Load the real view classes/registry, replacing only the media/UI leaves.
const root = path.resolve(__dirname, '../src/components/FrontEndWorkspace');
const cache = new Map();
function load(name) {
  const filename = ['.tsx', '.ts'].map(ext => path.join(root, name + ext)).find(fs.existsSync);
  if (cache.has(filename)) return cache.get(filename);
  const module = { exports: {} };
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText;
  vm.runInNewContext(source, {
    module, exports: module.exports,
    require(dependency) {
      if (dependency.startsWith('./')) return load(dependency.slice(2));
      if (dependency === 'react/jsx-runtime') return require(dependency);
      if (dependency === 'react') return { ...React, useRef: value => ({ current: value }) };
      return function Leaf(props) { return React.createElement('div', props); };
    },
  }, { filename });
  cache.set(filename, module.exports);
  return module.exports;
}
const { availableViews } = load('viewRegistry');
const { VideoDataView, TranscriptDataView } = load('dataViews');
const { BaseDataView } = load('BaseDataView');

test('unavailable view reasons remain visible outside the disabled menu', () => {
  const Selector = load('DataViewSelector').default;
  const tree = Selector({ panelCount: 1, threePanelLargeSide: 'left', selections: ['video'],
    views: [
      { id: 'video', label: 'Video', available: false, status: 'failed', reason: 'Image decoding failed' },
      { id: 'transcript', label: 'Transcript', available: false, status: 'loading' },
    ], onPanelCountChange() {}, onThreePanelLargeSideChange() {}, onSelectionChange() {} });
  const statuses = [];
  function visit(node) {
    if (Array.isArray(node)) return node.forEach(visit);
    if (!node?.props) return;
    if (node.props.role === 'status') statuses.push(node);
    visit(node.props.children);
  }
  function text(node) {
    if (Array.isArray(node)) return node.map(text).join('');
    if (node?.props) return text(node.props.children);
    return typeof node === 'string' ? node : '';
  }
  visit(tree);
  assert.equal(statuses.length, 1);
  assert.match(text(statuses[0]), /Video unavailable/);
  assert.match(text(statuses[0]), /Image decoding failed/);
});

function context() {
  return { videoPath: 'sample.bag/output.mp4', transcript: 'Hello', played: 12,
    isPlaying: false, onProgress() {}, onPlay() {}, onPause() {}, onSeek() {},
    onDurationChange() {}, playerRef() {} };
}

test('unavailable options expose a hover reason but cannot be selected', () => {
  const changes = [];
  const tree = load('DataViewSelector').default({ panelCount: 1, selections: ['video'],
    views: [
      { id: 'video', label: 'Video', available: true, status: 'ready' },
      { id: 'audio', label: 'Audio', available: false, status: 'unavailable', reason: 'No audio messages' },
      { id: 'wrench', label: 'Wrench', available: false, status: 'unavailable' },
    ], onSelectionChange: (...args) => changes.push(args) });
  const nodes = [];
  function visit(node) {
    if (Array.isArray(node)) return node.forEach(visit);
    if (!node?.props) return;
    nodes.push(node); visit(node.props.children);
  }
  visit(tree);
  const option = nodes.find(node => node.props.value === 'audio');
  assert.equal(option.props.disabled, true);
  assert.equal(option.props.sx['&.Mui-disabled'].pointerEvents, 'auto');
  assert.equal(option.props.children.props.title, 'Data type not available');
  assert.equal(nodes.find(node => node.props.value === 'wrench').props.children.props.title, 'Data type not available');
  const select = nodes.find(node => node.props.label === 'Panel 1');
  select.props.onChange({ target: { value: 'audio' } });
  assert.equal(changes.length, 0);
  select.props.onChange({ target: { value: 'video' } });
  assert.deepEqual(changes, [[0, 'video']]);
});

test('registry retains Cassie IDs, labels and renderable component contract', () => {
  assert.deepEqual(Array.from(availableViews, view => view.id), [
    'video', 'transcript', 'annotations', 'statistics-annotations', 'statistics-tiers', 'audio', 'waveform', 'wrench',
  ]);
  for (const view of availableViews) {
    assert.equal(typeof view.label, 'string');
    assert.equal(typeof view.component, 'function');
    assert.ok(React.isValidElement(view.component(context())));
  }
});

test('inherited adapter preserves component identity between calls', () => {
  const view = new VideoDataView();
  assert.ok(view instanceof BaseDataView);
  assert.equal(view.toDefinition().component, view.toDefinition().component);
});

test('video forwards playback callbacks and uses Cassie public media URL', () => {
  const state = context();
  let progress;
  state.onProgress = time => { progress = time; };
  const content = new VideoDataView().render(state);
  const player = content.type(content.props);
  assert.equal(player.props.url, '/processed/sample.bag/output.mp4');
  assert.equal(player.props.playing, false);
  assert.equal(player.props.height, '100%');
  assert.equal(player.props.config.file.attributes.style.objectFit, 'contain');
  assert.equal(player.props.onPause, state.onPause);
  assert.equal(player.props.onPlay, state.onPlay);
  assert.equal(player.props.onDuration, state.onDurationChange);
  assert.equal(player.ref, state.playerRef);
  player.props.onProgress({ playedSeconds: 13.5 });
  assert.equal(progress, 13.5);
});

test('repeated canplay events do not seek the video back or re-enter initialization', () => {
  const state = context();
  const content = new VideoDataView().render(state);
  const player = content.type(content.props);
  const seeks = [];
  const instance = { seekTo(time, unit) {
    seeks.push([time, unit]);
    assert.ok(seeks.length <= 1, 'ready must not start another seek');
    player.props.onReady(instance);
  } };
  player.props.onReady(instance);
  player.props.onReady(instance);
  assert.deepEqual(seeks, [[12, 'seconds']]);
});

test('a new video at zero starts without an unnecessary seek', () => {
  const content = new VideoDataView().render({ ...context(), played: 0 });
  content.type(content.props).props.onReady({ seekTo() { assert.fail('unexpected seek'); } });
});

test('transcript keeps media-local seconds and shared seek callback', () => {
  const state = context();
  const content = new TranscriptDataView().render(state);
  const transcript = content.type(content.props);
  assert.equal(transcript.props.LRC, 'Hello');
  assert.equal(transcript.props.played, 12);
  assert.equal(transcript.props.isPlaying, false);
  assert.equal(transcript.props.setPlayed, state.onSeek);
});


test('backend availability disables missing or invalid views with reasons', () => {
  const { viewsWithAvailability } = load('viewRegistry');
  const states = viewsWithAvailability({
    video: { status: 'ready', available: true, processed_data: { path: 'video.mp4' } },
    transcript: { status: 'failed', available: false, processed_data: null, reason: 'No speech' },
    audio: { status: 'ready', available: true, processed_data: null },
  });
  assert.equal(states.find(v => v.id === 'video').available, true);
  assert.equal(states.find(v => v.id === 'audio').available, false);
  assert.equal(states.find(v => v.id === 'transcript').reason, 'No speech');
  assert.equal(states.find(v => v.id === 'waveform').available, false);
});
