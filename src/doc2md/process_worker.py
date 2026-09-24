from __future__ import annotations

import ctypes
import multiprocessing
import sys
import tempfile
import time
from enum import IntEnum, IntFlag
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Callable, NamedTuple

from doc2md.limits import MAX_MARKDOWN_BYTES


DEFAULT_MAX_RESULT_BYTES = MAX_MARKDOWN_BYTES
WORKER_TERMINATION_SECONDS = 5
MAX_ERROR_CHARACTERS = 64 * 1024
WORKER_MEMORY_LIMIT = 768 * 1024 * 1024
WORKER_TOTAL_MEMORY_LIMIT = 1024 * 1024 * 1024
WORKER_PROCESS_LIMIT = 16


class WorkerError(RuntimeError):
    pass


class JobLimitFlags(IntFlag):
    ACTIVE_PROCESS = 0x00000008
    JOB_MEMORY = 0x00000100
    PROCESS_MEMORY = 0x00000200
    KILL_ON_JOB_CLOSE = 0x00002000


class JobInformationClass(IntEnum):
    EXTENDED_LIMIT_INFORMATION = 9


class JobLimits(NamedTuple):
    flags: int
    active_processes: int
    process_memory_bytes: int
    job_memory_bytes: int


EXPECTED_JOB_LIMITS = JobLimits(
    flags=int(
        JobLimitFlags.ACTIVE_PROCESS
        | JobLimitFlags.JOB_MEMORY
        | JobLimitFlags.PROCESS_MEMORY
        | JobLimitFlags.KILL_ON_JOB_CLOSE
    ),
    active_processes=WORKER_PROCESS_LIMIT,
    process_memory_bytes=WORKER_MEMORY_LIMIT,
    job_memory_bytes=WORKER_TOTAL_MEMORY_LIMIT,
)


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class WindowsJob:
    def __init__(self) -> None:
        self._handle: int | None = None
        self._kernel32: ctypes.CDLL | None = None
        if sys.platform == "win32":
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._configure_api()

    def _configure_api(self) -> None:
        kernel32 = self._kernel32
        if kernel32 is None:
            return
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        kernel32.SetInformationJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        kernel32.SetInformationJobObject.restype = ctypes.c_int
        kernel32.QueryInformationJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        kernel32.QueryInformationJobObject.restype = ctypes.c_int
        kernel32.AssignProcessToJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        kernel32.AssignProcessToJobObject.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int

    def assign(self, process: multiprocessing.Process) -> None:
        if self._kernel32 is None:
            raise WorkerError("El aislamiento de recursos requiere Windows")
        handle = self._kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise WorkerError("No se pudo crear el límite de recursos")
        self._handle = handle
        information = _ExtendedLimitInformation()
        information.BasicLimitInformation.LimitFlags = EXPECTED_JOB_LIMITS.flags
        information.BasicLimitInformation.ActiveProcessLimit = (
            EXPECTED_JOB_LIMITS.active_processes
        )
        information.ProcessMemoryLimit = EXPECTED_JOB_LIMITS.process_memory_bytes
        information.JobMemoryLimit = EXPECTED_JOB_LIMITS.job_memory_bytes
        updated = self._kernel32.SetInformationJobObject(
            handle,
            int(JobInformationClass.EXTENDED_LIMIT_INFORMATION),
            ctypes.byref(information),
            ctypes.sizeof(information),
        )
        if not updated:
            self.close()
            raise WorkerError("No se pudo configurar el límite de recursos")
        try:
            self.verify_limits()
        except WorkerError:
            self.close()
            raise
        process_handle = getattr(process, "sentinel", None)
        if not process_handle:
            self.close()
            raise WorkerError("El worker no tiene un handle de proceso válido")
        assigned = self._kernel32.AssignProcessToJobObject(handle, process_handle)
        if not assigned:
            self.close()
            raise WorkerError("No se pudo aislar el worker de recursos")

    def query_limits(self) -> JobLimits:
        kernel32 = self._kernel32
        if kernel32 is None or self._handle is None:
            raise WorkerError("El límite de recursos no está configurado")
        information = _ExtendedLimitInformation()
        queried = kernel32.QueryInformationJobObject(
            self._handle,
            int(JobInformationClass.EXTENDED_LIMIT_INFORMATION),
            ctypes.byref(information),
            ctypes.sizeof(information),
        )
        if not queried:
            raise WorkerError("No se pudo consultar el límite de recursos")
        return JobLimits(
            flags=int(information.BasicLimitInformation.LimitFlags),
            active_processes=int(information.BasicLimitInformation.ActiveProcessLimit),
            process_memory_bytes=int(information.ProcessMemoryLimit),
            job_memory_bytes=int(information.JobMemoryLimit),
        )

    def verify_limits(self) -> None:
        if self.query_limits() != EXPECTED_JOB_LIMITS:
            raise WorkerError("El límite de recursos no coincide con la política")

    def close(self) -> None:
        if self._handle is not None and self._kernel32 is not None:
            self._kernel32.CloseHandle(self._handle)
        self._handle = None


def run_bounded(
    target: Callable[..., None],
    arguments: tuple[object, ...],
    timeout_seconds: float,
    max_result_bytes: int = DEFAULT_MAX_RESULT_BYTES,
    temp_root: Path | None = None,
) -> str:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=True)
    with tempfile.TemporaryDirectory(
        prefix="doc2md-worker-",
        dir=str(temp_root) if temp_root is not None else None,
    ) as work_dir:
        result_path = Path(work_dir) / "result.txt"
        process = context.Process(
            target=_worker_entry,
            args=(target, arguments, result_path, sender),
            daemon=True,
        )
        deadline = time.monotonic() + timeout_seconds
        job = WindowsJob()
        try:
            process.start()
            # El handshake ocurre dentro del worker: ningún trabajo ni descendiente
            # empieza antes de que el proceso quede asignado al Job Object.
            job.assign(process)
            message = _wait_for_worker(
                process,
                receiver,
                result_path,
                max_result_bytes,
                deadline,
                timeout_seconds,
            )
            _join_worker(process, message, job, deadline)
            return _read_result(result_path, max_result_bytes)
        except EOFError as error:
            raise WorkerError(
                f"El worker cerró el canal sin resultado (código {process.exitcode})"
            ) from error
        finally:
            _cleanup_worker(receiver, sender, process, job)


def _wait_for_worker(
    process: multiprocessing.Process,
    receiver: Connection,
    result_path: Path,
    max_result_bytes: int,
    deadline: float,
    timeout_seconds: float,
) -> str:
    while True:
        if receiver.poll(0.1):
            message = receiver.recv()
            if message == "ready":
                receiver.send("release")
                continue
            return message
        if result_path.exists() and result_path.stat().st_size > max_result_bytes:
            _stop_process(process)
            raise WorkerError("El resultado del worker excede el límite permitido")
        if not process.is_alive():
            process.join()
            raise WorkerError(
                f"El worker terminó sin resultado (código {process.exitcode})"
            )
        if time.monotonic() >= deadline:
            _stop_process(process)
            raise WorkerError(f"El worker excedió {timeout_seconds:g} segundos")


def _join_worker(
    process: multiprocessing.Process,
    message: str,
    job: WindowsJob,
    deadline: float,
) -> None:
    process.join(max(0.0, deadline - time.monotonic()))
    if process.pid is not None and process.is_alive():
        _stop_process(process)
        raise WorkerError("El worker no terminó después de enviar el resultado")
    job.close()
    _raise_worker_error(message)


def _read_result(result_path: Path, max_result_bytes: int) -> str:
    if not result_path.is_file():
        raise WorkerError("El worker no generó el archivo de resultado")
    if result_path.stat().st_size > max_result_bytes:
        raise WorkerError("El resultado del worker excede el límite permitido")
    return result_path.read_bytes().decode("utf-8")


def _cleanup_worker(
    receiver: Connection,
    sender: Connection,
    process: multiprocessing.Process,
    job: WindowsJob,
) -> None:
    receiver.close()
    sender.close()
    if process.pid is not None and process.is_alive():
        _stop_process(process)
    job.close()


def _worker_entry(
    target: Callable[..., None],
    arguments: tuple[object, ...],
    result_path: Path,
    sender: Connection,
) -> None:
    try:
        sender.send("ready")
        if sender.recv() != "release":
            raise RuntimeError("El worker no recibió la autorización de inicio")
        target(result_path, *arguments)
        sender.send("done")
    except Exception as error:
        message = f"{type(error).__name__}: {error}"[:MAX_ERROR_CHARACTERS]
        sender.send(f"error:{message}")


def _stop_process(process: multiprocessing.Process) -> None:
    if process.pid is None or not process.is_alive():
        process.join()
        return
    process.terminate()
    process.join(WORKER_TERMINATION_SECONDS)
    if process.is_alive():
        process.kill()
        process.join()


def _raise_worker_error(message: str) -> None:
    if not message.startswith("error:"):
        return
    error = message.removeprefix("error:")
    error_type, separator, details = error.partition(": ")
    if not separator:
        raise WorkerError(error)
    if error_type == "ValueError":
        raise ValueError(details)
    if error_type in {"FileNotFoundError", "PermissionError", "OSError"}:
        raise OSError(details)
    raise WorkerError(error)
