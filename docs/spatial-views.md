# Motion / Path and Force / Torque

The `motion` and `wrench` views are registered child processors; the central
processing workflow is unchanged. Both work without a video/audio topic.
The shared Play/Pause button and time slider drive sensor-only bags; when a media
player is mounted its progress drives the same time. Clicking either wrench plot
seeks that shared time, including the video and transcript when present.

## Motion / Path

- Inputs: all nonempty `nav_msgs/Odometry` and/or `people_msgs/People` topics by
  default. Either type alone is enough. Choose a subset in the load dialog.
- Each odometry topic is a robot (triangle). Each topic + exact nonempty person
  name is a person (circle). Blank names and invalid numeric data are skipped with
  warnings. If an optional explicit `id` changes name, that entity is rejected.
  Standard People messages have no explicit tracking ID: different names are
  different entities. Duplicate names at one timestamp keep the first person.
- Pose is in the Odometry header frame; linear twist is rotated from its child
  frame using pose orientation. Positions, headings and velocities are then
  transformed into the chosen fixed frame. People velocities use the header frame.
- Set a fixed frame in the load dialog, or leave blank to use the first recorded
  nonempty frame (time then topic order). `/tf_static` applies across chunks;
  recorded TF chains can be traversed in either direction. Dynamic translation
  and rotation are interpolated (linear / SLERP) within their recorded interval.
  There is no dynamic extrapolation. Samples without a transform are skipped,
  and zero remaining entities makes only this view unavailable.
- Entity checkboxes only affect rendering. Colors are deterministic, and hash
  collisions are resolved within the sorted entity list. Heading and velocity
  arrows are distinct; zero velocity has no velocity arrow. Arrow display length
  is capped, with exact velocity shown on hover.
- Motion mode shows a fading 5/10/30-second trail. Path summary shows whole paths,
  approximate XY distance and distance / elapsed sample time in m/s. Statistics
  are computed from original samples, before optional downsampling.

## Force / Torque

- Input type is `geometry_msgs/WrenchStamped` (not `WrenchedStamped`). Each selected
  topic is one entity with force XYZ (N) and torque XYZ (N·m).
- Two aligned plots share a time axis. Color identifies the topic; solid/dashed/
  dotted strokes identify X/Y/Z. The red line shows shared playback time; dots
  show the closest samples within tolerance. Hover shows actual sample timestamp
  and all six values. Clicking a plot seeks all time-dependent views.
- Each legend names its source frame; separate-frame series are never summed or
  transformed as if they shared an origin. A topic changing frame midstream has
  those samples skipped with a warning. Wrench TF transformations are not applied.

## Contract and limits

`processed_data.entities` includes stable IDs, labels, kind, color, topic,
`sample_count` and samples. Every sample has `seconds` (bag/chunk local) and
`bag_seconds`; the usual response `time_origin` is retained. Duplicate times use
the last sample and samples are sorted. Existing header / bag-time fallback applies.

Options per view in `view_options`:

| Option | Default | Meaning |
| --- | --- | --- |
| `topics` | All supported nonempty topics | List of selected topics |
| `fixed_frame` | First nonempty motion frame | Motion only; TF target frame |
| `max_samples` | 2000 | 2–20000 samples per entity, retaining endpoints |
| `sample_tolerance_seconds` | 0.5 | 0–60s closest-sample tolerance, shared by both views |

Nearest-time selection is deterministic (earlier sample wins a tie), with no
entity displayed before its first or after its last sample. Downsampling bounds
response/render cost but can omit peaks or short events; warnings identify reduced
series. For sparse/downsampled data, adjust the tolerance through `view_options`
as needed. Unknown frames, invalid samples and missing types do not block other views.

The independent TF/URDF/mesh 3D robot viewer remains out of scope pending the
client decision. TF here is used for the 2D motion coordinate conversion only.

## Demo and tests

Generate a 30-second real ROS1 bag with two robots, two people, two wrench topics
and a static camera transform (the generator refuses to overwrite existing files):

```sh
docker exec annotator-back python tools/generate_spatial_demo.py /app/datas/rosbag-data/spatial-demo-30s.bag
docker exec annotator-back python manage.py test tests.test_spatial_views tests.test_real_spatial_bag
```

Load the demo, optionally split into 0.25-minute chunks, choose `map` as the fixed
frame, and select Motion / Path and Force / Torque in the panels. Play, pause,
seek, toggle entities, switch summary mode, and hover/click the force plots.

Frontend tests: `node tests/spatialData.test.cjs` and
`node tests/spatialViews.test.cjs`. Tests cover nearest time, entity lifetime,
offset series, endpoint limits, shapes, toggling, mode switching and graph seeking.
Backend tests cover ROS decoding through the actual API, two chunks, cache reuse,
TF interpolation/inversion, velocities, identities, statistics, invalid frames,
timestamps and per-view availability. Browser visual smoothness still needs a
manual check with representative workloads.
