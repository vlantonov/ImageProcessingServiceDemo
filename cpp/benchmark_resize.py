"""Benchmark Pillow thumbnailing vs pybind11 C++ resize backend.

Usage:
    python cpp/benchmark_resize.py
"""

from __future__ import annotations

import io
import statistics
import sys
import time
from pathlib import Path

from PIL import Image as PILImage

ITERATIONS = 25
MAX_SIZE = (256, 256)
SOURCE_SIZE = (4096, 3072)


def _build_source_image_bytes() -> bytes:
    image = PILImage.effect_noise(SOURCE_SIZE, 64.0).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _run_benchmark(name: str, fn, image_data: bytes) -> list[float]:
    latencies_ms: list[float] = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        result = fn(image_data, MAX_SIZE)
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies_ms.append(elapsed_ms)
        if result["width"] > MAX_SIZE[0] or result["height"] > MAX_SIZE[1]:
            raise RuntimeError(f"{name} produced out-of-bounds thumbnail")
    return latencies_ms


def _summarize(latencies_ms: list[float]) -> tuple[float, float]:
    median = statistics.median(latencies_ms)
    p95_index = min(len(latencies_ms) - 1, int(len(latencies_ms) * 0.95))
    p95 = sorted(latencies_ms)[p95_index]
    return median, p95


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from src.infrastructure.processing.cpp_processor import _generate_thumbnail_cpp_sync
    from src.infrastructure.processing.pillow_processor import _generate_thumbnail_sync

    cpp_build_path = repo_root / "cpp" / "build"
    if cpp_build_path.exists():
        sys.path.insert(0, str(cpp_build_path))

    source_image = _build_source_image_bytes()
    pillow_latencies = _run_benchmark("Pillow", _generate_thumbnail_sync, source_image)
    cpp_latencies = _run_benchmark("C++", _generate_thumbnail_cpp_sync, source_image)

    pillow_median, pillow_p95 = _summarize(pillow_latencies)
    cpp_median, cpp_p95 = _summarize(cpp_latencies)
    speedup = pillow_median / cpp_median

    print("Resize benchmark (4096x3072 PNG -> 256x256 max, 25 iterations)")
    print("")
    print("| Backend | Median (ms) | P95 (ms) |")
    print("|---|---:|---:|")
    print(f"| Pillow | {pillow_median:.2f} | {pillow_p95:.2f} |")
    print(f"| C++ pybind11 | {cpp_median:.2f} | {cpp_p95:.2f} |")
    print("")
    print(f"Speedup (median): {speedup:.2f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
