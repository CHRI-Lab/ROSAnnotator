# Code style guide

Use the naming conventions already established in ROSAnnotator: `snake_case`
for Python functions and methods, `camelCase` for TypeScript functions and
methods, and `PascalCase` for classes, types, and React components. This keeps
each part of the application readable and consistent with its existing code.

This guide applies to new code and code being changed. Follow the surrounding
file's formatting when editing existing code. Where the repository has mixed
styles, the defaults below are decisions for new files, not claims that every
existing file already follows them.

## Naming at a glance

| Element | Python backend | TypeScript / React frontend |
| --- | --- | --- |
| Class | `PascalCase`: `RosbagReader`, `DataViewProcessor` | `PascalCase`: `BaseDataView` |
| Function or method | `snake_case`: `get_rosbag_duration`, `check_availability` | `camelCase`: `loadDataViews`, `toDefinition` |
| Variable, parameter, or internal field | `snake_case`: `bag_filename`, `audio_path` | `camelCase`: `selectedRange`, `axisType` |
| Fixed module-level constant | `UPPER_SNAKE_CASE`: `PROCESSORS` | `UPPER_SNAKE_CASE` for new fixed configuration constants, e.g. `AUTOSAVE_DELAY_MS` |
| Boolean | Prefer `is_`, `has_`, or `can_`, e.g. `has_messages` | Prefer `is`, `has`, or `can`, e.g. `isEditing`, `hasUnsavedEdits` |
| Internal helper | Leading underscore: `_validate_chunk` (illustrative) | Use `private` for class members; keep module helpers unexported |
| Interface or type alias | Follow the class convention where applicable | `PascalCase`: `AxisProps`, `ViewPayload`; no `I` prefix |
| React component | Not applicable | `PascalCase`: `Axis`, `Block`, `DataViewSelector` |
| React hook | Not applicable | `use` + purpose: `useAutosave` |
| Event handler | Follow the function convention | `handle` + event locally: `handleDoubleClick`; `on` + event for callback props: `onSave` |

An ordinary TypeScript `const` still uses `camelCase`. Components and styled
components use `PascalCase` even when declared with `const`, as in
`AxisContainer`. Existing registry names such as `availableViews` stay as
they are. Python class attributes such as `view_id` and `cache_version` retain
their existing lowercase convention.

## Files and directories

- Python modules and packages use `snake_case`: `rosbag_reader.py`,
  `view_processor.py`, `rosbag_processing/`.
- React component files use the component name: `Axis.tsx`, `Block.tsx`.
  Follow the existing component-folder layout, such as `components/Axis/`.
- TypeScript helpers, API modules, and type modules use `camelCase`:
  `saveUtils.ts`, `dataViews.ts`, `viewTypes.ts`. Hook files include `use`, as
  in `useAutosave.ts`.
- Use lowercase `index.tsx` for new component re-export files. Existing
  `Index.tsx` files are legacy exceptions; preserve their spelling and import
  paths during unrelated changes, including on case-sensitive systems.
- Backend test modules use `test_*.py`; test methods use
  `test_<scenario>_<expected_result>`, following the descriptive names in
  `tests/test_chunks.py`.
- Documentation files use lowercase words separated by hyphens, such as
  `code-style.md` and `data-view-processing-contracts.md`.

## Choose names that explain their purpose

Use nouns for data and classes, and verbs for actions: `RosbagReader`,
`selectedRange`, `loadDataViews`, and `check_availability`. Prefer specific
names such as `audio_path` or `selectedTopics` over `data1`, `temp`, or `obj`.
Short names are appropriate when their meaning is clear in a small scope.

Use plural names for collections, such as `topics`, `blocks`, and `warnings`.
Include units when a value could otherwise be ambiguous: `duration_seconds`
in Python and `idleDelayMs` in TypeScript. Preserve existing contract fields
such as `duration`; explain their units in the associated type or documentation.

Keep domain terms consistent with nearby code, including `bag`, `chunk`,
`axis`, `annotation`, and `view`. Preserve established acronym spelling such
as `RosbagReader` and `BaseDataView`; avoid introducing another spelling for
the same concept.

## Formatting defaults

| Rule | Python | TypeScript / TSX |
| --- | --- | --- |
| Indentation in new files | 4 spaces | 2 spaces |
| String quotes in new files | Single quotes; triple double quotes for docstrings | Single quotes; double quotes for JSX attributes |
| Statement endings | No semicolons | Semicolons |
| Blocks | Standard indented blocks | Opening brace on the declaration line |
| Multiline lists and objects | Trailing commas | Trailing commas |
| Long expressions | Wrap at logical boundaries using parentheses | Wrap arguments, object fields, and JSX props at logical boundaries |

Both single and double quotes occur in the repository, and some frontend files
use 4 spaces. Match the current file when editing it. Choose a different quote
delimiter when it avoids unnecessary escaping. There is no repository-wide
enforced line-length limit; keep expressions easy to scan and split long calls
or JSX props across lines rather than compressing several operations together.

Separate logical steps with blank lines. In new Python files, use two blank
lines between top-level definitions and one between class methods. Avoid
unrelated whitespace changes in a functional patch.

## Functions, types, and components

Keep each function focused on one clear responsibility. Follow the existing
declaration form nearby: React components commonly use
`const Axis: React.FC<AxisProps> = (...) => { ... };`, while shared API helpers
also use named `function` declarations. Both are established styles.

Use `<ComponentName>Props` for a component's props interface. Preserve the
module's export pattern: components such as `Axis` use a default export and
an index re-export; shared helpers and types also use named exports.

Give shared TypeScript interfaces and function boundaries meaningful types.
Prefer `unknown` with validation for untrusted data instead of adding `any`.
Use `import type` for imports used only as types, following `api/dataViews.ts`.
Python type annotations are currently mixed; add useful annotations to new
interfaces without requiring a wholesale conversion of existing modules.

For new files, group imports into standard library / third-party / local
modules in Python, and external / project modules in TypeScript. Keep existing
lazy imports where they serve a runtime purpose, such as loading ROS inside
`RosbagReader.__enter__`.

## API and stored-data names

Preserve request, response, stored-data, registry, and framework-defined names
exactly. TypeScript payload types deliberately contain Python-style fields
such as `video_path`, `view_id`, and `duration_seconds`. Internal frontend
variables can use `camelCase` while reading those fields:

```ts
const videoPath = payload.video_path;
const durationSeconds = payload.duration_seconds;
```

Likewise, keep Django hooks such as `validate_bag_filename` and Python special
methods such as `__enter__`. Naming cleanup must not silently change a public
contract. See [data-view processing contracts](data-view-processing-contracts.md)
for the existing response fields and extension interfaces.

## Comments and documentation

Write comments that explain intent, units, constraints, or surprising behavior.
Use Python docstrings and TypeScript documentation comments for shared
contracts when an explanation helps the caller. Avoid comments that merely
repeat an obvious operation. Use clear English for new shared documentation.

## Review and tooling

Before submitting a change, check that names follow the relevant language,
local formatting is consistent, units are clear, and public fields retain
their established spelling. Keep broad renaming or formatting work in its own
change so it can be reviewed separately.

The frontend has [ESLint configuration](../src/frontend/.eslintrc.cjs) and
[TypeScript configuration](../src/frontend/tsconfig.json). From `src/frontend`,
`npm run lint` runs ESLint and `npm run build` runs TypeScript checking and the
Vite build. These checks do not enforce every naming or formatting decision in
this guide. No shared Prettier, Black, Ruff, or EditorConfig configuration was
found when this guide was written; the defaults above are review conventions.

## Existing examples

- [Axis.tsx](../src/frontend/src/components/Axis/Axis.tsx): component and props
  names, styled components, event handlers, and callback props.
- [dataViews.ts](../src/frontend/src/api/dataViews.ts): `camelCase` API helpers
  alongside preserved `snake_case` response fields.
- [BaseDataView.tsx](../src/frontend/src/components/FrontEndWorkspace/BaseDataView.tsx):
  a `PascalCase` class with `camelCase` methods.
- [rosbag_reader.py](../src/backend/rosbag_processing/rosbag_reader.py) and
  [view_processor.py](../src/backend/rosbag_processing/view_processor.py):
  `PascalCase` classes with `snake_case` methods and attributes.
