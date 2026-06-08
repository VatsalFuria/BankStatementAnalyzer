from abc import ABC, abstractmethod
from typing import List
from analyzer.models import StandardTransaction

class BaseParser(ABC):
    @abstractmethod
    def can_parse(self, filepath: str) -> bool:
        """Return True if this parser can handle the file."""
        pass

    @abstractmethod
    def parse(self, filepath: str) -> List[StandardTransaction]:
        """Convert raw file into list of StandardTransaction objects."""
        pass