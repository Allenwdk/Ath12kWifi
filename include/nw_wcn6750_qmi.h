/* SPDX-License-Identifier: BSD-2-Clause */
/* Read-only identity queries for WCN6750 board bring-up. The encoder,
 * decoder and field descriptors are taken from the locked Linux source.
 * This does not replace ath11k's firmware lifecycle or configure a radio. */
#ifndef NW_WCN6750_QMI_H
#define NW_WCN6750_QMI_H
#include <stddef.h>
#include <stdint.h>
struct nw_wcn6750_identity {
    uint32_t valid, chip_id, chip_family, board_id, soc_id, fw_version;
    uint64_t bar_address;
    uint32_t bar_size;
    uint16_t result, error;
    char timestamp[33], build_id[129];
};
enum { NW_WCN6750_CHIP = 1, NW_WCN6750_BOARD = 2, NW_WCN6750_SOC = 4,
       NW_WCN6750_VERSION = 8, NW_WCN6750_BUILD = 16, NW_WCN6750_BAR = 32 };
int nw_wcn6750_query_request(unsigned message, unsigned transaction, uint8_t *out, size_t capacity);
/* Caller first validates QMI header/transaction and a four-byte result TLV. */
int nw_wcn6750_query_decode(unsigned message, const uint8_t *data, size_t length,
                           struct nw_wcn6750_identity *identity);
unsigned nw_wcn6750_query_timeout_ms(void);
#endif
