const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');

function setup(view) {
  let cursor = 0;
  const state = [], cache = new Map();
  function load(name) {
    if (cache.has(name)) return cache.get(name);
    const file = ['tsx', 'ts'].map(ext => path.resolve(__dirname, `../src/components/FrontEndWorkspace/${name}.${ext}`)).find(fs.existsSync);
    const mod = { exports: {} };
    vm.runInNewContext(ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
    } }).outputText, { module: mod, exports: mod.exports, require(dep) {
      if (dep.startsWith('./')) return load(dep.slice(2));
      if (dep === 'react') return { useMemo: fn => fn(), useState(initial) {
        const index = cursor++; if (!(index in state)) state[index] = initial;
        return [state[index], value => { state[index] = typeof value === 'function' ? value(state[index]) : value; }];
      } };
      if (dep === '@mui/material') return new Proxy({}, { get: (_, name) => name });
      return require(dep);
    } });
    cache.set(name, mod.exports); return mod.exports;
  }
  const Component = load('SpatialViews')[view];
  return props => { cursor = 0; return Component(props); };
}

function elements(root, predicate) {
  const found = [];
  function visit(node) {
    if (Array.isArray(node)) return node.forEach(visit);
    if (!React.isValidElement(node)) return;
    if (predicate(node)) found.push(node);
    if (typeof node.type === 'function') visit(node.type(node.props)); else visit(node.props.children);
  }
  visit(root); return found;
}
function props() {
  const entities = ['robot', 'person'].map((kind, i) => ({ id: kind, kind, label: kind, color: ['red', 'blue'][i],
    samples: [0, 1, 2].map(seconds => ({ seconds, bag_seconds: seconds+5, position: [seconds, i, 0], velocity: [1, 0, 0], heading: 0,
      force: [seconds, -1, 2], torque: [-seconds, 0, 1] })),
    summary: { distance_m: 2, average_speed_mps: 1, elapsed_seconds: 2 } }));
  const processed_data = { entities, fixed_frame: 'map', sample_tolerance_seconds: 0.5 };
  return { played: 1, views: { motion: { processed_data }, wrench: { processed_data, duration: 2 } }, onSeek() {} };
}
test('motion uses different entity shapes and toggles without changing source data', () => {
  const render = setup('MotionView'), context = props();
  let tree = render(context);
  assert.equal(elements(tree, n => n.type === 'circle').length, 1);
  assert.equal(elements(tree, n => n.type === 'path' && n.props.d === 'M 11 0 L -8 -7 L -8 7 Z').length, 1);
  elements(tree, n => n.type === 'FormControlLabel')[0].props.control.props.onChange();
  tree = render(context);
  assert.equal(elements(tree, n => n.type === 'path' && n.props.d === 'M 11 0 L -8 -7 L -8 7 Z').length, 0);
  assert.equal(context.views.motion.processed_data.entities.length, 2);
});
test('summary switches from current markers to whole paths and distance statistics', () => {
  const render = setup('MotionView'), context = props();
  let tree = render(context);
  elements(tree, n => n.type === 'Select')[0].props.onChange({ target: { value: 'summary' } });
  tree = render(context);
  assert.equal(elements(tree, n => n.type === 'circle').length, 0);
  assert.equal(elements(tree, n => n.type === 'line' && n.props.opacity === 0.85).length, 4);
  assert.ok(elements(tree, n => n.type === 'Typography').some(n => JSON.stringify(n.props.children).includes('average')));
});
test('wrench has aligned plots, shared cursor, hover values and common seek callback', () => {
  const render = setup('WrenchView'), context = props();
  let sought; context.onSeek = time => { sought = time; };
  let tree = render(context);
  const charts = elements(tree, n => n.type === 'svg');
  assert.equal(charts.length, 2);
  assert.equal(elements(tree, n => n.type === 'polyline').length, 12);
  assert.equal(elements(tree, n => n.type === 'line' && n.props.stroke === '#ff5252').length, 2);
  const event = { clientX: 320, currentTarget: { getBoundingClientRect: () => ({ left: 0, width: 610 }) } };
  charts[0].props.onClick(event); assert.equal(sought, 1);
  charts[1].props.onMouseMove(event);
  tree = render(context);
  assert.ok(elements(tree, n => n.type === 'Typography').some(n => JSON.stringify(n.props.children).includes('Force (')));
});
