"""Add a child processor here; the workflow does not switch on view IDs."""
from .data_view_processors import (
    AudioProcessor, VideoProcessor, TranscriptProcessor, WaveformProcessor,
    AnnotationProcessor, AnnotationStatisticsProcessor, TierStatisticsProcessor,
)

PROCESSORS = (AudioProcessor(), VideoProcessor(), TranscriptProcessor(), WaveformProcessor(),
              AnnotationProcessor(), AnnotationStatisticsProcessor(), TierStatisticsProcessor())
