/**
 * fast_resize — C++ performance-critical image resize module.
 *
 * Demonstrates the "Nice-to-Have" C++ skill: a pybind11-wrapped module
 * for bilinear interpolation resize, significantly faster than pure-Python
 * for large images in tight loops.
 *
 * Build:
 *   pip install pybind11
 *   c++ -O3 -Wall -shared -std=c++17 -fPIC \
 *       $(python3 -m pybind11 --includes) \
 *       fast_resize.cpp -o fast_resize$(python3-config --extension-suffix)
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace py = pybind11;

namespace fast_resize {

/**
 * Bilinear interpolation resize for 8-bit RGB/RGBA images.
 *
 * @param src       Flat pixel buffer (row-major, channels interleaved)
 * @param src_w     Source width
 * @param src_h     Source height
 * @param channels  3 (RGB) or 4 (RGBA)
 * @param dst_w     Target width
 * @param dst_h     Target height
 * @return          Resized flat pixel buffer
 */
std::vector<uint8_t> bilinear_resize(
    const std::vector<uint8_t>& src,
    int src_w, int src_h, int channels,
    int dst_w, int dst_h)
{
    if (channels != 3 && channels != 4) {
        throw std::invalid_argument("channels must be 3 (RGB) or 4 (RGBA)");
    }
    if (src_w <= 0 || src_h <= 0 || dst_w <= 0 || dst_h <= 0) {
        throw std::invalid_argument("dimensions must be positive");
    }
    if (static_cast<size_t>(src_w * src_h * channels) != src.size()) {
        throw std::invalid_argument("src buffer size mismatch");
    }

    std::vector<uint8_t> dst(static_cast<size_t>(dst_w) * dst_h * channels);

    const double x_ratio = static_cast<double>(src_w) / dst_w;
    const double y_ratio = static_cast<double>(src_h) / dst_h;

    for (int dy = 0; dy < dst_h; ++dy) {
        const double src_y = dy * y_ratio;
        const int y0 = static_cast<int>(std::floor(src_y));
        const int y1 = std::min(y0 + 1, src_h - 1);
        const double fy = src_y - y0;

        for (int dx = 0; dx < dst_w; ++dx) {
            const double src_x = dx * x_ratio;
            const int x0 = static_cast<int>(std::floor(src_x));
            const int x1 = std::min(x0 + 1, src_w - 1);
            const double fx = src_x - x0;

            for (int c = 0; c < channels; ++c) {
                const double top_left     = src[(y0 * src_w + x0) * channels + c];
                const double top_right    = src[(y0 * src_w + x1) * channels + c];
                const double bottom_left  = src[(y1 * src_w + x0) * channels + c];
                const double bottom_right = src[(y1 * src_w + x1) * channels + c];

                const double top    = top_left    + fx * (top_right    - top_left);
                const double bottom = bottom_left + fx * (bottom_right - bottom_left);
                const double value  = top + fy * (bottom - top);

                dst[(dy * dst_w + dx) * channels + c] =
                    static_cast<uint8_t>(std::clamp(value, 0.0, 255.0));
            }
        }
    }
    return dst;
}

/**
 * Fit image into a bounding box while preserving aspect ratio.
 * Returns (new_width, new_height).
 */
std::pair<int, int> fit_dimensions(int src_w, int src_h, int max_w, int max_h)
{
    if (src_w <= max_w && src_h <= max_h) {
        return {src_w, src_h};
    }
    const double scale = std::min(
        static_cast<double>(max_w) / src_w,
        static_cast<double>(max_h) / src_h
    );
    return {
        std::max(1, static_cast<int>(std::round(src_w * scale))),
        std::max(1, static_cast<int>(std::round(src_h * scale)))
    };
}

}  // namespace fast_resize


PYBIND11_MODULE(fast_resize, m) {
    m.doc() = "Performance-critical image resize operations in C++";

    m.def("bilinear_resize", &fast_resize::bilinear_resize,
          py::arg("src"), py::arg("src_w"), py::arg("src_h"),
          py::arg("channels"), py::arg("dst_w"), py::arg("dst_h"),
          "Bilinear interpolation resize for 8-bit RGB/RGBA pixel buffers.");

    m.def("fit_dimensions", &fast_resize::fit_dimensions,
          py::arg("src_w"), py::arg("src_h"),
          py::arg("max_w"), py::arg("max_h"),
          "Compute dimensions that fit within a bounding box, preserving aspect ratio.");
}
