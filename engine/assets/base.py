"""
engine/assets/base.py - Abstract visual asset provider interface
"""
from abc import ABC, abstractmethod
from typing import Optional, List

class VisualAssetProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider credentials/network are available."""
        pass

    @abstractmethod
    def fetch_video(self, queries: List[str], target_path: str, min_duration: float = 5.0) -> Optional[str]:
        """Attempt to search and download a video clip matching the queries. Returns local path or None."""
        pass
