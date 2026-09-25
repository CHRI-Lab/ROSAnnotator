// Zero-dependency frontend contract tests for the conversation lifecycle.
// These inspect the real TSX wiring because this repository does not install a
// browser/component-test runtime. Stateful endpoint behavior is exercised by
// the companion Django acceptance suite.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const readSource = (relativePath) => fs.readFileSync(
  path.join(__dirname, relativePath),
  'utf8',
);

const panelSource = readSource(
  '../src/components/RightAssistantPanel/RightAssistantPanel.tsx',
);
const annotatorSource = readSource('../src/pages/Annotator/Annotator.tsx');
const chatboxSource = readSource('../src/components/Chatbox/Chatbox.tsx');
const mainPageSource = readSource('../src/pages/Main/MainPage.tsx');

function between(source, startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start + startMarker.length);
  assert.notEqual(start, -1, `Missing start marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing end marker: ${endMarker}`);
  return source.slice(start, end);
}

test('clear-history control is available and opens a confirmation prompt', () => {
  assert.match(panelSource, /aria-label="Clear conversation history"/);
  assert.match(panelSource, /onClick=\{\(\) => setConfirmClear\(true\)\}/);
  assert.match(panelSource, /<Dialog open=\{confirmClear\}/);
  assert.match(panelSource, /<DialogTitle>Clear conversation history\?<\/DialogTitle>/);
  assert.match(panelSource, /backend history \(not the saved AI records\)/);
});

test('cancel closes the clear prompt without invoking the clear callback', () => {
  const actions = between(panelSource, '<DialogActions>', '</DialogActions>');
  const cancelButton = between(actions, '<Button disabled={clearing}', '</Button>');

  assert.match(cancelButton, /setConfirmClear\(false\)/);
  assert.doesNotMatch(cancelButton, /clearConversation|onClearConversation/);
  assert.match(actions, /onClick=\{clearConversation\}/);
});

test('confirmed clear succeeds in the backend before the chat is remounted', () => {
  const clearHandler = between(
    annotatorSource,
    'const handleClearConversation = async () => {',
    'useEffect(() => {',
  );
  const requestIndex = clearHandler.indexOf('/api/gpt_chat/clear/');
  const responseCheckIndex = clearHandler.indexOf('if (!response.ok)');
  const remountIndex = clearHandler.indexOf('setConversationKey((key) => key + 1)');

  assert.ok(requestIndex >= 0);
  assert.ok(responseCheckIndex > requestIndex);
  assert.ok(remountIndex > responseCheckIndex);
  assert.match(
    annotatorSource,
    /<Chatbox key=\{conversationKey\} onSendMessage=\{handleSendMessageToGPT\}/,
  );
});

test('a refreshed or remounted chat starts without cleared messages', () => {
  assert.match(chatboxSource, /useState<ChatMessage\[]>\(\[]\)/);
  assert.doesNotMatch(chatboxSource, /localStorage\.(?:getItem|setItem)\([^\n]*chatHistory/);
});

test('chunk selection warns before switching and cancel keeps the current chunk', () => {
  assert.match(
    annotatorSource,
    /Your annotations will be saved and preserved, but the AI conversation history will be lost/,
  );
  assert.match(annotatorSource, /setPendingChunkIndex\(index\)/);
  assert.match(
    annotatorSource,
    /<Button disabled=\{confirmingChunkSwitch\} onClick=\{\(\) => setPendingChunkIndex\(null\)\}>Cancel<\/Button>/,
  );
});

test('confirmed chunk switch clears conversation before requesting navigation', () => {
  const confirmHandler = between(
    annotatorSource,
    'const confirmChunkSelection = async () => {',
    'return (',
  );
  const clearIndex = confirmHandler.indexOf('await handleClearConversation()');
  const navigationIndex = confirmHandler.indexOf('await onChunkChange(targetIndex)');

  assert.ok(clearIndex >= 0);
  assert.ok(navigationIndex > clearIndex);
  assert.match(confirmHandler, /catch \{/);
  assert.match(confirmHandler, /The chunk was not changed/);
});

test('chunk navigation saves current annotations and restores the target chunk', () => {
  const chunkChangeHandler = between(
    mainPageSource,
    'const handleChunkChange = async (targetIndex: number) => {',
    'if (loading) {',
  );
  const flushIndex = chunkChangeHandler.indexOf('await autosaveFlush.current()');
  const processIndex = chunkChangeHandler.indexOf(
    'await loadDataViews(',
  );
  const restoreIndex = chunkChangeHandler.indexOf(
    'await restoreChunk(rosBagFile!, manifestId, targetIndex)',
  );
  const activateIndex = chunkChangeHandler.indexOf(
    'setCurrentChunkIndex(targetIndex)',
  );

  assert.ok(flushIndex >= 0);
  assert.ok(processIndex > flushIndex);
  assert.ok(restoreIndex > processIndex);
  assert.ok(activateIndex > restoreIndex);
  assert.match(chunkChangeHandler, /setRestoredAxes\(recoveredAxes\)/);
});

test('completed AI replies directly invoke the dedicated record endpoint', () => {
  const persistenceHandler = between(
    annotatorSource,
    'const persistCompletedAIRecord = async (',
    'const handleAxesUpdate',
  );
  const sendHandler = between(
    annotatorSource,
    'const handleSendMessageToGPT = (',
    'const handleSaveBooklist',
  );

  assert.match(persistenceHandler, /\/api\/ai_records\/complete\//);
  assert.match(persistenceHandler, /ai_record: record/);
  assert.match(persistenceHandler, /outcome,/);
  assert.match(sendHandler, /await persistCompletedAIRecord\(aiRecord, "replied"\)/);
  assert.match(sendHandler, /await persistCompletedAIRecord\(aiRecord, "applied"\)/);
  assert.match(sendHandler, /await persistCompletedAIRecord\(aiRecord, "rejected"\)/);
  assert.match(sendHandler, /await persistCompletedAIRecord\(aiRecord, "not_applied"\)/);
  assert.doesNotMatch(sendHandler, /handleSaveAnnotations|\/api\/autosave\//);
});

test('failed AI HTTP responses cannot reach completed-record persistence', () => {
  const sendHandler = between(
    annotatorSource,
    'const handleSendMessageToGPT = (',
    'const handleSaveBooklist',
  );
  const failureCheck = sendHandler.indexOf('if (!response.ok)');
  const thrownFailure = sendHandler.indexOf('throw error;', failureCheck);
  const completedStage = sendHandler.indexOf('.then(async (data) =>', thrownFailure);
  const persistence = sendHandler.indexOf('persistCompletedAIRecord', completedStage);
  const errorResult = sendHandler.indexOf('.catch((error) =>', persistence);

  assert.ok(failureCheck >= 0);
  assert.ok(thrownFailure > failureCheck);
  assert.ok(completedStage > thrownFailure);
  assert.ok(persistence > completedStage);
  assert.ok(errorResult > persistence);
});
