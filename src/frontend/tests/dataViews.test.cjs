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
      return function Leaf(props) { return React.createElement('div', props); };
    },
  }, { filename });
  cache.set(filename, module.exports);
  return module.exports;
}
const { availableViews } = load('viewRegistry');
const { VideoDataView, TranscriptDataView } = load('dataViews');
const { BaseDataView } = load('BaseDataView');

function context() {
  return { videoPath: 'sample.bag/output.mp4', transcript: 'Hello', played: 12,
    isPlaying: false, onProgress() {}, onPlay() {}, onPause() {}, onSeek() {},
    onDurationChange() {}, playerRef() {} };
}

test('registry retains Cassie IDs, labels and renderable component contract', () => {
  assert.deepEqual(Array.from(availableViews, view => view.id), [
    'video', 'transcript', 'annotations', 'statistics-annotations', 'statistics-tiers', 'audio', 'waveform',
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
  assert.equal(player.props.onPause, state.onPause);
  assert.equal(player.props.onPlay, state.onPlay);
  assert.equal(player.props.onDuration, state.onDurationChange);
  assert.equal(player.ref, state.playerRef);
  player.props.onProgress({ playedSeconds: 13.5 });
  assert.equal(progress, 13.5);
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
