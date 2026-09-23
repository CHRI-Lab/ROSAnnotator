# Force / Torque

The `wrench` view is a registered child processor; the central
processing workflow is unchanged. It works without a video/audio topic.
The shared Play/Pause button and time slider drive sensor-only bags; when a media
player is mounted its progress drives the same time. Clicking either wrench plot
seeks that shared time, including the video and transcript when present.

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
| `max_samples` | 2000 | 2–20000 samples per entity, retaining endpoints |
| `sample_tolerance_seconds` | 0.5 | 0–60s closest-sample tolerance |

Nearest-time selection is deterministic (earlier sample wins a tie), with no
entity displayed before its first or after its last sample. Downsampling bounds
response/render cost but can omit peaks or short events; warnings identify reduced
series. For sparse/downsampled data, adjust the tolerance through `view_options`
as needed. Unknown frames, invalid samples and missing types do not block other views.

## Demo and tests

Generate a 30-second real ROS1 bag with two wrench topics (the generator refuses to overwrite existing files):

```sh
docker exec annotator-back python tools/generate_spatial_demo.py /app/datas/rosbag-data/spatial-demo-30s.bag
docker exec annotator-back python manage.py test tests.test_spatial_views tests.test_real_spatial_bag
```

Load the demo, optionally split into 0.25-minute chunks, and select Force / Torque
in a panel. Play, pause, seek, toggle entities, and hover/click the force plots.

Frontend tests: `node tests/spatialData.test.cjs` and
`node tests/spatialViews.test.cjs`. Tests cover nearest time, entity lifetime,
offset series, endpoint limits, toggling and graph seeking.
Backend tests cover ROS decoding through the actual API, two chunks, cache reuse,
invalid frames, timestamps and per-view availability. Browser visual smoothness
still needs a manual check with representative workloads.
