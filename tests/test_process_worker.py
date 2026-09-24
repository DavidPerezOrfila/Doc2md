from pathlib import Path
import ctypes
import multiprocessing
import subprocess
import sys
import tempfile
import time
import unittest

from doc2md.process_worker import EXPECTED_JOB_LIMITS, WindowsJob, run_bounded


def write_large_result(result_path: Path) -> None:
    result_path.write_text("x" * (1024 * 1024), encoding="utf-8")


def write_oversized_result(result_path: Path) -> None:
    result_path.write_text("x" * 2048, encoding="utf-8")


def slow_result(result_path: Path) -> None:
    time.sleep(5)
    result_path.write_text("late", encoding="utf-8")


def spawn_descendant(result_path: Path, pid_path: Path) -> None:
    child_code = (
        "from pathlib import Path; import os,time; "
        f"Path({str(pid_path)!r}).write_text(str(os.getpid())); time.sleep(5)"
    )
    subprocess.Popen([sys.executable, "-c", child_code])
    time.sleep(5)


def process_is_running(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    exit_code = ctypes.c_ulong()
    kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
    kernel32.CloseHandle(handle)
    return exit_code.value == 259


class ProcessWorkerTests(unittest.TestCase):
    def test_transports_result_larger_than_pipe_buffer(self) -> None:
        result = run_bounded(write_large_result, (), timeout_seconds=5)

        self.assertEqual(len(result), 1024 * 1024)

    def test_rejects_oversized_result(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "resultado"):
            run_bounded(
                write_oversized_result,
                (),
                timeout_seconds=5,
                max_result_bytes=1024,
            )

    def test_job_object_applies_configured_limits(self) -> None:
        context = multiprocessing.get_context("spawn")
        process = context.Process(target=time.sleep, args=(30,), daemon=True)
        process.start()
        job = WindowsJob()
        try:
            job.assign(process)
            job.verify_limits()
            self.assertEqual(job.query_limits(), EXPECTED_JOB_LIMITS)
        finally:
            job.close()
            if process.is_alive():
                process.kill()
            process.join()

    def test_job_object_kills_descendant_processes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            pid_path = root / "descendant.pid"
            with self.assertRaisesRegex(RuntimeError, "excedió"):
                run_bounded(
                    spawn_descendant,
                    (pid_path,),
                    timeout_seconds=2,
                    temp_root=root,
                )

            pid = int(pid_path.read_text(encoding="utf-8"))
            deadline = time.monotonic() + 2
            while process_is_running(pid) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertFalse(process_is_running(pid))

    def test_timeout_cleans_parent_owned_work_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            with self.assertRaisesRegex(RuntimeError, "excedió"):
                run_bounded(
                    slow_result,
                    (),
                    timeout_seconds=0.05,
                    temp_root=Path(temp_root),
                )

            self.assertEqual(list(Path(temp_root).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
