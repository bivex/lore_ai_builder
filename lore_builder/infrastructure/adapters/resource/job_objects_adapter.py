import ctypes
import os
import platform
import logging
from typing import Dict, Optional

from ....application.ports.outbound.resource_port import ResourceControllerPort

logger = logging.getLogger(__name__)


class JobObjectsResourceAdapter(ResourceControllerPort):
    """Adapter bridging ResourceControllerPort to the native C++ AgentJobEngine (JobObjects_RD).
    
    Supports:
    - macOS Darwin Kernel (PRIO_DARWIN_BG working set trim, SIGSTOP/SIGCONT freeze/thaw, seatbelt sandbox)
    - Windows Kernel (_EJOB working set compression, JobObjectFreezeInformation, completion ports)
    """

    def __init__(self, dylib_path: Optional[str] = None):
        self._sessions: Dict[str, ctypes.c_void_p] = {}
        self._lib = self._load_library(dylib_path)

    def _load_library(self, custom_path: Optional[str]) -> Optional[ctypes.CDLL]:
        paths_to_try = []
        if custom_path:
            paths_to_try.append(custom_path)

        current_dir = os.path.dirname(os.path.abspath(__file__))
        workspace_root = os.path.abspath(os.path.join(current_dir, "../../../.."))

        # Default build location
        if platform.system() == "Darwin":
            paths_to_try.append(
                os.path.join(workspace_root, "JobObjects_RD/out/build/lib/libAgentJobEngineC.dylib")
            )
        elif platform.system() == "Windows":
            paths_to_try.append(
                os.path.join(workspace_root, "JobObjects_RD/out/build/bin/AgentJobEngineC.dll")
            )
            paths_to_try.append(
                os.path.join(workspace_root, "JobObjects_RD/out/build/lib/AgentJobEngineC.dll")
            )

        for p in paths_to_try:
            if os.path.exists(p):
                try:
                    lib = ctypes.CDLL(p)
                    self._setup_function_signatures(lib)
                    logger.info(f"Loaded AgentJobEngine native library from {p}")
                    return lib
                except Exception as e:
                    logger.warning(f"Failed to load native library from {p}: {e}")

        logger.warning("AgentJobEngine native library not found. Operating in simulated fallback mode.")
        return None

    def _setup_function_signatures(self, lib: ctypes.CDLL) -> None:
        lib.AgentEngine_CreateSession.argtypes = [
            ctypes.c_char_p,
            ctypes.c_uint64,
            ctypes.c_uint32,
            ctypes.c_bool,
        ]
        lib.AgentEngine_CreateSession.restype = ctypes.c_void_p

        lib.AgentEngine_DestroySession.argtypes = [ctypes.c_void_p]
        lib.AgentEngine_DestroySession.restype = None

        lib.AgentEngine_AssignProcess.argtypes = [ctypes.c_void_p, ctypes.c_int32]
        lib.AgentEngine_AssignProcess.restype = ctypes.c_bool

        lib.AgentEngine_TrimWorkingSet.argtypes = [ctypes.c_void_p]
        lib.AgentEngine_TrimWorkingSet.restype = ctypes.c_bool

        lib.AgentEngine_FreezeJobTree.argtypes = [ctypes.c_void_p]
        lib.AgentEngine_FreezeJobTree.restype = ctypes.c_bool

        lib.AgentEngine_ThawJobTree.argtypes = [ctypes.c_void_p]
        lib.AgentEngine_ThawJobTree.restype = ctypes.c_bool

    def create_session(
        self,
        session_name: str,
        max_memory_mb: int = 512,
        cpu_cap_percent: int = 80,
        auto_trim_idle: bool = True,
    ) -> str:
        session_id = f"job_session_{session_name}"
        if self._lib:
            handle = self._lib.AgentEngine_CreateSession(
                session_name.encode("utf-8"),
                ctypes.c_uint64(max_memory_mb * 1024 * 1024),
                ctypes.c_uint32(cpu_cap_percent),
                ctypes.c_bool(auto_trim_idle),
            )
            if handle:
                self._sessions[session_id] = handle
                return session_id

        # Fallback simulation
        self._sessions[session_id] = None
        return session_id

    def assign_process(self, session_id: str, pid: int) -> bool:
        handle = self._sessions.get(session_id)
        if not hasattr(self, "_session_pids"):
            self._session_pids = {}
        if session_id not in self._session_pids:
            self._session_pids[session_id] = set()
        self._session_pids[session_id].add(pid)

        if self._lib and handle:
            return bool(self._lib.AgentEngine_AssignProcess(handle, ctypes.c_int32(pid)))
        return True

    def trim_working_set(self, session_id: str) -> bool:
        handle = self._sessions.get(session_id)
        if self._lib and handle:
            return bool(self._lib.AgentEngine_TrimWorkingSet(handle))
        return True

    def freeze_execution(self, session_id: str) -> bool:
        handle = self._sessions.get(session_id)
        # Avoid self-SIGSTOP deadlock if the current process itself was assigned
        pids = getattr(self, "_session_pids", {}).get(session_id, set())
        if os.getpid() in pids and len(pids) == 1:
            logger.debug(f"Skipping freeze on session {session_id} because only current PID is registered.")
            return True

        if self._lib and handle:
            return bool(self._lib.AgentEngine_FreezeJobTree(handle))
        return True

    def thaw_execution(self, session_id: str) -> bool:
        handle = self._sessions.get(session_id)
        pids = getattr(self, "_session_pids", {}).get(session_id, set())
        if os.getpid() in pids and len(pids) == 1:
            return True

        if self._lib and handle:
            return bool(self._lib.AgentEngine_ThawJobTree(handle))
        return True

    def destroy_session(self, session_id: str) -> None:
        handle = self._sessions.pop(session_id, None)
        if self._lib and handle:
            self._lib.AgentEngine_DestroySession(handle)
