/**
 * fast_resize — C++ performance-critical image resize module.
 *
 * Demonstrates the "Nice-to-Have" C++ skill: a pybind11-wrapped module
 * for bilinear interpolation resize, significantly faster than pure-Python
 * for large images in tight loops.
 *
 * Features:
 *   - SSE2 SIMD for parallel per-pixel channel interpolation (x86-64)
 *   - Zero-copy I/O via NumPy arrays (no Python list conversion overhead)
 *   - Scalar fallback for non-x86 architectures
 *
 * Build:
 *   pip install pybind11 numpy
 *   c++ -O3 -Wall -shared -std=c++17 -fPIC -march=native \
 *       $(python3 -m pybind11 --includes) \
 *       fast_resize.cpp -o fast_resize$(python3-config --extension-suffix)
 */

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <stdexcept>

#ifdef __SSE2__
#include <emmintrin.h>
#endif

namespace py = pybind11;

namespace fast_resize {

// ── SSE2 SIMD path ─────────────────────────────────────────────────────────

#ifdef __SSE2__

/// Unpack the low 4 bytes of a 128-bit int register to 4 floats.
static inline __m128 unpack_u8x4_to_ps(__m128i v) {
    const __m128i zero = _mm_setzero_si128();
    const __m128i i16 = _mm_unpacklo_epi8(v, zero);
    const __m128i i32 = _mm_unpacklo_epi16(i16, zero);
    return _mm_cvtepi32_ps(i32);
}

/// Pack 4 floats (clamped to [0,255]) to the low 4 bytes of a 128-bit int register.
static inline __m128i pack_ps_to_u8x4(__m128 v) {
    v = _mm_max_ps(_mm_min_ps(v, _mm_set1_ps(255.0f)), _mm_setzero_ps());
    const __m128i i32 = _mm_cvttps_epi32(v);
    const __m128i i16 = _mm_packs_epi32(i32, i32);
    return _mm_packus_epi16(i16, i16);
}

/// Load channels bytes (3 or 4) from ptr into the low bytes of __m128i.
static inline __m128i load_pixel(const uint8_t* ptr, int channels) {
    int32_t val = 0;
    std::memcpy(&val, ptr, static_cast<size_t>(channels));
    return _mm_cvtsi32_si128(val);
}

static void bilinear_resize_sse2(
    const uint8_t* src, int src_w, int src_h, int channels,
    uint8_t* dst, int dst_w, int dst_h)
{
    const float x_ratio = static_cast<float>(src_w) / static_cast<float>(dst_w);
    const float y_ratio = static_cast<float>(src_h) / static_cast<float>(dst_h);

    for (int dy = 0; dy < dst_h; ++dy) {
        const float src_y = dy * y_ratio;
        const int y0 = static_cast<int>(src_y);
        const int y1 = std::min(y0 + 1, src_h - 1);
        const float fy = src_y - static_cast<float>(y0);
        const __m128 fy_v = _mm_set1_ps(fy);
        const __m128 one_minus_fy = _mm_set1_ps(1.0f - fy);

        const int y0_off = y0 * src_w;
        const int y1_off = y1 * src_w;

        for (int dx = 0; dx < dst_w; ++dx) {
            const float src_x = dx * x_ratio;
            const int x0 = static_cast<int>(src_x);
            const int x1 = std::min(x0 + 1, src_w - 1);
            const float fx = src_x - static_cast<float>(x0);
            const __m128 fx_v = _mm_set1_ps(fx);
            const __m128 one_minus_fx = _mm_set1_ps(1.0f - fx);

            // Load four corner pixels and unpack to float
            const __m128 tl = unpack_u8x4_to_ps(
                load_pixel(src + (y0_off + x0) * channels, channels));
            const __m128 tr = unpack_u8x4_to_ps(
                load_pixel(src + (y0_off + x1) * channels, channels));
            const __m128 bl = unpack_u8x4_to_ps(
                load_pixel(src + (y1_off + x0) * channels, channels));
            const __m128 br = unpack_u8x4_to_ps(
                load_pixel(src + (y1_off + x1) * channels, channels));

            // Bilinear interpolation on all channels simultaneously
            const __m128 top = _mm_add_ps(
                _mm_mul_ps(tl, one_minus_fx), _mm_mul_ps(tr, fx_v));
            const __m128 bottom = _mm_add_ps(
                _mm_mul_ps(bl, one_minus_fx), _mm_mul_ps(br, fx_v));
            const __m128 result = _mm_add_ps(
                _mm_mul_ps(top, one_minus_fy), _mm_mul_ps(bottom, fy_v));

            // Pack back to uint8 and store
            const int32_t packed = _mm_cvtsi128_si32(pack_ps_to_u8x4(result));
            uint8_t* dst_pixel = dst + (dy * dst_w + dx) * channels;
            std::memcpy(dst_pixel, &packed, static_cast<size_t>(channels));
        }
    }
}

#endif  // __SSE2__

// ── Scalar fallback ─────────────────────────────────────────────────────────

#ifndef __SSE2__

static void bilinear_resize_scalar(
    const uint8_t* src, int src_w, int src_h, int channels,
    uint8_t* dst, int dst_w, int dst_h)
{
    const float x_ratio = static_cast<float>(src_w) / static_cast<float>(dst_w);
    const float y_ratio = static_cast<float>(src_h) / static_cast<float>(dst_h);

    for (int dy = 0; dy < dst_h; ++dy) {
        const float src_y = dy * y_ratio;
        const int y0 = static_cast<int>(src_y);
        const int y1 = std::min(y0 + 1, src_h - 1);
        const float fy = src_y - static_cast<float>(y0);

        for (int dx = 0; dx < dst_w; ++dx) {
            const float src_x = dx * x_ratio;
            const int x0 = static_cast<int>(src_x);
            const int x1 = std::min(x0 + 1, src_w - 1);
            const float fx = src_x - static_cast<float>(x0);

            for (int c = 0; c < channels; ++c) {
                const float tl = src[(y0 * src_w + x0) * channels + c];
                const float tr = src[(y0 * src_w + x1) * channels + c];
                const float bl = src[(y1 * src_w + x0) * channels + c];
                const float br = src[(y1 * src_w + x1) * channels + c];

                const float top    = tl + fx * (tr - tl);
                const float bottom = bl + fx * (br - bl);
                const float value  = top + fy * (bottom - top);

                dst[(dy * dst_w + dx) * channels + c] =
                    static_cast<uint8_t>(std::clamp(value, 0.0f, 255.0f));
            }
        }
    }
}

#endif  // !__SSE2__

// ── Public API ──────────────────────────────────────────────────────────────

/**
 * Bilinear interpolation resize for 8-bit RGB/RGBA images.
 *
 * Accepts and returns NumPy uint8 arrays (zero-copy, no Python list overhead).
 * Uses SSE2 intrinsics on x86-64 to interpolate all channels in parallel.
 *
 * @param src       Flat pixel buffer (row-major, channels interleaved)
 * @param src_w     Source width
 * @param src_h     Source height
 * @param channels  3 (RGB) or 4 (RGBA)
 * @param dst_w     Target width
 * @param dst_h     Target height
 * @return          Resized flat pixel buffer as NumPy uint8 array
 */
py::array_t<uint8_t> bilinear_resize(
    py::array_t<uint8_t, py::array::c_style | py::array::forcecast> src,
    int src_w, int src_h, int channels,
    int dst_w, int dst_h)
{
    if (channels != 3 && channels != 4) {
        throw std::invalid_argument("channels must be 3 (RGB) or 4 (RGBA)");
    }
    if (src_w <= 0 || src_h <= 0 || dst_w <= 0 || dst_h <= 0) {
        throw std::invalid_argument("dimensions must be positive");
    }

    const auto buf = src.request();
    const auto expected = static_cast<py::ssize_t>(src_w) * src_h * channels;
    if (buf.size != expected) {
        throw std::invalid_argument("src buffer size mismatch");
    }

    const auto* src_data = static_cast<const uint8_t*>(buf.ptr);

    // Allocate output NumPy array — caller receives it with zero copy
    const auto dst_size = static_cast<py::ssize_t>(dst_w) * dst_h * channels;
    py::array_t<uint8_t> dst(dst_size);
    auto* dst_data = static_cast<uint8_t*>(dst.request().ptr);

#ifdef __SSE2__
    bilinear_resize_sse2(src_data, src_w, src_h, channels, dst_data, dst_w, dst_h);
#else
    bilinear_resize_scalar(src_data, src_w, src_h, channels, dst_data, dst_w, dst_h);
#endif

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
          "Bilinear interpolation resize for 8-bit RGB/RGBA pixel buffers.\n\n"
          "Accepts and returns NumPy uint8 arrays for zero-copy I/O.");

    m.def("fit_dimensions", &fast_resize::fit_dimensions,
          py::arg("src_w"), py::arg("src_h"),
          py::arg("max_w"), py::arg("max_h"),
          "Compute dimensions that fit within a bounding box, preserving aspect ratio.");
}
