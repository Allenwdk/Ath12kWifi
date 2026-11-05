/* Board-backed SMP2P state; no successful fallback. */
#ifndef NW_LINUX_SMEM_STATE_H
#define NW_LINUX_SMEM_STATE_H
#include "lx_ath.h"
struct qcom_smem_state *qcom_smem_state_get(struct device *dev, const char *con_id, unsigned *bit);
void qcom_smem_state_put(struct qcom_smem_state *state);
int qcom_smem_state_update_bits(struct qcom_smem_state *state, u32 mask, u32 value);
#endif
