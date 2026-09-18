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
