#!/usr/bin/env python3
"""Stage original Linux QMI codec and exact ath11k identity descriptors."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TABLES = [
    'qmi_wlanfw_cap_req_msg_v01_ei', 'qmi_wlanfw_device_info_req_msg_v01_ei',
    'qmi_wlfw_device_info_resp_msg_v01_ei', 'qmi_wlanfw_rf_chip_info_s_v01_ei',
    'qmi_wlanfw_rf_board_info_s_v01_ei', 'qmi_wlanfw_soc_info_s_v01_ei',
    'qmi_wlanfw_fw_version_info_s_v01_ei', 'qmi_wlanfw_cap_resp_msg_v01_ei',
]
WRAPPER = r'''
#include "qmi.h"
#include "nw_wcn6750_qmi.h"
/* Exact descriptor definitions from the pinned original qmi.c follow. */
@TABLES@
unsigned nw_wcn6750_query_timeout_ms(void) { return ATH11K_QMI_WLANFW_TIMEOUT_MS; }
int nw_wcn6750_query_request(unsigned message, unsigned transaction, uint8_t *out, size_t capacity) {
    const struct qmi_elem_info *ei;
    if (message == QMI_WLANFW_CAP_REQ_V01) ei = qmi_wlanfw_cap_req_msg_v01_ei;
    else if (message == QMI_WLANFW_DEVICE_INFO_REQ_V01) ei = qmi_wlanfw_device_info_req_msg_v01_ei;
    else return -EOPNOTSUPP;
    size_t length = 0;
    void *encoded = qmi_encode_message(QMI_REQUEST, message, &length, transaction, ei, NULL);
    if (IS_ERR(encoded)) return PTR_ERR(encoded);
    if (length > capacity) { kfree(encoded); return -EMSGSIZE; }
    memcpy(out, encoded, length); kfree(encoded); return (int)length;
}
/* The original decoder assumes complete TLV headers and reads scalar
 * fields at their descriptor widths. Check the wire bounds before it runs. */
static int response_bounds(unsigned message, const uint8_t *data, size_t length) {
    if (length < sizeof(struct qmi_header)) return -EINVAL;
    size_t left = length - sizeof(struct qmi_header);
    if (left != ((size_t)data[5] | (size_t)data[6] << 8)) return -EINVAL;
    data += sizeof(struct qmi_header);
    while (left) {
        if (left < 3) return -EINVAL;
        unsigned type = data[0];
        size_t bytes = (size_t)data[1] | (size_t)data[2] << 8;
        data += 3;
        left -= 3;
        if (bytes > left) return -EINVAL;
        size_t exact = 0;
        if (type == 2) exact = 4;
        else if (message == QMI_WLANFW_DEVICE_INFO_REQ_V01) {
            if (type == 0x10) exact = 8;
            if (type == 0x11) exact = 4;
        } else {
            if (type == 0x10) exact = 8;
            if (type == 0x11 || type == 0x12 || (type >= 0x16 && type <= 0x19)) exact = 4;
            if (type == 0x15) exact = 1;
            if (type == 0x13 &&
                (bytes < 5 || data[4] > ATH11K_QMI_WLANFW_MAX_TIMESTAMP_LEN_V01 || bytes != 5u + data[4]))
                return -EINVAL;
            if (type == 0x14 && bytes > ATH11K_QMI_WLANFW_MAX_BUILD_ID_LEN_V01) return -EINVAL;
        }
        if (exact && bytes != exact) return -EINVAL;
        data += bytes;
        left -= bytes;
    }
    return 0;
}
int nw_wcn6750_query_decode(unsigned message, const uint8_t *data, size_t length, struct nw_wcn6750_identity *out) {
    if (response_bounds(message, data, length)) return -EINVAL;
    int rc;
    if (message == QMI_WLANFW_CAP_RESP_V01) {
        struct qmi_wlanfw_cap_resp_msg_v01 response = {};
        rc = qmi_decode_message(data, length, qmi_wlanfw_cap_resp_msg_v01_ei, &response);
        if (rc < 0) return rc;
        out->result = response.resp.result; out->error = response.resp.error;
        if (out->result) return -EIO;
        if (response.chip_info_valid) { out->valid |= NW_WCN6750_CHIP; out->chip_id = response.chip_info.chip_id; out->chip_family = response.chip_info.chip_family; }
        if (response.board_info_valid) { out->valid |= NW_WCN6750_BOARD; out->board_id = response.board_info.board_id; }
        if (response.soc_info_valid) { out->valid |= NW_WCN6750_SOC; out->soc_id = response.soc_info.soc_id; }
        if (response.fw_version_info_valid) { out->valid |= NW_WCN6750_VERSION; out->fw_version = response.fw_version_info.fw_version; memcpy(out->timestamp, response.fw_version_info.fw_build_timestamp, sizeof out->timestamp); out->timestamp[32] = 0; }
        if (response.fw_build_id_valid) { out->valid |= NW_WCN6750_BUILD; memcpy(out->build_id, response.fw_build_id, sizeof out->build_id); out->build_id[128] = 0; }
        return 0;
    }
    if (message == QMI_WLANFW_DEVICE_INFO_REQ_V01) {
        struct qmi_wlanfw_device_info_resp_msg_v01 response = {};
        rc = qmi_decode_message(data, length, qmi_wlfw_device_info_resp_msg_v01_ei, &response);
        if (rc < 0) return rc;
        out->result = response.resp.result; out->error = response.resp.error;
        if (out->result) return -EIO;
        if (!response.bar_addr_valid || !response.bar_size_valid || !response.bar_addr || response.bar_size != ATH11K_QMI_DEVICE_BAR_SIZE) return -EINVAL;
        out->valid |= NW_WCN6750_BAR; out->bar_address = response.bar_addr; out->bar_size = response.bar_size;
        return 0;
    }
    return -EOPNOTSUPP;
}
'''


def main():
    subprocess.run(['python3', str(ROOT / 'tools/fetch-sources.py'), '--check'], check=True)
    subprocess.run(['bash', str(ROOT / 'tools/pin-headers.sh')], check=True)
    subprocess.run(['python3', str(ROOT / 'tools/prepare-ath11k.py')], check=True)
    source = ROOT / 'deps/linux/drivers/net/wireless/ath/ath11k/qmi.c'
    text = source.read_text()
    blocks = []
    for name in TABLES:
        match = re.search(r'static const struct qmi_elem_info ' + name + r'\[\] = \{.*?^\};', text, re.M | re.S)
        if not match:
            raise SystemExit('original descriptor not found: ' + name)
        blocks.append(match.group())
    output = ROOT / 'out/wcn6750-qmi'
    output.mkdir(parents=True, exist_ok=True)
    generated = WRAPPER.replace('@TABLES@', '\n\n'.join(blocks))
    (output / 'Wcn6750Qmi.c').write_text(generated)
    codec = ROOT / 'deps/linux/drivers/soc/qcom/qmi_encdec.c'
    (output / 'identity.json').write_text(json.dumps({
        'linux_revision': json.loads((ROOT / 'tools/source-lock.json').read_text())['linux']['commit'],
        'qmi_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'codec_source_sha256': hashlib.sha256(codec.read_bytes()).hexdigest(),
        'descriptor_names': TABLES, 'descriptors_modified': False,
        'generated_sha256': hashlib.sha256(generated.encode()).hexdigest(),
        'purpose': 'read-only CAP and DEVICE_INFO board discovery before ath11k data-path integration',
    }, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
    main()
