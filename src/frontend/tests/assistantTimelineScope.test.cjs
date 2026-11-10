// Timeline-scope acceptance tests shared by Local and Remote response handling.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadHelpers() {
  const module = { exports: {} };
  const filename = path.join(
    __dirname,
    '../src/components/Timeline/aiInstruction.ts',
  );
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  vm.runInNewContext(source, {
    module,
    exports: module.exports,
    require(name) {
      throw new Error(`Unexpected runtime import: ${name}`);
    },
  });
  return module.exports;
}

const normalize = (value) => JSON.parse(JSON.stringify(value));

const makeAxes = () => [
  {
    id: 1,
    type: 'Type-in',
    axisName: 'Selected timeline',
    blocks: [],
  },
  {
    id: 2,
    type: 'Type-in',
    axisName: 'Other timeline',
    blocks: [],
  },
];

const addBlock = (axisId, start, end, text) => ({
  action: 'addBlock',
  parameters: { axisId, start, end, text },
});

const instruction = (...steps) => ({ type: 'instruction', steps });

test('one selected timeline accepts and applies a change only to that timeline', () => {
  const { instructionExceedsTimelineScope, applyAIInstruction } = loadHelpers();
  const axes = makeAxes();
  const proposal = instruction(addBlock(1, 1, 2, 'selected change'));
  const scope = { axisIds: [1], allowNew: false };

  assert.equal(instructionExceedsTimelineScope(proposal, scope), false);
  const result = applyAIInstruction(axes, proposal, 60);

  assert.deepEqual(normalize(result[0].blocks), [
    { start: 1, end: 2, text: 'selected change' },
  ]);
  assert.deepEqual(normalize(result[1].blocks), []);
  assert.deepEqual(normalize(axes), makeAxes());
});

test('selected-plus-unselected and unselected-only proposals are anomalies', () => {
  const { instructionExceedsTimelineScope } = loadHelpers();
  const scope = { axisIds: [1], allowNew: false };

  const mixed = instruction(
    addBlock(1, 1, 2, 'selected change'),
    addBlock(2, 3, 4, 'unselected change'),
  );
  const unselectedOnly = instruction(addBlock(2, 3, 4, 'unselected change'));

  assert.equal(instructionExceedsTimelineScope(mixed, scope), true);
  assert.equal(instructionExceedsTimelineScope(unselectedOnly, scope), true);
});

test('apply-all keeps every valid model-proposed timeline change', () => {
  const { applyAIInstruction } = loadHelpers();
  const proposal = instruction(
    addBlock(1, 1, 2, 'selected change'),
    addBlock(2, 3, 4, 'unselected change'),
  );

  const result = applyAIInstruction(makeAxes(), proposal, 60);

  assert.equal(result[0].blocks[0].text, 'selected change');
  assert.equal(result[1].blocks[0].text, 'unselected change');
});

test('apply-selected filters out changes to unselected timelines', () => {
  const { filterInstructionToTimelineScope, applyAIInstruction } = loadHelpers();
  const proposal = instruction(
    addBlock(1, 1, 2, 'selected change'),
    addBlock(2, 3, 4, 'unselected change'),
  );
  const scope = { axisIds: [1], allowNew: false };

  const filtered = filterInstructionToTimelineScope(proposal, scope);
  const result = applyAIInstruction(makeAxes(), filtered, 60);

  assert.deepEqual(normalize(filtered.steps), [addBlock(1, 1, 2, 'selected change')]);
  assert.equal(result[0].blocks[0].text, 'selected change');
  assert.deepEqual(normalize(result[1].blocks), []);
});

test('reject-all returns before annotation application', () => {
  const annotator = fs.readFileSync(
    path.join(__dirname, '../src/pages/Annotator/Annotator.tsx'),
    'utf8',
  );
  const anomalyStart = annotator.indexOf(
    'if (instructionExceedsTimelineScope(parsedInstruction, timelineScope))',
  );
  const rejectBranch = annotator.indexOf('if (decision === "reject")', anomalyStart);
  const rejectedRecord = annotator.indexOf(
    'persistCompletedAIRecord(aiRecord, "rejected")',
    rejectBranch,
  );
  const rejectReturn = annotator.indexOf('return {', rejectedRecord);
  const applyCall = annotator.indexOf('applyAIInstruction(', rejectReturn);

  assert.ok(anomalyStart >= 0);
  assert.ok(rejectBranch > anomalyStart);
  assert.ok(rejectedRecord > rejectBranch);
  assert.ok(rejectReturn > rejectedRecord);
  assert.ok(applyCall > rejectReturn);
});

test('multiple selected timelines accept changes to all or a subset', () => {
  const { instructionExceedsTimelineScope, applyAIInstruction } = loadHelpers();
  const scope = { axisIds: [1, 2], allowNew: false };
  const allSelected = instruction(
    addBlock(1, 1, 2, 'first'),
    addBlock(2, 3, 4, 'second'),
  );
  const selectedSubset = instruction(addBlock(2, 5, 6, 'subset'));

  assert.equal(instructionExceedsTimelineScope(allSelected, scope), false);
  assert.equal(instructionExceedsTimelineScope(selectedSubset, scope), false);

  const allResult = applyAIInstruction(makeAxes(), allSelected, 60);
  const subsetResult = applyAIInstruction(makeAxes(), selectedSubset, 60);
  assert.equal(allResult[0].blocks[0].text, 'first');
  assert.equal(allResult[1].blocks[0].text, 'second');
  assert.deepEqual(normalize(subsetResult[0].blocks), []);
  assert.equal(subsetResult[1].blocks[0].text, 'subset');
});

test('new-only scope creates and targets a new timeline with a safe name and ID', () => {
  const { instructionExceedsTimelineScope, applyAIInstruction } = loadHelpers();
  const axes = [{
    id: 1,
    type: 'Type-in',
    axisName: 'Existing name',
    blocks: [],
  }];
  const proposal = instruction(
    {
      action: 'addAxi',
      parameters: { axisId: 1, axisName: 'Existing name', axistype: 'Type-in' },
    },
    addBlock(1, 1, 2, 'new-axis change'),
  );
  const scope = { axisIds: [], allowNew: true };

  assert.equal(instructionExceedsTimelineScope(proposal, scope), false);
  const result = applyAIInstruction(axes, proposal, 60);

  assert.equal(result.length, 2);
  assert.equal(result[0].id, 1);
  assert.equal(result[1].id, 2);
  assert.equal(result[1].axisName, 'Existing name 1');
  assert.equal(result[1].blocks[0].text, 'new-axis change');
});

test('no timeline access bypasses annotation application', () => {
  const annotator = fs.readFileSync(
    path.join(__dirname, '../src/pages/Annotator/Annotator.tsx'),
    'utf8',
  );
  const noAccess = annotator.indexOf('if (!hasTimelineAccess)');
  const noApplyMessage = annotator.indexOf(
    'No timeline was selected, so no annotation changes were applied.',
    noAccess,
  );
  const applyCall = annotator.indexOf('applyAIInstruction(', noAccess);

  assert.ok(noAccess >= 0);
  assert.ok(noApplyMessage > noAccess);
  assert.ok(applyCall > noApplyMessage);
});

test('scope-anomaly dialog exposes reject, selected-only, and apply-all decisions', () => {
  const annotator = fs.readFileSync(
    path.join(__dirname, '../src/pages/Annotator/Annotator.tsx'),
    'utf8',
  );

  assert.match(annotator, /<DialogTitle>AI targeted other timelines<\/DialogTitle>/);
  assert.match(annotator, /resolveScopeAnomaly\("reject"\).*Reject all/s);
  assert.match(annotator, /resolveScopeAnomaly\("selected"\).*Apply selected timelines only/s);
  assert.match(annotator, /resolveScopeAnomaly\("all"\).*Apply all changes/s);
  assert.match(annotator, /if \(decision === "reject"\)/);
  assert.match(annotator, /if \(decision === "selected"\)/);
});

test('empty-data warning cancel cannot submit while continue submits an empty list', () => {
  const chatbox = fs.readFileSync(
    path.join(__dirname, '../src/components/Chatbox/Chatbox.tsx'),
    'utf8',
  );
  const dialogStart = chatbox.indexOf('<DialogTitle>No data views selected</DialogTitle>');
  const dialogEnd = chatbox.indexOf('</Dialog>', dialogStart);
  const dialog = chatbox.slice(dialogStart, dialogEnd);

  assert.ok(dialogStart >= 0);
  assert.match(dialog, /setConfirmEmptyDataViews\(false\).*Cancel/s);
  const cancelSection = dialog.slice(0, dialog.indexOf('Cancel'));
  assert.doesNotMatch(cancelSection, /submitMessage/);
  assert.match(dialog, /Continue without data/);
  assert.match(dialog, /submitMessage\(\[\]\)/);
});
