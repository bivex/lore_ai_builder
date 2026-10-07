from abc import ABC, abstractmethod
from typing import Optional
from contextlib import contextmanager


class ResourceControllerPort(ABC):
    """Outbound SPI port for OS-level kernel resource control (JobObjects / Darwin QoS)."""

    @abstractmethod
    def create_session(
        self,
        session_name: str,
        max_memory_mb: int = 512,
        cpu_cap_percent: int = 80,
        auto_trim_idle: bool = True,
    ) -> str:
        """Initialize an OS kernel job session with hardware boundaries."""
        pass

    @abstractmethod
    def assign_process(self, session_id: str, pid: int) -> bool:
        """Bind an agent process PID to the OS Job Object."""
        pass

    @abstractmethod
    def trim_working_set(self, session_id: str) -> bool:
        """Trigger OS memory compression to shrink idle heap during LLM reasoning."""
        pass

    @abstractmethod
    def freeze_execution(self, session_id: str) -> bool:
        """Freeze agent worker process tree (SIGSTOP / EJOB Freeze) with 0% CPU consumption."""
        pass

    @abstractmethod
    def thaw_execution(self, session_id: str) -> bool:
        """Thaw agent worker process tree (SIGCONT / EJOB Thaw) to resume execution."""
        pass

    @abstractmethod
    def destroy_session(self, session_id: str) -> None:
        """Clean up kernel handles and release OS resources."""
        pass

    @contextmanager
    def memory_shield(self, session_id: str):
        """Context manager that compresses memory while waiting for external LLM calls."""
        self.trim_working_set(session_id)
        try:
            yield
        finally:
            pass

    @contextmanager
    def frozen_scope(self, session_id: str):
        """Context manager that freezes the process tree during audit/synchronization."""
        self.freeze_execution(session_id)
        try:
            yield
        finally:
            self.thaw_execution(session_id)
