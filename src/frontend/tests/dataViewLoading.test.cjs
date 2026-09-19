const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function load(fetch) {
  const module = { exports: {} };
  const source = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/api/dataViews.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  vm.runInNewContext(source, { module, exports: module.exports, fetch });
  return module.exports.loadDataViews;
}

const response = payload => ({ ok: true, json: async () => payload });
const view = (id, ready = true) => ({ view_id: id, status: ready ? 'ready' : 'failed', available: ready,
  processed_data: ready ? { value: id } : null, reason: ready ? null : 'Decoder failed', warnings: [] });

test('video is published while speech is pending; speech failure does not erase video', async () => {
  let finishSpeech;
  const speech = new Promise(resolve => { finishSpeech = resolve; });
  const seen = [];
  const loader = load(async (url, request) => {
    if (url.endsWith('/views/')) return response({ views: [{ view_id: 'video' }, { view_id: 'transcript' }] });
    const id = JSON.parse(request.body).view_ids[0];
    if (id === 'transcript') return speech;
    return response({ video_path: 'clip.mp4', views: { video: view('video') }, annotation_data: [] });
  });
  let firstProgress;
  const progressed = new Promise(resolve => { firstProgress = resolve; });
  const pending = loader('/process', {}, state => { seen.push(state); firstProgress(); });
  await progressed;
  assert.equal(seen[0].views.video.status, 'ready');
  assert.equal(seen[0].views.transcript.status, 'loading');
  finishSpeech(response({ video_path: '', views: { transcript: view('transcript', false) } }));
  const result = await pending;
  assert.equal(result.video_path, 'clip.mp4');
  assert.equal(result.views.video.available, true);
  assert.equal(result.views.transcript.reason, 'Decoder failed');
});

test('network failure is scoped to one view and unknown registry entries load generically', async () => {
  const loader = load(async (url, request) => {
    if (url.endsWith('/views/')) return response({ views: [{ view_id: 'new-sensor' }, { view_id: 'video' }] });
    const id = JSON.parse(request.body).view_ids[0];
    if (id === 'video') throw new Error('offline');
    return response({ views: { [id]: view(id) } });
  });
  const result = await loader('/process', {});
  assert.equal(result.views['new-sensor'].available, true);
  assert.equal(result.views.video.status, 'failed');
  assert.match(result.views.video.reason, /offline/);
});

test('zero usable views retain individual reasons for the global error dialog', async () => {
  const loader = load(async (url) => url.endsWith('/views/')
    ? response({ views: [{ view_id: 'audio' }] })
    : response({ views: { audio: view('audio', false) } }));
  const result = await loader('/process', {});
  assert.equal(Object.values(result.views).some(v => v.available), false);
  assert.equal(result.views.audio.reason, 'Decoder failed');
});
