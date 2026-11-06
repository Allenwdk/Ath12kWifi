#ifndef NW_PORTABLE_CRYPTO_INCLUDES_H
#define NW_PORTABLE_CRYPTO_INCLUDES_H
#include "lx.h"
/* The portable crypto sources are shared with wpa_supplicant, whose os_*
 * helpers are plain libc wrappers in this kernel build. */
#ifndef NW_PORTABLE_CRYPTO_OS
#define NW_PORTABLE_CRYPTO_OS
#define os_memcpy memcpy
#define os_malloc(n) lx_alloc((n), 0)
#define os_zalloc(n) lx_alloc((n), 1)
#define os_free(p) lx_free(p)
#define os_memset memset
#define os_memcmp memcmp
static inline int os_memcmp_const(const void *a, const void *b, size_t n) { const u8 *x = a, *y = b; u8 r = 0; for (size_t i = 0; i < n; ++i) r |= (u8)(x[i] ^ y[i]); return r; }
#define WPA_GET_BE16(a) ((u16)(((a)[0] << 8) | (a)[1]))
#define WPA_GET_BE32(a) ((u32)(((u32)(a)[0] << 24) | ((u32)(a)[1] << 16) | ((u32)(a)[2] << 8) | (a)[3]))
#define WPA_PUT_BE16(a, v) do { (a)[0] = (u8)((v) >> 8); (a)[1] = (u8)(v); } while (0)
#define WPA_PUT_BE64(a, v) do { u64 _v = (u64)(v); for (int _i = 7; _i >= 0; --_i) { (a)[_i] = (u8)_v; _v >>= 8; } } while (0)
#define WPA_GET_LE16(a) ((u16)(((a)[1] << 8) | (a)[0]))
#define WPA_GET_LE32(a) ((u32)(((u32)(a)[3] << 24) | ((u32)(a)[2] << 16) | ((u32)(a)[1] << 8) | (a)[0]))
#define WPA_PUT_LE32(a, v) do { (a)[0] = (u8)(v); (a)[1] = (u8)((v) >> 8); (a)[2] = (u8)((v) >> 16); (a)[3] = (u8)((v) >> 24); } while (0)
#define WPA_PUT_BE32(a, v) do { (a)[0] = (u8)((v) >> 24); (a)[1] = (u8)((v) >> 16); (a)[2] = (u8)((v) >> 8); (a)[3] = (u8)(v); } while (0)
static inline void *os_memdup(const void *src, size_t n) { void *p = lx_alloc(n, 0); if (p) memcpy(p, src, n); return p; }
#ifndef TEST_FAIL
#define TEST_FAIL(...) 0
#define wpa_printf(...) do {} while (0)
#define wpa_hexdump_key(...) do {} while (0)
#define wpa_hexdump(...) do {} while (0)
#define forced_memzero(p, n) memset((p), 0, (n))
#define bin_clear_free(p, n) do { if (p) { memset((p), 0, (n)); lx_free(p); } } while (0)
#endif
#endif
#endif
