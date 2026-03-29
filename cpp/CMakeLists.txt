cmake_minimum_required(VERSION 3.16)
project(fast_resize LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(pybind11 REQUIRED)

pybind11_add_module(fast_resize fast_resize.cpp)
target_compile_options(fast_resize PRIVATE -O3 -Wall -Wextra -march=native)

install(TARGETS fast_resize DESTINATION .)
