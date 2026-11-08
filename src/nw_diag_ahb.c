/* Diagnostics the ABI publishes from the WiFi worker, for the WCN6750 AHB
 * backend.
 *
 * The ath12k image defines these four in nw_wifi.c against ath12k structures
 * (ath12k_dp_link_peer_get_sta_rate_info_stats, struct ath11k_device_dp_stats,
 * the WMI extended-stats request). This ath11k tree has neither the peer-rate
 * helper nor the tx completion counters, so the same ABI names report what the
 * rings and the station status really hold:
 *
 *  - ring_state: every ring the host fills or empties, with free entries;
 *  - rx_state: error/refill/destination-ring occupancy and the delivered counts;
 *  - tx_reasons: transmit-completion ring occupancy (no release-reason table in
 *    this tree);
 *  - link_state: frequency, signal and channel count from the cached status.
 *
 * Deviation on record: link_state carries no rate. Wiring an ath11k peer-rate
 * source is a follow-up; until then the OS keeps whatever rate mac80211 reports
 * instead of a zero from here. Read-only: called on the LX worker only. */
#include "lx_plat.h"
#include <net/mac80211.h>
#include "core.h"
#include "dp.h"
#include "dp_tx.h"
#include "hal.h"
#include "nw_abi.h"
#include "nw_mainline.h"

extern struct net_device *nw_cfg80211_primary(void);
unsigned nw_rx_backlog(void);
unsigned nw_rx_dropped(void);

static struct ath11k_base *primary_ab(void)
{
	struct net_device *dev = nw_cfg80211_primary();
	if (!dev || !dev->ieee80211_ptr)
		return 0;
	struct ieee80211_hw *hw = wiphy_to_ieee80211_hw(dev->ieee80211_ptr->wiphy);
	struct ath11k *ar = hw ? hw->priv : 0;
	return ar ? ar->ab : 0;
}

/* Entries a ring holds for its consumer (dst: waiting for the host; src: free
 * for the host to fill); -1 for a ring that was never set up. */
static int ring_count(struct ath11k_base *ab, const struct dp_srng *r, int dst)
{
	if (!r->vaddr)
		return -1;
	struct hal_srng *s = &ab->hal.srng_list[r->ring_id];
	if (!s->initialized)
		return -1;
	spin_lock_bh(&s->lock);
	int n = dst ? ath11k_hal_srng_dst_num_free(ab, s, true)
	            : ath11k_hal_srng_src_num_free(ab, s, true);
	spin_unlock_bh(&s->lock);
	return n;
}

void nw_wifi_ring_state(char *b, int n)
{
	struct ath11k_base *ab = primary_ab();
	b[0] = 0;
	if (!ab)
		return;
	struct ath11k_dp *dp = &ab->dp;
	struct ath11k *ar = ath11k_ab_to_ar(ab, 0);
	snprintf(b, n, "exc %d rel %d st %d dmaerr %d/%d txc %d/%d/%d; free mon %d mac %d/%d idle %d; queued %u dropped %u",
	         ring_count(ab, &dp->reo_except_ring, 1), ring_count(ab, &dp->rx_rel_ring, 1),
	         ring_count(ab, &dp->reo_status_ring, 1),
	         ring_count(ab, &ar->dp.rxdma_err_dst_ring[0], 1), ring_count(ab, &ar->dp.rxdma_err_dst_ring[1], 1),
	         ring_count(ab, &dp->tx_ring[0].tcl_comp_ring, 1), ring_count(ab, &dp->tx_ring[1].tcl_comp_ring, 1),
	         ring_count(ab, &dp->tx_ring[2].tcl_comp_ring, 1),
	         ring_count(ab, &ar->dp.rx_mon_status_refill_ring[0].refill_buf_ring, 0),
	         ring_count(ab, &ar->dp.rx_mac_buf_ring[0], 0), ring_count(ab, &ar->dp.rx_mac_buf_ring[1], 0),
	         ring_count(ab, &dp->wbm_idle_ring, 0), nw_rx_backlog(), nw_rx_dropped());
}

void nw_wifi_rx_state(char *b, int n)
{
	struct ath11k_base *ab = primary_ab();
	b[0] = 0;
	if (!ab)
		return;
	struct ath11k_dp *dp = &ab->dp;
	struct ath11k *ar = ath11k_ab_to_ar(ab, 0);
	int o = 0;
	o += snprintf(b + o, n - o, "refill free %d; waiting",
	              ring_count(ab, &ar->dp.rx_refill_buf_ring.refill_buf_ring, 0));
	for (int i = 0; i < DP_REO_DST_RING_MAX && o < n; i++)
		o += snprintf(b + o, n - o, " %d", ring_count(ab, &dp->reo_dst_ring[i], 1));
	o += snprintf(b + o, n - o, "; mon status %d; queued %u, dropped %u",
	              ring_count(ab, &ar->dp.rx_mon_status_refill_ring[0].refill_buf_ring, 0),
	              nw_rx_backlog(), nw_rx_dropped());
}

/* No release-reason table exists in this tree; the completion rings are what
 * says whether the firmware is returning transmit buffers. */
void nw_wifi_tx_reasons(char *b, int n)
{
	struct ath11k_base *ab = primary_ab();
	b[0] = 0;
	if (!ab)
		return;
	struct ath11k_dp *dp = &ab->dp;
	int o = snprintf(b, n, "comp free");
	for (int i = 0; i < DP_TCL_NUM_RING_MAX && o < n; i++)
		o += snprintf(b + o, n - o, " %d", ring_count(ab, &dp->tx_ring[i].tcl_comp_ring, 1));
	if (o < n)
		snprintf(b + o, n - o, "; frames %u", nw_wifi_stats.frames);
}

void nw_wifi_link_state(char *text, int size)
{
	struct nw_wifi_status state;
	nw_wifi_status_get(&state);
	text[0] = 0;
	if (state.state != NW_STA_UP)
		return;
	/* Rate needs an ath11k peer-rate source this tree does not expose; the
	 * cached signal already comes from cfg80211, so nothing is pushed back. */
	snprintf(text, size, "freq %u rssi %d channels %u", state.freq_mhz, state.signal_dbm, state.channels);
}
