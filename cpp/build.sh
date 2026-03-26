#!/usr/bin/env bash
# Build the C++ fast_resize module.
# Prerequisites: pip install pybind11 && apt-get install cmake g++
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"

mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

cmake .. -Dpybind11_DIR="$(python3 -c 'import pybind11; print(pybind11.get_cmake_dir())')"
cmake --build . --config Release -j "$(nproc)"

echo ""
echo "Build complete. Module:"
ls -la fast_resize*.so 2>/dev/null || ls -la fast_resize*.pyd 2>/dev/null
echo ""
echo "Copy the .so file to your Python path or src/ directory to use it."
