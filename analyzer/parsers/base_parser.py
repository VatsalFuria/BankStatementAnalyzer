from abc import ABC, abstractmethod
from typing import List
from analyzer.models import StandardTransaction

class BaseParser(ABC):
    # Subclasses should set this to a human-readable name — shown in the
    # GUI's parser dropdown instead of the raw class name.
    display_name: str | None = None

    def __init__(self):
        if self.display_name is None:
            self.display_name = type(self).__name__

    @abstractmethod
    def can_parse(self, filepath: str) -> bool:
        pass

    @abstractmethod
    def parse(self, filepath: str) -> List[StandardTransaction]:
        pass