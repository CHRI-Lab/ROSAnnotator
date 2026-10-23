const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function load(file, globals = {}, imports = () => { throw new Error('Unexpected import'); }) {
  const module = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src', file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  vm.runInNewContext(code, { module, exports: module.exports, require: imports, Error, ...globals });
  return module.exports;
}
const draftHelpers = load('components/Transcript/transcriptDraft.ts');
const { createTranscriptDraft, parseTranscriptDraft, renameTranscriptSpeaker } = draftHelpers;
const { applySavedTranscript } = load('api/transcripts.ts');
const convert = load('components/Timeline/transcriptAnnotations.ts').convertTranscriptToAnnotations;
const plain = value => JSON.parse(JSON.stringify(value));
const segment = { speaker_label: 'SPEAKER_00', text: 'Original', start_time: 1.25, end_time: 2.5 };

test('edited speaker, text and precise times are used when creating annotations', () => {
  const draft = createTranscriptDraft([segment]);
  draft[0] = { ...draft[0], speaker_label: 'Alice', text: 'Corrected', start_time: '3.125', end_time: '4.875' };
  const parsed = parseTranscriptDraft(draft, 30);
  const annotations = convert([], parsed, 30, 1);
  assert.equal(annotations.axes[0].axisName, 'Alice');
  assert.deepEqual(plain(annotations.axes[0].blocks), [{ start: 3.125, end: 4.875, text: 'Corrected' }]);
  assert.equal(segment.text, 'Original');
});

test('bulk rename affects all matching segments without modifying other speakers or source data', () => {
  const draft = createTranscriptDraft([segment, { ...segment, start_time: 4 }, { ...segment, speaker_label: 'Other' }]);
  const renamed = renameTranscriptSpeaker(draft, 'SPEAKER_00', ' Alice ');
  assert.deepEqual(plain(renamed.map(row => row.speaker_label)), ['Alice', 'Alice', 'Other']);
  assert.equal(draft[0].speaker_label, 'SPEAKER_00');
});

test('invalid or empty time fields and blank speaker labels cannot be saved', () => {
  for (const patch of [{ start_time: '' }, { start_time: '-1' }, { end_time: '31' }, { end_time: '1' }, { end_time: 'NaN' }, { end_time: 'Infinity' }, { speaker_label: ' ' }]) {
    const draft = createTranscriptDraft([segment]);
    assert.throws(() => parseTranscriptDraft([{ ...draft[0], ...patch }], 30));
  }
  assert.deepEqual(plain(parseTranscriptDraft([], 30)), []);
});

const ref = { scope: 'chunks', key: 'a'.repeat(64) };
function view(revision = 0, editRef = ref) {
  return { view_id: 'transcript', available: true, status: 'ready', processed_data: { edit_ref: editRef, revision, transcript: 'Original', speaker_data: [segment] } };
}
function payload() {
  return { audio_transcript: 'Original', speaker_data: [segment], views: { transcript: view() }, annotation_data: [{ axisName: 'Saved' }], ai_records: [] };
}
function saved() {
  const segments = [{ ...segment, text: 'Corrected', speaker_label: 'Alice' }];
  return { audio_transcript: 'Corrected', speaker_data: segments, view: { ...view(1), processed_data: { ...view(1).processed_data, transcript: 'Corrected', speaker_data: segments } } };
}

test('saved corrections update display, conversion and AI view data together without replacing annotations', () => {
  const original = payload(), edit = saved();
  const updated = applySavedTranscript(original, edit);
  assert.equal(updated.audio_transcript, 'Corrected');
  assert.equal(updated.speaker_data, edit.speaker_data);
  assert.equal(updated.views.transcript.processed_data.transcript, 'Corrected');
  assert.equal(updated.annotation_data, original.annotation_data);
  assert.equal(updated.ai_records, original.ai_records);
  assert.equal(original.audio_transcript, 'Original');
});

test('old saved state cannot override a different chunk, scope or newer server revision', () => {
  for (const otherView of [view(0, { ...ref, key: 'b'.repeat(64) }), view(0, { ...ref, scope: 'whole' }), view(2)]) {
    const data = { ...payload(), views: { transcript: otherView } };
    assert.equal(applySavedTranscript(data, saved()), data);
  }
});

test('clearing a transcript propagates empty text and segments', () => {
  const edit = saved();
  edit.audio_transcript = '';
  edit.speaker_data = [];
  const updated = applySavedTranscript(payload(), edit);
  assert.equal(updated.audio_transcript, '');
  assert.equal(updated.speaker_data.length, 0);
});

test('save API sends revision and edited segments and surfaces conflicts', async () => {
  let request;
  const { saveTranscript } = load('api/transcripts.ts', { fetch: async (url, options) => {
    request = { url, options };
    return { ok: false, json: async () => ({ error: 'Transcript changed elsewhere' }) };
  } });
  await assert.rejects(saveTranscript(ref, 2, [segment]), /changed elsewhere/);
  assert.equal(request.options.method, 'PUT');
  assert.match(request.url, /\/api\/transcripts\/chunks\/a{64}\/$/);
  assert.deepEqual(JSON.parse(request.options.body), { revision: 2, speaker_data: [segment] });
});

function editorHarness(saveAction) {
  const state = [];
  let cursor = 0, closed = false;
  const Editor = load('components/Transcript/TranscriptEditor.tsx', {}, name => {
    if (name === './transcriptDraft') return draftHelpers;
    if (name === 'react') return {
      useEffect() {},
      useState(initial) {
        const index = cursor++;
        if (!(index in state)) state[index] = typeof initial === 'function' ? initial() : initial;
        return [state[index], value => { state[index] = typeof value === 'function' ? value(state[index]) : value; }];
      },
    };
    if (name === 'react/jsx-runtime') return { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
    return new Proxy({}, { get: (_, key) => key });
  }).default;
  function nodes(node) {
    if (!node || typeof node !== 'object') return [];
    if (Array.isArray(node)) return node.flatMap(nodes);
    return [node, ...nodes(node.props?.children)];
  }
  return {
    closed: () => closed,
    render() {
      cursor = 0;
      return nodes(Editor({ segments: [segment], duration: 30, chunked: true, onSave: saveAction, onClose: () => { closed = true; } }));
    },
  };
}

test('save failure preserves the editor draft for retry', async () => {
  const h = editorHarness(async () => { throw new Error('Disk full'); });
  h.render().find(node => node.props?.label === 'Transcript text').props.onChange({ target: { value: 'Keep this edit' } });
  await h.render().find(node => node.props?.children === 'Save transcript').props.onClick();
  assert.equal(h.closed(), false);
  const nodes = h.render();
  assert.equal(nodes.find(node => node.props?.label === 'Transcript text').props.value, 'Keep this edit');
  assert.equal(nodes.find(node => node.type === 'Alert').props.children, 'Disk full');
  assert.equal(nodes.find(node => node.props?.children === 'Save transcript').props.disabled, false);
});

test('successful save sends edited segments and closes; cancel does not save', async () => {
  let sent;
  const h = editorHarness(async segments => { sent = segments; });
  h.render().find(node => node.props?.label === 'Speaker').props.onChange({ target: { value: 'Alice' } });
  await h.render().find(node => node.props?.children === 'Save transcript').props.onClick();
  assert.equal(sent[0].speaker_label, 'Alice');
  assert.equal(h.closed(), true);
  const cancelled = editorHarness(async () => assert.fail('Cancel must not save'));
  cancelled.render().find(node => node.props?.children === 'Cancel').props.onClick();
  assert.equal(cancelled.closed(), true);
});
