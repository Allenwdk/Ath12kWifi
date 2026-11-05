/* Board-backed remoteproc API; no successful fallback. */
#ifndef NW_LINUX_REMOTEPROC_H
#define NW_LINUX_REMOTEPROC_H
#include "lx_ath.h"
struct rproc *rproc_get_by_phandle(u32 phandle);
int rproc_boot(struct rproc *rproc);
void rproc_shutdown(struct rproc *rproc);
void rproc_put(struct rproc *rproc);
#endif
