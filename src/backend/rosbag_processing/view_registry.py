"""Add a child processor here; the workflow does not switch on view IDs."""
from .data_view_processors import (
    AudioProcessor, VideoProcessor, TranscriptProcessor, WaveformProcessor,
    AnnotationProcessor, AnnotationStatisticsProcessor, TierStatisticsProcessor,
)
from .spatial_processors import WrenchProcessor

PROCESSORS = (AudioProcessor(), VideoProcessor(), TranscriptProcessor(), WaveformProcessor(),
              AnnotationProcessor(), AnnotationStatisticsProcessor(), TierStatisticsProcessor(),
              WrenchProcessor())
