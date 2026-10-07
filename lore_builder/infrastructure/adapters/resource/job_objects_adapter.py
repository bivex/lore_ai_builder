import ctypes
import os
import platform
import logging
from typing import Dict, Optional, Set

from ....application.ports.outbound.resource_port import ResourceControllerPort

logger = logging.getLogger(__name__)


class JobObjectsResourceAdapter(ResourceControllerPort):
    """Adapter bridging ResourceControllerPort strictly to the native C++ AgentJobEngine (JobObjects_RD).
    
    No fallbacks or simulation: requires the native library to load and execute OS kernel calls.
    Supports:
    - macOS Darwin Kernel (PRIO_DARWIN_BG working set trim, SIGSTOP/SIGCONT freeze/thaw, seatbelt sandbox)
    - Windows Kernel (_EJOB working set compression, JobObjectFreezeInformation, completion ports)
    """

    def __init__(self, dylib_path: Optional[str] = None):
        self._sessions: Dict[str, ctypes.c_void_p] = {}
        self._session_pids: Dict[str, Set[int]] = {}
        self._lib = self._load_library_strictly(dylib_path)

    def _load_library_strictly(self, custom_path: Optional[str]) -> ctypes.CDLL:
        paths_to_try = []
        if custom_path:
            paths_to_try.append(custom_path)

        current_dir = os.path.dirname(os.path.abspath(__file__))
        workspace_root = os.path.abspath(os.path.join(current_dir, "../../../.."))

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
                    logger.info(f"Strictly loaded native AgentJobEngine from {p}")
                    return lib
                except Exception as e:
                    raise RuntimeError(f"Failed to load native AgentJobEngine library at {p}: {e}")

        raise RuntimeError(
            f"AgentJobEngine native library not found in paths: {paths_to_try}. "
            "Native library is strictly required; fallbacks are disabled."
        )

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
        handle = self._lib.AgentEngine_CreateSession(
            session_name.encode("utf-8"),
            ctypes.c_uint64(max_memory_mb * 1024 * 1024),
            ctypes.c_uint32(cpu_cap_percent),
            ctypes.c_bool(auto_trim_idle),
        )
        if not handle:
            raise RuntimeError(f"Native AgentEngine_CreateSession returned NULL for '{session_name}'.")

        self._sessions[session_id] = handle
        self._session_pids[session_id] = set()
        return session_id

    def assign_process(self, session_id: str, pid: int) -> bool:
        if session_id not in self._sessions:
            raise KeyError(f"Session '{session_id}' not found.")
        handle = self._sessions[session_id]

        success = bool(self._lib.AgentEngine_AssignProcess(handle, ctypes.c_int32(pid)))
        if not success:
            raise RuntimeError(f"Native AgentEngine_AssignProcess failed to bind PID {pid} to '{session_id}'.")

        self._session_pids[session_id].add(pid)
        return True

    def trim_working_set(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            raise KeyError(f"Session '{session_id}' not found.")
        handle = self._sessions[session_id]

        success = bool(self._lib.AgentEngine_TrimWorkingSet(handle))
        if not success:
            raise RuntimeError(f"Native AgentEngine_TrimWorkingSet failed for '{session_id}'.")
        return True

    def freeze_execution(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            raise KeyError(f"Session '{session_id}' not found.")
        handle = self._sessions[session_id]

        # Safety guard for self-freeze: if only current PID is registered, skip self-SIGSTOP deadlock
        pids = self._session_pids.get(session_id, set())
        if os.getpid() in pids and len(pids) == 1:
            logger.debug(f"Process tree only contains orchestrator PID {os.getpid()}; skipping self-SIGSTOP.")
            return True

        success = bool(self._lib.AgentEngine_FreezeJobTree(handle))
        if not success:
            raise RuntimeError(f"Native AgentEngine_FreezeJobTree failed for '{session_id}'.")
        return True

    def thaw_execution(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            raise KeyError(f"Session '{session_id}' not found.")
        handle = self._sessions[session_id]

        pids = self._session_pids.get(session_id, set())
        if os.getpid() in pids and len(pids) == 1:
            return True

        success = bool(self._lib.AgentEngine_ThawJobTree(handle))
        if not success:
            raise RuntimeError(f"Native AgentEngine_ThawJobTree failed for '{session_id}'.")
        return True

    def destroy_session(self, session_id: str) -> None:
        handle = self._sessions.pop(session_id, None)
        self._session_pids.pop(session_id, None)
        if not handle:
            raise KeyError(f"Session '{session_id}' does not exist or was already destroyed.")
        self._lib.AgentEngine_DestroySession(handle)
