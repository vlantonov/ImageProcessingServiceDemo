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
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <stdexcept>

#ifdef __SSE2__
#include <emmintrin.h>
#endif

namespace py = pybind11;

namespace fast_resize {

constexpr float MAX_CHANNEL_VALUE = 255.0F;

// ── SSE2 SIMD path ─────────────────────────────────────────────────────────

#ifdef __SSE2__

/// Unpack the low 4 bytes of a 128-bit int register to 4 floats.
static inline __m128 unpack_u8x4_to_ps(__m128i packed) {
    const __m128i zero = _mm_setzero_si128();
    const __m128i i16 = _mm_unpacklo_epi8(packed, zero);
    const __m128i i32 = _mm_unpacklo_epi16(i16, zero);
    return _mm_cvtepi32_ps(i32);
}

/// Pack 4 floats (clamped to [0,255]) to the low 4 bytes of a 128-bit int register.
static inline __m128i pack_ps_to_u8x4(__m128 values) {
    values = _mm_max_ps(
        _mm_min_ps(values, _mm_set1_ps(MAX_CHANNEL_VALUE)), _mm_setzero_ps());
    const __m128i i32 = _mm_cvttps_epi32(values);
    const __m128i i16 = _mm_packs_epi32(i32, i32);
    return _mm_packus_epi16(i16, i16);
}

/// Load channels bytes (3 or 4) from ptr into the low bytes of __m128i.
static inline __m128i load_pixel(const uint8_t* ptr, int num_channels) {
    int32_t val = 0;
    std::memcpy(&val, ptr, static_cast<size_t>(num_channels));
    return _mm_cvtsi32_si128(val);
}

static void bilinear_resize_sse2(
    const uint8_t* src, int src_w,
    int src_h,  // NOLINT(bugprone-easily-swappable-parameters)
    int num_channels,
    uint8_t* dst, int dst_w, int dst_h)
{
    const auto col_stride = static_cast<ptrdiff_t>(num_channels);
    const float x_ratio = static_cast<float>(src_w) / static_cast<float>(dst_w);
    const float y_ratio = static_cast<float>(src_h) / static_cast<float>(dst_h);

    for (int dst_y = 0; dst_y < dst_h; ++dst_y) {
        const float src_y = static_cast<float>(dst_y) * y_ratio;
        const int row_top = static_cast<int>(src_y);
        const int row_bot = std::min(row_top + 1, src_h - 1);
        const float frac_y = src_y - static_cast<float>(row_top);
        const __m128 frac_y_v = _mm_set1_ps(frac_y);
        const __m128 one_minus_fy = _mm_set1_ps(1.0F - frac_y);

        const auto top_row_off = static_cast<ptrdiff_t>(row_top) * src_w;
        const auto bot_row_off = static_cast<ptrdiff_t>(row_bot) * src_w;

        for (int dst_x = 0; dst_x < dst_w; ++dst_x) {
            const float src_x = static_cast<float>(dst_x) * x_ratio;
            const int col_left = static_cast<int>(src_x);
            const int col_right = std::min(col_left + 1, src_w - 1);
            const float frac_x = src_x - static_cast<float>(col_left);
            const __m128 frac_x_v = _mm_set1_ps(frac_x);
            const __m128 one_minus_fx = _mm_set1_ps(1.0F - frac_x);

            // Load four corner pixels and unpack to float
            const __m128 top_left = unpack_u8x4_to_ps(
                load_pixel(src + ((top_row_off + col_left) * col_stride), num_channels));
            const __m128 top_right = unpack_u8x4_to_ps(
                load_pixel(src + ((top_row_off + col_right) * col_stride), num_channels));
            const __m128 bot_left = unpack_u8x4_to_ps(
                load_pixel(src + ((bot_row_off + col_left) * col_stride), num_channels));
            const __m128 bot_right = unpack_u8x4_to_ps(
                load_pixel(src + ((bot_row_off + col_right) * col_stride), num_channels));

            // Bilinear interpolation on all channels simultaneously
            const __m128 top = _mm_add_ps(
                _mm_mul_ps(top_left, one_minus_fx), _mm_mul_ps(top_right, frac_x_v));
            const __m128 bottom = _mm_add_ps(
                _mm_mul_ps(bot_left, one_minus_fx), _mm_mul_ps(bot_right, frac_x_v));
            const __m128 result = _mm_add_ps(
                _mm_mul_ps(top, one_minus_fy), _mm_mul_ps(bottom, frac_y_v));

            // Pack back to uint8 and store
            const int32_t pixel_packed = _mm_cvtsi128_si32(pack_ps_to_u8x4(result));
            const auto dst_off =
                (static_cast<ptrdiff_t>(dst_y) * dst_w + dst_x) * col_stride;
            std::memcpy(dst + dst_off, &pixel_packed, static_cast<size_t>(num_channels));
        }
    }
}

#endif  // __SSE2__

// ── Scalar fallback ─────────────────────────────────────────────────────────

#ifndef __SSE2__

static void bilinear_resize_scalar(
    const uint8_t* src, int src_w,
    int src_h,  // NOLINT(bugprone-easily-swappable-parameters)
    int num_channels,
    uint8_t* dst, int dst_w, int dst_h)
{
    const float x_ratio = static_cast<float>(src_w) / static_cast<float>(dst_w);
    const float y_ratio = static_cast<float>(src_h) / static_cast<float>(dst_h);

    for (int dst_y = 0; dst_y < dst_h; ++dst_y) {
        const float src_y = static_cast<float>(dst_y) * y_ratio;
        const int row_top = static_cast<int>(src_y);
        const int row_bot = std::min(row_top + 1, src_h - 1);
        const float frac_y = src_y - static_cast<float>(row_top);

        for (int dst_x = 0; dst_x < dst_w; ++dst_x) {
            const float src_x = static_cast<float>(dst_x) * x_ratio;
            const int col_left = static_cast<int>(src_x);
            const int col_right = std::min(col_left + 1, src_w - 1);
            const float frac_x = src_x - static_cast<float>(col_left);

            for (int chan = 0; chan < num_channels; ++chan) {
                const float top_left =
                    src[(row_top * src_w + col_left) * num_channels + chan];
                const float top_right =
                    src[(row_top * src_w + col_right) * num_channels + chan];
                const float bot_left =
                    src[(row_bot * src_w + col_left) * num_channels + chan];
                const float bot_right =
                    src[(row_bot * src_w + col_right) * num_channels + chan];

                const float top    = top_left + frac_x * (top_right - top_left);
                const float bottom = bot_left + frac_x * (bot_right - bot_left);
                const float value  = top + frac_y * (bottom - top);

                dst[(dst_y * dst_w + dst_x) * num_channels + chan] =
                    static_cast<uint8_t>(std::clamp(value, 0.0F, MAX_CHANNEL_VALUE));
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
    const py::array_t<uint8_t, py::array::c_style | py::array::forcecast>& src,
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

// NOLINTNEXTLINE(readability-identifier-length)
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
