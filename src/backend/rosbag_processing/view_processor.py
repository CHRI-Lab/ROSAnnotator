"""The extension contract; processors never read or write cache entries."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


class ViewUnavailable(ValueError):
    pass


@dataclass
class ViewContext:
    reader: object
    directory: Path
    options: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)
    cache_id: Optional[str] = None


class DataViewProcessor(ABC):
    view_id = ''
    supported_message_types = ()
    dependencies = ()
    cache_version = 1

    def check_availability(self, context):
        candidates = sorted(name for name, info in context.reader.topics.items()
                            if info['message_type'] in self.supported_message_types
                            and info['message_count'] > 0)
        requested = context.options.get('topics')
        if requested is not None:
            if not isinstance(requested, list) or len(requested) != 1 or requested[0] not in candidates:
                raise ViewUnavailable('Select one nonempty topic with a supported message type.')
            return requested
        if not candidates:
            raise ViewUnavailable('No nonempty topic with a supported message type: ' +
                                  ', '.join(self.supported_message_types))
        return candidates[:1]

    @abstractmethod
    def extract(self, context, topics):
        """Extract ROS records or dependency data."""

    @abstractmethod
    def preprocess(self, context, extracted):
        """Return JSON data after validating usable input."""

    def serialize(self, context, topics, data, warnings=()):
        return {'view_id': self.view_id, 'status': 'ready', 'available': True,
                'reason': None, 'selected_topics': topics,
                'duration': context.reader.duration, 'time_origin': context.reader.time_origin,
                'processed_data': data, 'warnings': list(warnings)}

    def legacy_fields(self, data):
        """Optional compatibility adapter for pre-registry API consumers."""
        return {}
