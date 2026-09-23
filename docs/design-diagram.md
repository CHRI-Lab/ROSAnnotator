# Design diagram

This diagram describes the implemented whole-bag and chunk data-view pipeline.

```mermaid
flowchart TD
    Main[MainPage] --> Loader[loadDataViews: discover catalog and request views concurrently]
    Loader --> Catalog[GET /api/views/]
    Loader --> Whole[POST /api/process_rosbag/ with view_ids]
    Loader --> Chunk[POST /api/chunks/id/index/process/ with view_ids]
    Whole --> WS[RosbagProcessingSession]
    Chunk --> CS[ChunkProcessingSession]
    WS --> Base[BaseDataProcessingSession.process]
    CS --> Base
    Base --> Workflow[process_views]
    Workflow --> Registry[view_registry.PROCESSORS and dependency order]
    Workflow --> Reader[RosbagReader: metadata, timestamps, message iteration, close]
    Workflow --> Cache[ViewCache: source, view, topics, options, bounds, dependencies]
    Registry --> Parent[DataViewProcessor]
    Parent --> Audio[AudioProcessor]
    Parent --> Video[VideoProcessor]
    Parent --> Transcript[TranscriptProcessor]
    Parent --> Waveform[WaveformProcessor]
    Parent --> Annotation[AnnotationProcessor and two statistics processors]
    Audio -. optional mux input .-> Video
    Audio --> Transcript
    Audio --> Waveform
    Workflow --> Contract[Per-view availability, reason, data, time origin, warnings]
    Contract --> Metadata[attach_metadata: codebook and rebased annotations]
    Metadata --> Loader
    Loader --> Annotator[Annotator: shared playback state and seek callback]
    Annotator --> Panels[Frontend registry and isolated ViewPanel boundaries]
    Annotator --> Clock[Shared Play/Pause and seek slider]
    Annotator --> Timeline[Timeline: mount after initial data and recovery are complete]
    Timeline --> Recovery[Autosave API: bag or manifest/chunk scope]
```

```mermaid
sequenceDiagram
    participant UI as Frontend loader
    participant API as API/session
    participant Flow as Shared workflow
    participant Cache as View cache
    participant Child as Child processor
    UI->>API: Request one registered view
    API->>Flow: ProcessingRequest including bag/chunk and options
    Flow->>Flow: Inspect bag and resolve dependencies
    Flow->>Child: check_availability(context)
    alt Supported nonempty input
        Flow->>Cache: Lock and load matching cache
        alt Cache miss
            Flow->>Child: extract(context, selected_topics)
            Flow->>Child: preprocess(context, extracted)
            Flow->>Child: serialize(context, topics, data, warnings)
            Flow->>Cache: Atomically publish successful result
        end
    else Missing/invalid input or processing failure
        Flow->>Flow: Record unavailable/failed view and reason
    end
    Flow-->>API: Structured result and legacy compatibility fields
    API-->>UI: View result; other requests continue independently
    UI->>UI: Mount valid views; show per-view loading or reason
    UI->>UI: Show global error only if no usable views remain
```

The cache lock is released by the OS if a worker exits. A manifest is navigation
and recovery identity, not processing-cache identity. Optional chat context is
stored under a returned context token in Django's cache instead of module globals.
