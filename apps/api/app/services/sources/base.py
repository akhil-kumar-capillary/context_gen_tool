"""Abstract base class for all context source modules."""
from abc import ABC, abstractmethod
from typing import Any

from app.core.websocket import WebSocketManager


class BaseSourceModule(ABC):
    """Interface that all source modules must implement."""

    @property
    @abstractmethod
    def module_id(self) -> str:
        """Unique module identifier: 'databricks', 'confluence', 'config_apis'"""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable module name."""
        ...

    @abstractmethod
    async def test_connection(self, credentials: dict) -> dict:
        """Test connection to the source.
        Returns: {success: bool, message: str, user?: str}
        """
        ...

    @abstractmethod
    async def extract(
        self,
        config: dict,
        ws_manager: WebSocketManager,
        user_id: int,
        org_id: int,
    ) -> str:
        """Run extraction pipeline. Returns run_id.
        Sends progress via ws_manager.
        """
        ...

    @abstractmethod
    async def get_extracted_data(self, run_id: str) -> dict:
        """Get extracted data for review before LLM generation."""
        ...

    @abstractmethod
    async def generate_context(
        self,
        run_id: str,
        llm_config: dict,
        ws_manager: WebSocketManager,
    ) -> list[dict]:
        """Generate context documents from extracted data.
        Returns: [{doc_key: str, doc_content: str}]
        """
        ...
