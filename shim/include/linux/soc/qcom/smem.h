/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef NW_LINUX_QCOM_SMEM_H
#define NW_LINUX_QCOM_SMEM_H
#include "lx_os.h"
#define QCOM_SMEM_HOST_ANY (-1)
/* Implemented by the selected board transport; no successful fallback. */
void *qcom_smem_get(unsigned host, unsigned item, size_t *size);
#endif
