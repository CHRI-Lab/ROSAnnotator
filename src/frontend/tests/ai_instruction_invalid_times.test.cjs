// Contract tests for rejecting invalid model-proposed annotation times.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadAIInstructionHelpers() {
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
    axisName: 'Existing annotations',
    blocks: [{ start: 10, end: 12, text: 'Existing block' }],
  },
];

const makeInstruction = (start, end) => ({
  type: 'instruction',
  steps: [
    {
      action: 'addBlock',
      parameters: { axisId: 1, start, end, text: 'Model proposal' },
    },
  ],
});

test('invalid model block times leave annotations unchanged', async (t) => {
  const { applyAIInstruction } = loadAIInstructionHelpers();
  const duration = 60;
  const cases = [
    { name: 'negative start', start: -1, end: 2 },
    { name: 'start after end', start: 8, end: 4 },
    { name: 'end beyond duration', start: 58, end: 65 },
    { name: 'nonfinite start', start: NaN, end: 2 },
    { name: 'nonfinite end', start: 58, end: Infinity },
  ];

  for (const invalidCase of cases) {
    await t.test(invalidCase.name, () => {
      const axes = makeAxes();
      const originalAxes = normalize(axes);
      const result = applyAIInstruction(
        axes,
        makeInstruction(invalidCase.start, invalidCase.end),
        duration,
      );

      assert.deepEqual(normalize(axes), originalAxes);
      assert.deepEqual(normalize(result), originalAxes);
    });
  }
});

test('zero start and equal start/end within the duration are accepted', () => {
  const { applyAIInstruction } = loadAIInstructionHelpers();
  for (const [start, end] of [[0, 2], [60, 60]]) {
    const result = applyAIInstruction(makeAxes(), makeInstruction(start, end), 60);
    assert.deepEqual(normalize(result[0].blocks[1]), { start, end, text: 'Model proposal' });
  }
});

test('unknown or invalid duration never permits an AI block', () => {
  const { applyAIInstruction } = loadAIInstructionHelpers();
  for (const duration of [undefined, NaN, Infinity, -1]) {
    const axes = makeAxes();
    const result = applyAIInstruction(axes, makeInstruction(1, 2), duration);
    assert.deepEqual(normalize(result), axes);
  }
});

test('a model block ending exactly at duration is accepted', () => {
  const { applyAIInstruction } = loadAIInstructionHelpers();
  const axes = makeAxes();
  const result = applyAIInstruction(axes, makeInstruction(58, 60), 60);

  assert.deepEqual(normalize(axes), makeAxes());
  assert.deepEqual(normalize(result[0].blocks[1]), {
    start: 58,
    end: 60,
    text: 'Model proposal',
  });
});

test('AI-created axes with the same proposed name receive numeric suffixes', () => {
  const { applyAIInstruction } = loadAIInstructionHelpers();
  const instruction = {
    type: 'instruction',
    steps: [1, 2, 3].map((axisId) => ({
      action: 'addAxi',
      parameters: { axisId, axisName: "Speaker's attitude", axistype: 'Type-in' },
    })),
  };

  const result = applyAIInstruction([], instruction, 60);

  assert.deepEqual(
    normalize(result.map((axis) => axis.axisName)),
    ["Speaker's attitude 1", "Speaker's attitude 2", "Speaker's attitude 3"],
  );
});

test('AI-created axis avoids an existing name case-insensitively', () => {
  const { applyAIInstruction } = loadAIInstructionHelpers();
  const existing = [{
    id: 1,
    type: 'Type-in',
    axisName: "Speaker's Attitude",
    blocks: [],
  }];
  const instruction = {
    type: 'instruction',
    steps: [{
      action: 'addAxi',
      parameters: { axisId: 2, axisName: "speaker's attitude", axistype: 'Type-in' },
    }],
  };

  const result = applyAIInstruction(existing, instruction, 60);

  assert.equal(result[1].axisName, "speaker's attitude 1");
});

test('AI-created axis IDs are remapped when they collide with existing axes', () => {
  const { applyAIInstruction, remapAIInstructionAxisIds } = loadAIInstructionHelpers();
  const existing = [
    { id: 1, type: 'Type-in', axisName: 'Unknown Speaker', blocks: [
      { start: 0, end: 7.8, text: 'Existing transcript' },
    ] },
    { id: 2, type: 'Type-in', axisName: 'SPEAKER_00', blocks: [] },
    { id: 3, type: 'Type-in', axisName: 'SPEAKER_01', blocks: [] },
  ];
  const instruction = {
    type: 'instruction',
    steps: [
      { action: 'addAxi', parameters: {
        axisId: 1, axisName: 'Speech Attitude', axistype: 'Type-in',
      } },
      { action: 'addBlock', parameters: {
        axisId: 1, start: 0, end: 7.8, text: 'ATTITUDE_NEUTRAL',
      } },
    ],
  };

  const remapped = remapAIInstructionAxisIds(existing, instruction);
  const result = applyAIInstruction(existing, remapped, 60);

  assert.equal(remapped.steps[0].parameters.axisId, 4);
  assert.equal(remapped.steps[1].parameters.axisId, 4);
  assert.equal(result.length, 4);
  assert.equal(result[0].blocks.length, 1);
  assert.equal(result[3].axisName, 'Speech Attitude');
  assert.deepEqual(normalize(result[3].blocks), [
    { start: 0, end: 7.8, text: 'ATTITUDE_NEUTRAL' },
  ]);
});

test('manual axis names detect trimmed case-insensitive duplicates', () => {
  const { isDuplicateAxisName } = loadAIInstructionHelpers();
  const axes = [
    { id: 1, axisName: 'Speaker Attitude' },
    { id: 2, axisName: 'Notes' },
  ];

  assert.equal(isDuplicateAxisName(axes, 2, ' speaker attitude '), true);
  assert.equal(isDuplicateAxisName(axes, 1, 'Speaker Attitude'), false);
  assert.equal(isDuplicateAxisName(axes, 2, 'Different name'), false);
});
