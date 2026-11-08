#!/usr/bin/env python3
"""Prepare the locked upstream ath11k core and WCN6750 AHB sources.

Protocol and hardware code is unchanged. Disabled trace points use the same
generated no-op declarations as the existing ath12k preparation. Build gaps
must be implemented in the shared compatibility layer or board callbacks.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def patch_board_staging(output: Path):
    """Board-side QMI trace: file id 0xff and one line per BDF segment. The
    upload itself stays the upstream segmented path."""
    path = output / 'qmi.c'
    text = path.read_text()
    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise SystemExit('ath11k qmi trace patch: pattern not unique')
        text = text.replace(old, new)
    replace('		req->file_id = ab->qmi.target.board_id;',
            '		req->file_id = 0xff; /* icnss2 sends 0xff: the CAP reply has no valid board id */')
    replace('''		ret = qmi_txn_init(&ab->qmi.handle, &txn,
				   qmi_wlanfw_bdf_download_resp_msg_v01_ei,
				   &resp);''',
            '''		ath11k_info(ab, "bdf seg type %u id %u total %u data %u end %u",
			    type, req->seg_id, req->total_size, req->data_len, req->end);
		ret = qmi_txn_init(&ab->qmi.handle, &txn,
				   qmi_wlanfw_bdf_download_resp_msg_v01_ei,
				   &resp);''')
    core = output / 'core.c'
    ctext = core.read_text()
    def creplace(old, new):
        nonlocal ctext
        if ctext.count(old) != 1:
            raise SystemExit('ath11k core trace patch: pattern not unique')
        ctext = ctext.replace(old, new)
    creplace('	ret = ath11k_qmi_firmware_start(ab, mode);',
             '	ath11k_info(ab, "fw ready: firmware_start");\n	ret = ath11k_qmi_firmware_start(ab, mode);')
    creplace('	ret = ath11k_ce_init_pipes(ab);',
             '	ath11k_info(ab, "fw ready: ce_init_pipes");\n	ret = ath11k_ce_init_pipes(ab);')
    creplace('	ret = ath11k_dp_alloc(ab);',
             '	ath11k_info(ab, "fw ready: dp_alloc");\n	ret = ath11k_dp_alloc(ab);')
    creplace('	ret = ath11k_core_start(ab);',
             '	ath11k_info(ab, "fw ready: core_start");\n	ret = ath11k_core_start(ab);')
    creplace('	ret = ath11k_core_pdev_create(ab);',
             '	ath11k_info(ab, "fw ready: pdev_create");\n	ret = ath11k_core_pdev_create(ab);')
    creplace('	ath11k_hif_irq_enable(ab);\n	mutex_unlock(&ab->core_lock);',
             '	ath11k_info(ab, "fw ready: irq_enable");\n	ath11k_hif_irq_enable(ab);\n	mutex_unlock(&ab->core_lock);\n	ath11k_info(ab, "fw ready: done");')
    # WCN6750 power save. The stock firmware asserts in
    # whal_wmac_recipes.c:whal_wmac_transition_to_fw_control as soon as the first
    # vdev exists, and that file is the MAC low power recipe: its neighbours in
    # the firmware's own string table are whal_wmac_phy_off_check,
    # whal_wmac_h2s_grant_check ("Polling H2S_GRANT_ISSUED failed") and the
    # IMPS / HW-DTIM enter messages. ath11k asks for IDLE_PS at the end of
    # ath11k_mac_op_start, i.e. before any interface exists, so the firmware is
    # already allowed into that recipe when the vdev appears. This port has no
    # APPS side of the H2S handshake, so the recipe cannot complete. Upstream
    # sets idle_ps = true for this chip; keep it off until the handshake
    # exists, and record why next to the entry.
    creplace('''		.interface_modes = BIT(NL80211_IFTYPE_STATION) |
					BIT(NL80211_IFTYPE_AP),
		.supports_monitor = false,
		.supports_shadow_regs = true,
		.idle_ps = true,''',
             '''		.interface_modes = BIT(NL80211_IFTYPE_STATION) |
					BIT(NL80211_IFTYPE_AP),
		.supports_monitor = false,
		.supports_shadow_regs = true,
		/* uke: no APPS side H2S handshake yet, so the firmware's IMPS
		 * recipe cannot complete (see prepare-ath11k.py). */
		.idle_ps = false,''')
    core.write_text(ctext)
    replace('		ret = ath11k_qmi_wlanfw_wlan_ini_send(ab, true);',
            '		ath11k_info(ab, "fw start: wlan_ini");\n		ret = ath11k_qmi_wlanfw_wlan_ini_send(ab, true);')
    replace('	ret = ath11k_qmi_wlanfw_wlan_cfg_send(ab);',
            '	ath11k_info(ab, "fw start: wlan_cfg");\n	ret = ath11k_qmi_wlanfw_wlan_cfg_send(ab);')
    replace('	ret = ath11k_qmi_wlanfw_mode_send(ab, mode);',
            '	ath11k_info(ab, "fw start: mode %u", mode);\n	ret = ath11k_qmi_wlanfw_mode_send(ab, mode);')
    dp = output / 'dp.c'
    dtext = dp.read_text()
    def dreplace(old, new):
        nonlocal dtext
        if dtext.count(old) != 1:
            raise SystemExit('ath11k dp trace patch: pattern not unique')
        dtext = dtext.replace(old, new)
    dreplace('	ret = ath11k_wbm_idle_ring_setup(ab, &n_link_desc);',
             '	ath11k_info(ab, "dp: wbm_idle_ring_setup");\n	ret = ath11k_wbm_idle_ring_setup(ab, &n_link_desc);')
    dreplace('	srng = &ab->hal.srng_list[dp->wbm_idle_ring.ring_id];',
             '	ath11k_info(ab, "dp: wbm_idle done");\n	srng = &ab->hal.srng_list[dp->wbm_idle_ring.ring_id];')
    dreplace('	ret = ath11k_dp_link_desc_setup(ab, dp->link_desc_banks,',
             '	ath11k_info(ab, "dp: link_desc_setup links %u", n_link_desc);\n	ret = ath11k_dp_link_desc_setup(ab, dp->link_desc_banks,')
    dreplace('	ret = ath11k_dp_srng_common_setup(ab);',
             '	ath11k_info(ab, "dp: srng_common_setup");\n	ret = ath11k_dp_srng_common_setup(ab);')
    dreplace('''	size = sizeof(struct hal_wbm_release_ring) * DP_TX_COMP_RING_SIZE;

	for (i = 0; i < ab->hw_params.hal_params->num_tx_rings; i++) {''',
             '''	size = sizeof(struct hal_wbm_release_ring) * DP_TX_COMP_RING_SIZE;

	ath11k_info(ab, "dp: tx_rings %u", ab->hw_params.hal_params->num_tx_rings);
	for (i = 0; i < ab->hw_params.hal_params->num_tx_rings; i++) {''')
    dp.write_text(dtext)
    path.write_text(text)
    return (hashlib.sha256(path.read_bytes()).hexdigest(), hashlib.sha256(core.read_bytes()).hexdigest(),
            hashlib.sha256(dp.read_bytes()).hexdigest())


def patch_ce_ring_trace(output: Path):
    """Log both views of the CE source ring the WMI commands go out on.

    With idle_ps off the firmware answers every command through the first vdev
    create and then stops: VDEV_SET_WMM_PARAMS (0x500d), STA_POWERSAVE_PARAM
    (0x9002) and the later SCAN_CHAN_LIST (0x3003) all fail in ath11k_ce_send
    with -ENOBUFS, i.e. the 32 entry source ring reports no free slot even
    though the firmware keeps returning HTC credits and keeps sending
    WMI_DIAG_EVENTID. Two very different faults look like that: the target
    consumed the descriptors but never wrote the tail pointer where we read it,
    or the host reads the tail pointer from a place nothing writes. The host
    view (hp / cached_tp / the word in the RDP block), the CE register view
    (R2 HP and TP) and the TP_ADDR the ring was programmed with separate them.
    """
    path = output / 'ce.c'
    text = path.read_text()
    anchor = '''static bool ath11k_ce_need_shadow_fix(int ce_id)
'''
    if text.count(anchor) != 1:
        raise SystemExit('ath11k ce ring trace patch: anchor not unique')
    helper = '''#define UKE_CE_TRACE_SENDS 48
static unsigned int uke_ce_traced_sends;

static void uke_ce_ring_trace(struct ath11k_base *ab, struct ath11k_ce_pipe *pipe,
			      struct hal_srng *srng, const char *where)
{
	u32 r0 = srng->hwreg_base[HAL_SRNG_REG_GRP_R0];
	u32 r2 = srng->hwreg_base[HAL_SRNG_REG_GRP_R2];

	ath11k_info(ab,
		    "uke ce %s pipe %u ring %u hp %u cached %u mem %u free %d n %u es %u hp_reg %u tp_reg %u tpa %08x%08x hp_addr %llx rdp_pa %llx",
		    where, pipe->pipe_num, srng->ring_id,
		    srng->u.src_ring.hp, srng->u.src_ring.cached_tp,
		    *(volatile u32 *)srng->u.src_ring.tp_addr,
		    ath11k_hal_srng_src_num_free(ab, srng, true),
		    srng->num_entries, srng->entry_size,
		    ath11k_hif_read32(ab, r2),
		    ath11k_hif_read32(ab, r2 + HAL_TCL1_RING_TP_OFFSET),
		    ath11k_hif_read32(ab, r0 + HAL_TCL1_RING_TP_ADDR_MSB_OFFSET(ab)),
		    ath11k_hif_read32(ab, r0 + HAL_TCL1_RING_TP_ADDR_LSB_OFFSET(ab)),
		    (unsigned long long)(unsigned long)srng->u.src_ring.hp_addr,
		    (unsigned long long)ab->hal.rdp.paddr);
}

'''
    text = text.replace(anchor, helper + anchor)
    traced = '''	pipe->src_ring->write_index = CE_RING_IDX_INCR(nentries_mask,
						       write_index);

	ath11k_hal_srng_access_end(ab, srng);
'''
    if text.count(traced) != 1:
        raise SystemExit('ath11k ce ring trace patch: send anchor not unique')
    text = text.replace(traced, '''	pipe->src_ring->write_index = CE_RING_IDX_INCR(nentries_mask,
						       write_index);

	if (uke_ce_traced_sends < UKE_CE_TRACE_SENDS) {
		uke_ce_traced_sends++;
		uke_ce_ring_trace(ab, pipe, srng, "send");
	}

	ath11k_hal_srng_access_end(ab, srng);
''')
    nofree = '''	if (unlikely(ath11k_hal_srng_src_num_free(ab, srng, false) < 1)) {
		ath11k_hal_srng_access_end(ab, srng);'''
    if text.count(nofree) != 1:
        raise SystemExit('ath11k ce ring trace patch: nofree anchor not unique')
    text = text.replace(nofree, '''	if (unlikely(ath11k_hal_srng_src_num_free(ab, srng, false) < 1)) {
		uke_ce_ring_trace(ab, pipe, srng, "nofree");
		ath11k_hal_srng_access_end(ab, srng);''')
    noreap = '''	desc = ath11k_hal_srng_src_get_next_reaped(ab, srng);
	if (!desc) {
		ath11k_hal_srng_access_end(ab, srng);'''
    if text.count(noreap) != 1:
        raise SystemExit('ath11k ce ring trace patch: reap anchor not unique')
    text = text.replace(noreap, '''	desc = ath11k_hal_srng_src_get_next_reaped(ab, srng);
	if (!desc) {
		uke_ce_ring_trace(ab, pipe, srng, "noreap");
		ath11k_hal_srng_access_end(ab, srng);''')
    path.write_text(text)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch_ce_inline_reap(output: Path):
    """Reap the CE source ring from the send path instead of from an interrupt.

    The CE ring trace of candidate 4E6B2BB5408C0063 shows the failure exactly:
    `uke ce noreap pipe 3 ring 35 hp 124 cached 124 mem 124 free 31 n 32` --
    the target keeps the tail pointer current, the ring is empty, and the send
    still fails because ath11k_hal_srng_src_get_next_reaped() compares hp with
    reap_hp. Upstream only advances reap_hp / sw_index from
    ath11k_ce_tx_process_cb(), which the CE interrupt triggers.

    On this AHB port the endpoint can leave exactly one 32 bit word in the host
    MSI sink page, and the WMI receive vector (0x322, the HTC credit report) is
    written immediately after each command's consumption, overwriting the
    source ring completion vector (0x323). Evidence: the older boot
    1497FEF9FCB11D48, where the credit reports stopped, does show one
    `msi vector 3 (00000323)` right after vdev create, while the 1BF4587A and
    4E6B2BB5 boots never see vector 3 at all although 31 descriptors were
    consumed.

    So reap here, before taking the ring lock: this is the same completion work
    the interrupt would have done, and the CE_ATTR_DIS_INTR pipes already poll
    it for the same reason.
    """
    path = output / 'ce.c'
    text = path.read_text()
    anchor = '''int ath11k_ce_send(struct ath11k_base *ab, struct sk_buff *skb, u8 pipe_id,
		   u16 transfer_id)
{'''
    if text.count(anchor) != 1:
        raise SystemExit('ath11k inline reap patch: anchor not unique')
    text = text.replace(anchor, '''static void ath11k_ce_tx_process_cb(struct ath11k_ce_pipe *pipe);

int ath11k_ce_send(struct ath11k_base *ab, struct sk_buff *skb, u8 pipe_id,
		   u16 transfer_id)
{''')
    prologue = '''	u8 byte_swap_data = 0;
	int num_used;
'''
    if text.count(prologue) != 1:
        raise SystemExit('ath11k inline reap patch: prologue not unique')
    text = text.replace(prologue, '''	u8 byte_swap_data = 0;
	int num_used;

	/* uke: the source ring completion interrupt is lost on this AHB port
	 * (single word MSI sink; the WMI rx vector overwrites it), so reap the
	 * descriptors the target has already consumed before asking for a free
	 * slot. Without this hp == reap_hp forever after the first wrap and
	 * every later WMI command fails with -ENOBUFS.
	 */
	if (pipe->src_ring && pipe->src_ring->write_index != pipe->src_ring->sw_index)
		ath11k_ce_tx_process_cb(pipe);
''')
    path.write_text(text)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch_dp_rx_trace(output: Path):
    """Log the DP receive plumbing the firmware needs before it can deliver a
    frame.

    Candidate F6FA03ECEE587EF1 gets a real scan out (WMI_START_SCAN, the
    firmware reports scan started and walks 2412/2417/2422) and then the WPSS
    asserts in whal_recv.c:whalRxMpduPop, i.e. when the firmware pops the first
    received MPDU. Nothing on the host side ever sees a data path interrupt
    (the probe's vector bitmap never grows past 0xe), so the question is
    whether the host posted receive buffers and told the firmware about the
    rings at all. These lines answer it: buffers posted per ring, the result of
    each HTT ring setup message, and the irq each DP group was registered on.
    """
    rx = output / 'dp_rx.c'
    text = rx.read_text()
    anchor = '''	rx_ring->bufs_max = num_entries;
	ath11k_dp_rxbufs_replenish(ar->ab, dp->mac_id, rx_ring, num_entries,
				   ar->ab->hw_params.hal_params->rx_buf_rbm);
'''
    if text.count(anchor) != 1:
        raise SystemExit('ath11k dp rx trace patch: ring setup anchor not unique')
    text = text.replace(anchor, '''	rx_ring->bufs_max = num_entries;
	{
		int uke_posted = ath11k_dp_rxbufs_replenish(ar->ab, dp->mac_id, rx_ring,
							   num_entries,
							   ar->ab->hw_params.hal_params->rx_buf_rbm);

		ath11k_info(ar->ab, "uke dp ring type %u ring %d entries %d posted %d",
			    ringtype, rx_ring->refill_buf_ring.ring_id,
			    num_entries, uke_posted);
	}
''')
    refill = '''	req_entries = min(num_free, req_entries);
	num_remain = req_entries;

	while (num_remain > 0) {
		skb = dev_alloc_skb(DP_RX_BUFFER_SIZE +
'''
    if text.count(refill) != 1:
        raise SystemExit('ath11k dp rx trace patch: refill anchor not unique')
    text = text.replace(refill, '''	req_entries = min(num_free, req_entries);
	num_remain = req_entries;

	if (uke_dp_refill_traced < 16) {
		uke_dp_refill_traced++;
		ath11k_info(ab, "uke dp refill ring %d mac %d req %d free %d bufs_max %d",
			    rx_ring->refill_buf_ring.ring_id, mac_id, req_entries,
			    num_free, rx_ring->bufs_max);
	}

	while (num_remain > 0) {
		skb = dev_alloc_skb(DP_RX_BUFFER_SIZE +
''')
    sig = '''int ath11k_dp_rxbufs_replenish(struct ath11k_base *ab, int mac_id,
'''
    if text.count(sig) != 1:
        raise SystemExit('ath11k dp rx trace patch: refill signature not unique')
    text = text.replace(sig, '''static unsigned int uke_dp_refill_traced;

int ath11k_dp_rxbufs_replenish(struct ath11k_base *ab, int mac_id,
''')
    rx.write_text(text)

    dp = output / 'dp.c'
    dtext = dp.read_text()
    danchor = '''	/* TODO:Per-pdev rx ring unlike tx ring which is mapped to different AC's */
	for (i = 0; i < ab->num_radios; i++) {
'''
    if dtext.count(danchor) != 1:
        raise SystemExit('ath11k dp rx trace patch: pdev alloc anchor not unique')
    dtext = dtext.replace(danchor, '''	ath11k_info(ab, "uke dp pdev_alloc radios %u", ab->num_radios);

	/* TODO:Per-pdev rx ring unlike tx ring which is mapped to different AC's */
	for (i = 0; i < ab->num_radios; i++) {
''')
    dp.write_text(dtext)

    dtx = output / 'dp_tx.c'
    ttext = dtx.read_text()
    tret = '''		   cmd->msi_data, ring_id, ring_type, cmd->intr_info, cmd->info2);

	ret = ath11k_htc_send(&ab->htc, ab->dp.eid, skb);
	if (ret)
		goto err_free;

	return 0;

err_free:
	dev_kfree_skb_any(skb);

	return ret;
'''
    if ttext.count(tret) != 1:
        raise SystemExit('ath11k dp rx trace patch: htt setup anchor not unique')
    ttext = ttext.replace(tret, '''		   cmd->msi_data, ring_id, ring_type, cmd->intr_info, cmd->info2);

	ret = ath11k_htc_send(&ab->htc, ab->dp.eid, skb);
	if (ret)
		goto err_free;

	ath11k_info(ab, "uke htt srng setup ring %d mac %d type %d ok",
		    ring_id, mac_id, ring_type);

	return 0;

err_free:
	dev_kfree_skb_any(skb);
	ath11k_info(ab, "uke htt srng setup ring %d mac %d type %d ret %d",
		    ring_id, mac_id, ring_type, ret);

	return ret;
''')
    dtx.write_text(ttext)

    pcic = output / 'pcic.c'
    ptext = pcic.read_text()
    ianchor = '''			irq_set_status_flags(irq, IRQ_DISABLE_UNLAZY);
			ret = request_irq(irq, ath11k_pcic_ext_interrupt_handler,
'''
    if ptext.count(ianchor) != 1:
        raise SystemExit('ath11k dp rx trace patch: ext irq anchor not unique')
    ptext = ptext.replace(ianchor, '''			ath11k_info(ab, "uke dp irq group %d vector %d irq %d",
				    i, vector, irq);
			irq_set_status_flags(irq, IRQ_DISABLE_UNLAZY);
			ret = request_irq(irq, ath11k_pcic_ext_interrupt_handler,
''')
    pcic.write_text(ptext)
    return (hashlib.sha256(rx.read_bytes()).hexdigest(), hashlib.sha256(dp.read_bytes()).hexdigest(),
            hashlib.sha256(dtx.read_bytes()).hexdigest(), hashlib.sha256(pcic.read_bytes()).hexdigest())


def patch_dp_irq_trace(output: Path):
    """Log whether the data path interrupt and its NAPI actually run.

    Candidate 16212C1F062308BE posts every receive buffer (refill ring 4095 of
    4096, monitor status 1023 of 1024) and the firmware accepts all four HTT
    ring setup messages, but no data path vector ever appears in the board's
    MSI counter, while cfg80211's BSS list ends up with 5 entries. One of the
    two readings has to be wrong, so this traces the chain once end to end.
    """
    dp = output / 'dp.c'
    dtext = dp.read_text()
    anchor = '''int ath11k_dp_service_srng(struct ath11k_base *ab,
			   struct ath11k_ext_irq_grp *irq_grp,
			   int budget)
{'''
    if dtext.count(anchor) != 1:
        raise SystemExit('ath11k dp irq trace patch: service anchor not unique')
    dtext = dtext.replace(anchor, '''static unsigned int uke_service_enter, uke_service_done;

int ath11k_dp_service_srng(struct ath11k_base *ab,
			   struct ath11k_ext_irq_grp *irq_grp,
			   int budget)
{''')
    entry = '''	int i, j;
	int tot_work_done = 0;
'''
    if dtext.count(entry) != 1:
        raise SystemExit('ath11k dp irq trace patch: service entry anchor not unique')
    dtext = dtext.replace(entry, '''	int i, j;
	int tot_work_done = 0;

	if (uke_service_enter < 32) {
		uke_service_enter++;
		ath11k_info(ab, "uke dp service grp %d budget %d", grp_id, budget);
	}
''')
    tail = '''done:
	return tot_work_done;
}
EXPORT_SYMBOL(ath11k_dp_service_srng);'''
    if dtext.count(tail) != 1:
        raise SystemExit('ath11k dp irq trace patch: service tail anchor not unique')
    dtext = dtext.replace(tail, '''done:
	if (uke_service_done < 32) {
		uke_service_done++;
		ath11k_info(ab, "uke dp service grp %d done %d", grp_id, tot_work_done);
	}
	return tot_work_done;
}
EXPORT_SYMBOL(ath11k_dp_service_srng);''')
    dp.write_text(dtext)

    rx = output / 'dp_rx.c'
    rtext = rx.read_text()
    ranchor = '''	struct hal_reo_dest_ring *desc;
	enum hal_reo_dest_ring_push_reason push_reason;
	u32 cookie;
	int i;
'''
    if rtext.count(ranchor) != 1:
        raise SystemExit('ath11k dp irq trace patch: process_rx anchor not unique')
    rtext = rtext.replace(ranchor, '''	struct hal_reo_dest_ring *desc;
	enum hal_reo_dest_ring_push_reason push_reason;
	u32 cookie;
	int i;

	if (uke_process_rx_traced < 32) {
		uke_process_rx_traced++;
		ath11k_info(ab, "uke dp process_rx ring %d", ring_id);
	}
''')
    sig = '''int ath11k_dp_process_rx(struct ath11k_base *ab, int ring_id,
			 struct napi_struct *napi, int budget)
{'''
    if rtext.count(sig) != 1:
        raise SystemExit('ath11k dp irq trace patch: process_rx signature not unique')
    rtext = rtext.replace(sig, '''static unsigned int uke_process_rx_traced;

int ath11k_dp_process_rx(struct ath11k_base *ab, int ring_id,
			 struct napi_struct *napi, int budget)
{''')
    rx.write_text(rtext)

    pcic = output / 'pcic.c'
    ptext = pcic.read_text()
    ianchor = '''static irqreturn_t ath11k_pcic_ext_interrupt_handler(int irq, void *arg)
{
	struct ath11k_ext_irq_grp *irq_grp = arg;
	struct ath11k_base *ab = irq_grp->ab;
	int i;
'''
    if ptext.count(ianchor) != 1:
        raise SystemExit('ath11k dp irq trace patch: ext handler anchor not unique')
    ptext = ptext.replace(ianchor, '''static unsigned int uke_ext_irq_traced;

static irqreturn_t ath11k_pcic_ext_interrupt_handler(int irq, void *arg)
{
	struct ath11k_ext_irq_grp *irq_grp = arg;
	struct ath11k_base *ab = irq_grp->ab;
	int i;

	if (uke_ext_irq_traced < 32) {
		uke_ext_irq_traced++;
		ath11k_info(ab, "uke dp ext irq %d grp %d", irq, irq_grp->grp_id);
	}
''')
    pcic.write_text(ptext)
    return (hashlib.sha256(dp.read_bytes()).hexdigest(), hashlib.sha256(rx.read_bytes()).hexdigest(),
            hashlib.sha256(pcic.read_bytes()).hexdigest())


def patch_rxdma_buf_trace(output: Path):
    """Log whether the target consumes the receive buffers the host posts.

    The scan results do arrive (a real AP shows up in cfg80211's list through
    ath11k_wmi_mgmt_rx_event), while the firmware still asserts in its receive
    path (whalRxMpduPop, whalRecvDmaLeakDetect) right after the scan starts.
    The refill ring reports 4095 of 4096 buffers posted, but posting only proves
    the host wrote descriptors and rang the doorbell. These lines show the tail
    pointer the target publishes for that ring and the consumer register, so
    "the target never saw the buffers" separates from "the target used them and
    then failed for another reason".
    """
    rx = output / 'dp_rx.c'
    text = rx.read_text()
    anchor = '''	ath11k_hal_srng_access_end(ab, srng);

	spin_unlock_bh(&srng->lock);

	return req_entries - num_remain;

fail_idr_remove:'''
    if text.count(anchor) != 1:
        raise SystemExit('ath11k rxdma trace patch: replenish tail anchor not unique')
    text = text.replace(anchor, '''	ath11k_hal_srng_access_end(ab, srng);

	if (uke_refill_traced < 16) {
		u32 r2 = srng->hwreg_base[HAL_SRNG_REG_GRP_R2];

		uke_refill_traced++;
		ath11k_info(ab, "uke rxdma buf ring %d hp %u cached %u mem %u free %d hp_reg %u tp_reg %u",
			    rx_ring->refill_buf_ring.ring_id, srng->u.src_ring.hp,
			    srng->u.src_ring.cached_tp,
			    *(volatile u32 *)srng->u.src_ring.tp_addr,
			    ath11k_hal_srng_src_num_free(ab, srng, true),
			    ath11k_hif_read32(ab, r2),
			    ath11k_hif_read32(ab, r2 + HAL_TCL1_RING_TP_OFFSET));
	}

	spin_unlock_bh(&srng->lock);

	return req_entries - num_remain;

fail_idr_remove:''')
    inc = '''#include "peer.h"'''
    if text.count(inc) != 1:
        raise SystemExit('ath11k rxdma trace patch: include anchor not unique')
    text = text.replace(inc, '''#include "peer.h"
#include "hif.h" /* ath11k_hif_read32 for the refill ring register readback */''')
    if text.count('static unsigned int uke_dp_refill_traced;') != 1:
        raise SystemExit('ath11k rxdma trace patch: refill counter anchor not unique')
    text = text.replace('static unsigned int uke_dp_refill_traced;',
                        'static unsigned int uke_dp_refill_traced, uke_refill_traced;')
    rx.write_text(text)

    wmi = output / 'wmi.c'
    wtext = wmi.read_text()
    wanchor = '''	ath11k_dbg(ab, ATH11K_DBG_MGMT, "event mgmt rx status %08x\\n",
		   rx_ev.status);
'''
    if wtext.count(wanchor) != 1:
        raise SystemExit('ath11k rxdma trace patch: mgmt rx anchor not unique')
    wtext = wtext.replace(wanchor, '''	ath11k_dbg(ab, ATH11K_DBG_MGMT, "event mgmt rx status %08x\\n",
		   rx_ev.status);

	if (uke_mgmt_rx_traced < 16) {
		uke_mgmt_rx_traced++;
		ath11k_info(ab, "uke mgmt rx freq %u chan %u len %u status %08x",
			    rx_ev.chan_freq, rx_ev.channel, skb->len, rx_ev.status);
	}
''')
    wtext = wtext.replace('''static void ath11k_mgmt_rx_event(struct ath11k_base *ab, struct sk_buff *skb)
{''', '''static unsigned int uke_mgmt_rx_traced;

static void ath11k_mgmt_rx_event(struct ath11k_base *ab, struct sk_buff *skb)
{''')
    wmi.write_text(wtext)
    return (hashlib.sha256(rx.read_bytes()).hexdigest(), hashlib.sha256(wmi.read_bytes()).hexdigest())


def patch_shadow_slot_trace(output: Path):
    """Log whether every ring that needs a shadow register got one.

    With supports_shadow_regs set, ath11k_hal_srng_setup() leaves a source
    ring's hp_addr unset and ath11k_hal_srng_update_shadow_config() fills it.
    There are only HAL_SHADOW_NUM_REGS (36) slots and the update silently
    returns -EINVAL beyond them, after which ath11k_hal_srng_access_end() writes
    the doorbell to a bogus offset. The refill trace shows exactly the symptom
    on the receive buffer ring: hp 8190 with tp 0, i.e. the target never
    consumed a single posted buffer, while every CE ring works.

    This prints how many slots were taken, which ring types were skipped, and
    the hp_addr the refill ring ended up with.
    """
    hal = output / 'hal.c'
    text = hal.read_text()
    limit = '''	if (shadow_cfg_idx >= HAL_SHADOW_NUM_REGS)
		return -EINVAL;
'''
    if text.count(limit) != 1:
        raise SystemExit('ath11k shadow trace patch: limit anchor not unique')
    text = text.replace(limit, '''	if (shadow_cfg_idx >= HAL_SHADOW_NUM_REGS) {
		ath11k_info(ab, "uke shadow full, skipped type %d ring %d",
			    ring_type, ring_num);
		return -EINVAL;
	}
''')
    tail = '''	/* update hp/tp addr to hal structure*/
	ath11k_hal_srng_update_hp_tp_addr(ab, shadow_cfg_idx, ring_type,
					  ring_num);
'''
    if text.count(tail) != 1:
        raise SystemExit('ath11k shadow trace patch: update anchor not unique')
    hal.write_text(text.replace(tail, tail + '''
	ath11k_info(ab, "uke shadow slot %d type %d ring %d target %08x",
		    shadow_cfg_idx, ring_type, ring_num, target_reg);
'''))

    rx = output / 'dp_rx.c'
    rtext = rx.read_text()
    old = '''		ath11k_info(ab, "uke rxdma buf ring %d hp %u cached %u mem %u free %d hp_reg %u tp_reg %u",
			    rx_ring->refill_buf_ring.ring_id, srng->u.src_ring.hp,
			    srng->u.src_ring.cached_tp,
			    *(volatile u32 *)srng->u.src_ring.tp_addr,
			    ath11k_hal_srng_src_num_free(ab, srng, true),
			    ath11k_hif_read32(ab, r2),
			    ath11k_hif_read32(ab, r2 + HAL_TCL1_RING_TP_OFFSET));'''
    new = '''		ath11k_info(ab, "uke rxdma buf ring %d hp %u cached %u mem %u free %d hp_reg %u tp_reg %u hp_addr %llx",
			    rx_ring->refill_buf_ring.ring_id, srng->u.src_ring.hp,
			    srng->u.src_ring.cached_tp,
			    *(volatile u32 *)srng->u.src_ring.tp_addr,
			    ath11k_hal_srng_src_num_free(ab, srng, true),
			    ath11k_hif_read32(ab, r2),
			    ath11k_hif_read32(ab, r2 + HAL_TCL1_RING_TP_OFFSET),
			    (unsigned long long)(unsigned long)srng->u.src_ring.hp_addr);'''
    if rtext.count(old) != 1:
        raise SystemExit('ath11k shadow trace patch: refill line not unique')
    rx.write_text(rtext.replace(old, new))
    return hashlib.sha256(hal.read_bytes()).hexdigest(), hashlib.sha256(rx.read_bytes()).hexdigest()


def patch_rdp_dump(output: Path):
    """Locate where the target publishes the receive buffer ring's tail.

    The receive buffer ring shows hp 8190 with tp 0 while the firmware clearly
    takes frames through it (each scan result arrives as a WMI management frame,
    which is what the host's buffers carry). The host therefore believes the
    ring is full, never replenishes, and the firmware runs out of buffers and
    asserts in its DMA leak detector. Either the target writes the tail pointer
    somewhere the host does not read, or it never writes it at all. Dumping the
    non-zero words of the ring pointer block after a few management frames shows
    which: a word that tracks the consumed count is the target's tail pointer.
    """
    wmi = output / 'wmi.c'
    text = wmi.read_text()
    anchor = '''	if (uke_mgmt_rx_traced < 16) {
		uke_mgmt_rx_traced++;
		ath11k_info(ab, "uke mgmt rx freq %u chan %u len %u status %08x",
			    rx_ev.chan_freq, rx_ev.channel, skb->len, rx_ev.status);
	}
'''
    if text.count(anchor) != 1:
        raise SystemExit('ath11k rdp dump patch: anchor not unique')
    ar_anchor = '''	if (!ar) {
		ath11k_warn(ab, "invalid pdev_id %d in mgmt_rx_event\\n",
			    rx_ev.pdev_id);
		dev_kfree_skb(skb);
		goto exit;
	}
'''
    if text.count(ar_anchor) != 1:
        raise SystemExit('ath11k rdp dump patch: ar check anchor not unique')
    dump = '''	if (!ar) {
		ath11k_warn(ab, "invalid pdev_id %d in mgmt_rx_event\\n",
			    rx_ev.pdev_id);
		dev_kfree_skb(skb);
		goto exit;
	}

	if (uke_mgmt_rx_traced == 1 || uke_mgmt_rx_traced == 4 ||
	    uke_mgmt_rx_traced == 8 || uke_mgmt_rx_traced == 12) {
		int i, shown = 0;

		ath11k_info(ab, "uke rdp dump after %u mgmt frames, refill ring %d mon status ring %d",
			    uke_mgmt_rx_traced,
			    ar->dp.rx_refill_buf_ring.refill_buf_ring.ring_id,
			    ar->dp.rx_mon_status_refill_ring[0].refill_buf_ring.ring_id);
		for (i = 0; i < HAL_SRNG_RING_ID_MAX && shown < 20; i++) {
			if (!ab->hal.rdp.vaddr[i])
				continue;
			ath11k_info(ab, "uke rdp[%d] = %u", i, ab->hal.rdp.vaddr[i]);
			shown++;
		}
	}
'''
    text = text.replace(ar_anchor, dump)
    wmi.write_text(text)
    return hashlib.sha256(wmi.read_bytes()).hexdigest()


def patch_rxbuf_poll_replenish(output: Path):
    """Replenish the receive rings from the board thread, not from NAPI.

    The ring pointer dump settles it: the target does consume the posted
    buffers (rdp[128] reaches 2110 and stays there, ~1055 descriptors of 4096),
    the host simply never refills them because ath11k_dp_rxbufs_replenish() only
    runs at the end of ath11k_dp_service_srng(), i.e. from the data path NAPI,
    which this port never enters (no data path interrupt is raised for scan
    traffic). With 55 free slots left the firmware asserts in
    whalRecvDmaLeakRecovery. Export one entry point that does the same
    housekeeping so the board can call it on a timer.
    """
    rx = output / 'dp_rx.c'
    text = rx.read_text()
    anchor = '''int ath11k_dp_rx_pdev_alloc(struct ath11k_base *ab, int mac_id)
{
	struct ath11k *ar = ab->pdevs[mac_id].ar;
	struct ath11k_pdev_dp *dp = &ar->dp;
	u32 ring_id;
	int i;
	int ret;
'''
    if text.count(anchor) != 1:
        raise SystemExit('ath11k replenish patch: rx_pdev_alloc anchor not unique')
    text = text.replace(anchor, '''static struct ath11k_base *uke_replenish_ab;

/* uke: what ath11k_dp_service_srng() does at the end of a NAPI poll. The board
 * thread calls this while the port has no data path interrupt, otherwise the
 * target empties the ring and asserts in its DMA leak recovery. */
void ath11k_dp_rx_poll_replenish(void)
{
	struct ath11k_base *ab = uke_replenish_ab;
	const struct ath11k_hw_hal_params *hal_params;
	int i, j;

	if (!ab)
		return;

	{
		static unsigned int uke_poll_traced;

		if (uke_poll_traced < 4) {
			uke_poll_traced++;
			ath11k_info(ab, "uke poll run radios %u refill %d free-ish %d",
				    ab->num_radios,
				    ab->num_radios ? ab->pdevs[0].ar->dp.rx_refill_buf_ring.refill_buf_ring.ring_id : -1,
				    ab->num_radios ? ab->pdevs[0].ar->dp.rx_refill_buf_ring.bufs_max : -1);
		}
	}

	hal_params = ab->hw_params.hal_params;

	for (i = 0; i < ab->num_radios; i++) {
		struct ath11k *ar = ab->pdevs[i].ar;
		struct ath11k_pdev_dp *dp;

		if (!ar)
			continue;

		dp = &ar->dp;
		/* A zero request only tops the ring up once it is more than three
		 * quarters free (ath11k_dp_rxbufs_replenish decides that), which is
		 * too late here: ask for a fixed share every tick instead. */
		ath11k_dp_rxbufs_replenish(ab, i, &dp->rx_refill_buf_ring,
					   dp->rx_refill_buf_ring.bufs_max / 2,
					   hal_params->rx_buf_rbm);
		for (j = 0; j < ab->hw_params.num_rxdma_per_pdev; j++)
			ath11k_dp_rxbufs_replenish(ab,
						   i * ab->hw_params.num_rxdma_per_pdev + j,
						   &dp->rx_mon_status_refill_ring[j],
						   dp->rx_mon_status_refill_ring[j].bufs_max / 2,
						   hal_params->rx_buf_rbm);
	}
}

int ath11k_dp_rx_pdev_alloc(struct ath11k_base *ab, int mac_id)
{
	struct ath11k *ar = ab->pdevs[mac_id].ar;
	struct ath11k_pdev_dp *dp = &ar->dp;
	u32 ring_id;
	int i;
	int ret;

	uke_replenish_ab = ab;
''')
    rx.write_text(text)
    return hashlib.sha256(rx.read_bytes()).hexdigest()


def patch_mon_timer_replenish(output: Path):
    """Run the receive refill from the driver's own 10 ms monitor timer.

    Calling it from the board thread proved unreliable: the board's call never
    reached the driver (neither the board's tick line nor the function's own
    line ever appeared, while the rest of that same loop kept printing). The
    monitor reap timer is driver internal, already initialised where the monitor
    rings are attached, and ATH11K_MON_TIMER_INTERVAL is 10 ms, so the refill
    rides on a path this port cannot fail to reach. The timer is armed here
    because ath11k_dp_rx_pktlog_start(), its normal starter, never runs.
    """
    rx = output / 'dp_rx.c'
    text = rx.read_text()
    decl = '''static void ath11k_dp_service_mon_ring(struct timer_list *t)
{
	struct ath11k_base *ab = timer_container_of(ab, t, mon_reap_timer);
	int i;

	for (i = 0; i < ab->hw_params.num_rxdma_per_pdev; i++)
		ath11k_dp_rx_process_mon_rings(ab, i, NULL, DP_MON_SERVICE_BUDGET);
'''
    if text.count(decl) != 1:
        raise SystemExit('ath11k mon timer patch: callback anchor not unique')
    text = text.replace(decl, '''void ath11k_dp_rx_poll_replenish(void);

static void ath11k_dp_service_mon_ring(struct timer_list *t)
{
	struct ath11k_base *ab = timer_container_of(ab, t, mon_reap_timer);
	int i;

	for (i = 0; i < ab->hw_params.num_rxdma_per_pdev; i++)
		ath11k_dp_rx_process_mon_rings(ab, i, NULL, DP_MON_SERVICE_BUDGET);

	/* uke: keep the receive rings fed; nothing else runs this housekeeping
	 * while the port has no data path interrupt. */
	ath11k_dp_rx_poll_replenish();
''')
    rx.write_text(text)

    dp = output / 'dp.c'
    dtext = dp.read_text()
    tail = '''	return 0;

err:
	ath11k_dp_pdev_free(ab);'''
    if dtext.count(tail) != 1:
        raise SystemExit('ath11k mon timer patch: pdev alloc tail not unique')
    dtext = dtext.replace(tail, '''	if (!timer_pending(&ab->mon_reap_timer)) {
		mod_timer(&ab->mon_reap_timer,
			  jiffies + msecs_to_jiffies(ATH11K_MON_TIMER_INTERVAL));
		ath11k_info(ab, "uke mon reap timer armed for receive refill");
	}

	return 0;

err:
	ath11k_dp_pdev_free(ab);''')
    dp.write_text(dtext)
    return hashlib.sha256(rx.read_bytes()).hexdigest(), hashlib.sha256(dp.read_bytes()).hexdigest()


def patch_he_cap_trace(output: Path):
    """Log what mac80211 will validate about each band's HT/HE bandwidth.

    mac80211 7.x refuses a band that advertises HT 40 MHz while its HE station
    entry lacks the matching HE PHY 40 MHz bit, with a bare -EINVAL. On this
    firmware the two sides do agree, so this is observation only: print the
    per-band HE PHY/mac capabilities and the HT capability word, plus the raw
    WMI mac-phy-capabilities words, so a future disagreement is visible without
    another round trip.
    """
    path = output / 'mac.c'
    text = path.read_text()

    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise SystemExit('ath11k HE cap trace patch: pattern not unique')
        text = text.replace(old, new)

    helper = '''/* Print the bandwidth bits mac80211 will cross-check between HT and HE per
 * band. Observation only: nothing is modified. */
static void ath11k_mac_trace_ht_he_bandwidth(struct ath11k *ar)
{
	struct ieee80211_supported_band *band;
	const struct ieee80211_sband_iftype_data *iftd;
	int b, i;

	for (b = 0; b < NUM_NL80211_BANDS; b++) {
		band = &ar->mac.sbands[b];
		if (!band->ht_cap.ht_supported)
			continue;

		for_each_sband_iftype_data(band, i, iftd)
			ath11k_info(ar->ab, "he cap band %d entry %d types %x has_he %u phy0 %02x mac0 %02x",
				    b, i, iftd->types_mask, iftd->he_cap.has_he,
				    iftd->he_cap.he_cap_elem.phy_cap_info[0],
				    iftd->he_cap.he_cap_elem.mac_cap_info[0]);

		ath11k_info(ar->ab, "he cap band %d ht %08x ht40 %u n_iftd %u",
			    b, band->ht_cap.cap,
			    !!(band->ht_cap.cap & IEEE80211_HT_CAP_SUP_WIDTH_20_40),
			    band->n_iftype_data);
	}
}

'''
    replace('static int __ath11k_mac_register(struct ath11k *ar)\n',
            helper + 'static int __ath11k_mac_register(struct ath11k *ar)\n')
    replace('\tath11k_mac_setup_he_cap(ar, cap);\n\n\tret = ath11k_mac_setup_iface_combinations(ar);',
            '\tath11k_mac_setup_he_cap(ar, cap);\n\tath11k_mac_trace_ht_he_bandwidth(ar);\n\n'
            '\tret = ath11k_mac_setup_iface_combinations(ar);')
    path.write_text(text)

    # WMI command observation uses the driver's own debug mask
    # (ATH11K_DBG_WMI): ath11k_dbg already logs every command and event, so the
    # board only has to set ath11k_debug_mask. Nothing is added to htc.c.
    wmi = output / 'wmi.c'
    wtext = wmi.read_text()
    old = '''	if (tag != WMI_TAG_MAC_PHY_CAPABILITIES)
		return -EPROTO;
'''
    new = '''	if (tag != WMI_TAG_MAC_PHY_CAPABILITIES)
		return -EPROTO;

	/* Board diagnostic: the same words mac80211 later validates, read straight
	 * from the TLV payload, so a zero in our decoded copy can be told apart from
	 * a zero the firmware actually sent. */
	if (len >= 112) {
		const u8 *raw = ptr;
		u32 bands, ht2g, he2g, phy2g, ht5g, he5g, phy5g, ampdu;

		memcpy(&bands, raw + 16, 4);
		memcpy(&ampdu, raw + 20, 4);
		memcpy(&ht2g, raw + 28, 4);
		memcpy(&he2g, raw + 40, 4);
		memcpy(&ht5g, raw + 60, 4);
		memcpy(&he5g, raw + 72, 4);
		memcpy(&phy2g, raw + 88, 4);
		memcpy(&phy5g, raw + 100, 4);
		ath11k_info(soc, "mac phy cap tlv len %u bands %08x ampdu %08x ht2g %08x he2g %08x phy2g0 %08x ht5g %08x he5g %08x phy5g0 %08x",
			    len, bands, ampdu, ht2g, he2g, phy2g, ht5g, he5g, phy5g);
	} else {
		ath11k_info(soc, "mac phy cap tlv len %u below the expected 112", len);
	}
'''
    if wtext.count(old) != 1:
        raise SystemExit('ath11k HE cap alignment patch: wmi anchor not unique')
    wmi.write_text(wtext.replace(old, new))
    return (hashlib.sha256(path.read_bytes()).hexdigest(), hashlib.sha256(wmi.read_bytes()).hexdigest())


def main():
    lock = json.loads((ROOT / 'tools/source-lock.json').read_text())['linux']
    linux = ROOT / 'deps/linux'
    revision = subprocess.check_output(['git', '-C', str(linux), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != lock['commit']:
        raise SystemExit('ath11k must use the same locked Linux revision as mac80211/cfg80211')
    source = linux / 'drivers/net/wireless/ath/ath11k'
    output = ROOT / 'out/ath11k-src'
    output.mkdir(parents=True, exist_ok=True)
    hashes = {}
    trace_names = set()
    for path in sorted(source.parent.glob('*.h')):
        shutil.copyfile(path, output.parent / path.name)
        hashes['../' + path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(source.iterdir()):
        if path.suffix not in ('.c', '.h'):
            continue
        data = path.read_bytes()
        hashes[path.name] = hashlib.sha256(data).hexdigest()
        trace_names.update(re.findall(r'\btrace_ath11k_[a-z_0-9]+', data.decode()))
        if path.name != 'trace.h':
            shutil.copyfile(path, output / path.name)
    (output / 'trace.h').write_text('/* CONFIG_ATH11K_TRACING is disabled. */\n' +
                                   '\n'.join(f'#define {name}(...) ' + ('0' if name.endswith('_enabled') else '((void)0)')
                                             for name in sorted(trace_names)) + '\n')
    makefile = (source / 'Makefile').read_text()
    core = makefile.split('ath11k-y +=', 1)[1].split('ath11k-$(', 1)[0]
    selected = [name + '.c' for name in re.findall(r'\b([a-z0-9_]+)\.o\b', core)] + ['ahb.c']
    staging_hash, core_hash, dp_staging_hash = patch_board_staging(output)
    mac_hash, wmi_hash = patch_he_cap_trace(output)
    ce_hash = patch_ce_ring_trace(output)
    # Bridges disabled on 2026-11-07 per the rule against stopgap fixes: with the hardware
    # MSI path delivering every vector, upstream's own NAPI runs the completion reaping and
    # the receive refill, so none of these belong in the tree.
    ce_reap_hash = None               # patch_ce_inline_reap
    dp_rx_hash, dp_hash, dp_tx_hash, dp_pcic_hash = patch_dp_rx_trace(output)
    irq_dp_hash, irq_rx_hash, irq_pcic_hash = patch_dp_irq_trace(output)
    refill_rx_hash, refill_wmi_hash = patch_rxdma_buf_trace(output)
    shadow_hal_hash, shadow_rx_hash = patch_shadow_slot_trace(output)
    rdp_dump_hash = patch_rdp_dump(output)
    replenish_hash = None             # patch_rxbuf_poll_replenish
    mon_rx_hash = mon_dp_hash = None  # patch_mon_timer_replenish
    # Every patch that touches the same file must be applied before the hash is
    # recorded, so publish the final bytes of each patched source as well.
    patched = {}
    for name in ('ce.c', 'core.c', 'dp.c', 'dp_rx.c', 'dp_tx.c', 'mac.c', 'pcic.c', 'qmi.c', 'wmi.c'):
        p = output / name
        if p.exists():
            patched[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    (ROOT / 'out/ath11k-identity.json').write_text(json.dumps({
        'patched_sha256': patched,
        'linux_revision': revision,
        'source_sha256': hashes,
        'sources': selected,
        'configuration': ['CONFIG_ATH11K', 'CONFIG_ATH11K_AHB', 'CONFIG_ATH11K_DEBUG'],
        'trace_disabled': True,
        'board_staging_qmi_sha256': staging_hash,
        'board_staging_core_sha256': core_hash,
        'board_staging_dp_sha256': dp_staging_hash,
        'he_cap_trace_mac_sha256': mac_hash,
        'he_cap_trace_wmi_sha256': wmi_hash,
        'ce_ring_trace_ce_sha256': ce_hash,
        'ce_inline_reap_ce_sha256': ce_reap_hash or '',
        'dp_rx_trace_dp_rx_sha256': dp_rx_hash,
        'dp_rx_trace_dp_sha256': dp_hash,
        'dp_rx_trace_dp_tx_sha256': dp_tx_hash,
        'dp_rx_trace_pcic_sha256': dp_pcic_hash,
        'dp_irq_trace_dp_sha256': irq_dp_hash,
        'dp_irq_trace_dp_rx_sha256': irq_rx_hash,
        'dp_irq_trace_pcic_sha256': irq_pcic_hash,
        'rxdma_buf_trace_dp_rx_sha256': refill_rx_hash,
        'rxdma_buf_trace_wmi_sha256': refill_wmi_hash,
        'shadow_slot_trace_hal_sha256': shadow_hal_hash,
        'shadow_slot_trace_dp_rx_sha256': shadow_rx_hash,
        'rdp_dump_wmi_sha256': rdp_dump_hash,
        'rxbuf_poll_replenish_dp_rx_sha256': replenish_hash or '',
        'mon_timer_replenish_dp_rx_sha256': mon_rx_hash or '',
        'mon_timer_replenish_dp_sha256': mon_dp_hash or '',
        'hardware_verified': False,
    }, indent=2) + '\n')
    print(f'ath11k: {len(selected)} original core/AHB sources at {revision}')


if __name__ == '__main__':
    main()
