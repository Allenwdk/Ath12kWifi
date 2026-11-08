/* WCN6750 AHB platform provider for the ported ath11k driver.
 *
 * The stock DT describes the WLAN node with "msi_addr"/"smmu_iova_ipa"
 * resources, a 32-vector SPI range, the WPSS rproc handle and the fixed MSA
 * region. XNU has no platform bus, so this file supplies the small Linux
 * object model the AHB driver expects and bridges it to the board callbacks:
 * the BAR comes from the QMI device-info reply, the MSI doorbell from the DT,
 * and WPSS start/stop from the board worker. MMIO of the BAR itself is owned
 * by the board (nw_board.map_phys). */
#include "lx_plat.h"
#include "lx_pci.h"
#include "nw_qrtr.h"

extern int ath11k_ahb_driver_init(void);
extern void ath11k_ahb_driver_exit(void);

extern volatile uint32_t native_ufs_msi_iova __attribute__((weak_import));
#define WCN6750_MSI_PA 0x17110040ULL
#define WCN6750_MSI_SPI_BASE 0x300U
#define WCN6750_BAR_PA 0x61e00000ULL
#define WCN6750_BAR_BYTES 0x200000U
#define WCN6750_MSA_PA 0xa6400000ULL
#define WCN6750_MSA_BYTES 0x00c00000U

static struct platform_driver *g_driver;
static struct platform_device g_pdev;
static struct device_node g_node;
static struct resource g_res[2];
static const char *g_compat = "qcom,wcn6750-wifi";
static const void *g_match_data;

/* Provided by the board worker. */
extern int nw_board_wpss_start(void);
extern int nw_board_glink_xmit(const void *packet, size_t length);
extern void *nw_board_bar(void);
extern void *nw_board_map_phys(uint64_t pa, size_t n);
extern int nw_board_mac(unsigned char *address);
extern uint64_t nw_board_msi_iova(void);

static struct property *node_property(const struct device_node *node, const char *name)
{
    (void)node; (void)name;
    return 0; /* The board fills g_res and the small property set directly. */
}

int of_property_read_u32(const struct device_node *node, const char *name, u32 *value)
{
    (void)node;
    if (!name || !value) return -EINVAL;
    if (!strcmp(name, "qcom,rproc")) {*value = 1; return 0;}
    if (!strcmp(name, "qcom,qmi-service-ins-id")) {*value = 3; return 0;}
    if (!strcmp(name, "qcom,board_id")) {*value = 0xff; return 0;}
    return -ENOENT;
}

int of_property_read_u32_index(const struct device_node *node, const char *name, u32 index, u32 *value)
{
    (void)node;
    if (!name || !value) return -EINVAL;
    if (!strcmp(name, "interrupts")) {*value = index ? WCN6750_MSI_SPI_BASE : 0; return 0;}
    return -ENOENT;
}

bool of_property_read_bool(const struct device_node *node, const char *name)
{
    (void)node; (void)name;
    return false;
}

int of_property_read_string(const struct device_node *node, const char *name, const char **value)
{
    (void)node; (void)name; (void)value;
    return -ENOENT;
}

int of_device_is_compatible(const struct device_node *node, const char *compatible)
{
    (void)node;
    return compatible && !strcmp(compatible, g_compat);
}

struct property *of_find_property(const struct device_node *node, const char *name, int *length)
{
    (void)length;
    return node_property(node, name);
}

const void *of_get_property(const struct device_node *node, const char *name, int *length)
{
    (void)length;
    return node_property(node, name);
}

void of_node_put(struct device_node *node) { (void)node; }

struct device_node *of_get_child_by_name(const struct device_node *node, const char *name)
{
    (void)node; (void)name;
    return 0; /* No wifi-firmware child: the WPSS/MSA are fixed by the boot chain. */
}

struct device_node *of_parse_phandle(const struct device_node *node, const char *name, int index)
{
    (void)node; (void)name; (void)index;
    return 0;
}

const struct of_device_id *of_match_device(const struct of_device_id *matches, const struct device *device)
{
    (void)device;
    if (!matches) return 0;
    for (; matches->compatible[0]; ++matches)
        if (!strcmp(matches->compatible, g_compat)) {g_match_data = matches->data; return matches;}
    return 0;
}

const struct of_device_id *of_match_node(const struct of_device_id *matches, const struct device_node *node)
{
    (void)node;
    return matches;
}

const void *device_get_match_data(const struct device *dev)
{
    (void)dev;
    /* ATH11K_HW_WCN6750_HW10 = 6; prefer the driver's of_match data. */
    return g_match_data ? g_match_data : (const void *)(uintptr_t)6;
}

int of_reserved_mem_region_to_resource(const struct device_node *node, int index, struct resource *res)
{
    (void)node;
    if (!res) return -EINVAL;
    if (index == 0) {res->start = WCN6750_MSA_PA; res->end = WCN6750_MSA_PA + WCN6750_MSA_BYTES - 1; return 0;}
    return -ENOENT;
}

struct reserved_mem *of_reserved_mem_lookup(struct device_node *node) { (void)node; return 0; }

int device_property_read_u32(const struct device *device, const char *name, u32 *value)
{
    return of_property_read_u32(device ? device->of_node : 0, name, value);
}

int device_property_read_string(const struct device *device, const char *name, const char **value)
{
    return of_property_read_string(device ? device->of_node : 0, name, value);
}

int of_machine_is_compatible(const char *compatible) { (void)compatible; return 0; }

struct resource *platform_get_resource(struct platform_device *pdev, unsigned type, unsigned index)
{
    (void)pdev;
    if (type != IORESOURCE_MEM || index != 0) return 0;
    return &g_res[0]; /* MSI doorbell: msi_addr is DT resource 0. */
}

int platform_get_irq(struct platform_device *pdev, unsigned index)
{
    (void)pdev;
    return (int)(0x400 + index); /* Board IRQ numbers, mapped by lx_request_irq. */
}

int platform_get_irq_byname(struct platform_device *pdev, const char *name)
{
    (void)pdev; (void)name;
    return 0x400;
}

void *devm_platform_get_and_ioremap_resource(struct platform_device *pdev, unsigned index, struct resource **resource)
{
    (void)pdev;
    if (resource) *resource = &g_res[1];
    return g_res[1].start ? (void *)(uintptr_t)g_res[1].start : 0;
}

static int probe_matches(struct platform_driver *driver)
{
    const struct of_device_id *match = of_match_device(driver->driver.of_match_table, &g_pdev.dev);
    return match != 0;
}

int platform_driver_register(struct platform_driver *driver)
{
    g_driver = driver;
    if (g_pdev.dev.of_node && probe_matches(driver) && driver->probe)
        return driver->probe(&g_pdev);
    return 0;
}

void platform_driver_unregister(struct platform_driver *driver)
{
    if (driver && driver->remove && g_pdev.dev.of_node) driver->remove(&g_pdev);
    if (g_driver == driver) g_driver = 0;
}

struct platform_device *platform_device_register_full(const struct platform_device_info *info)
{
    (void)info;
    g_pdev.dev.of_node = &g_node;
    /* The port's root device: ath11k passes this as the wiphy parent, and
     * device_add() takes a reference on it. Leaving it uninitialised trips the
     * get_device() BUG_ON as soon as registration succeeds. */
    g_pdev.dev.parent = lx_root_device();
    device_initialize(&g_pdev.dev);
    if (g_driver && probe_matches(g_driver) && g_driver->probe) g_driver->probe(&g_pdev);
    return &g_pdev;
}

void platform_device_unregister(struct platform_device *pdev) { (void)pdev; }

/* ---- DMA / IOMMU / remoteproc bridges ---- */

dma_addr_t dma_map_resource(struct device *dev, phys_addr_t address, size_t size,
                            enum dma_data_direction direction, unsigned long attrs)
{
    (void)dev; (void)size; (void)direction; (void)attrs;
    if (address == WCN6750_MSI_PA) {
        /* The endpoint must write the SoC's MSI bitmap (qcom,pci-msi@0x17110040), which ShengUfs now
         * maps into this bank at native_ufs_msi_iova. Bit N of that register raises level SPI 0x300+N,
         * so the GIC latches every vector; the old host memory sink kept only the last write. */
        if (&native_ufs_msi_iova != 0 && native_ufs_msi_iova)
            return (dma_addr_t)native_ufs_msi_iova;
        lx_log(3, "UKE WIFI AHB: MSI doorbell IOVA missing, memory sink in use");
        return nw_board_msi_iova();
    }
    return (dma_addr_t)address;
}


struct iommu_domain *iommu_paging_domain_alloc(struct device *dev) { (void)dev; return 0; }
int iommu_attach_device(struct iommu_domain *d, struct device *dev) { (void)d; (void)dev; return -ENODEV; }
void iommu_detach_device(struct iommu_domain *d, struct device *dev) { (void)d; (void)dev; }
void iommu_domain_free(struct iommu_domain *d) { (void)d; }
int iommu_map(struct iommu_domain *d, unsigned long iova, phys_addr_t pa, size_t size, int prot) { (void)d; (void)iova; (void)pa; (void)size; (void)prot; return -ENODEV; }
size_t iommu_unmap(struct iommu_domain *d, unsigned long iova, size_t size) { (void)d; (void)iova; return size; }

struct rproc *rproc_get_by_phandle(phandle handle)
{
    (void)handle;
    return (struct rproc *)(uintptr_t)1; /* The WPSS is owned by the board worker. */
}

int rproc_boot(struct rproc *rproc) { (void)rproc; return nw_board_wpss_start(); }
int rproc_shutdown(struct rproc *rproc) { (void)rproc; return 0; }
void rproc_put(struct rproc *rproc) { (void)rproc; }

/* ---- worker ---- */

static int glink_xmit(void *ctx, const void *pkt, size_t len)
{
    (void)ctx;
    return nw_board_glink_xmit(pkt, len);
}

void nw_ahb_qrtr_input(const void *packet, size_t length) { nw_qrtr_rx(packet, length); }
void nw_ahb_qrtr_down(void) { nw_qrtr_endpoint_down(); }
void nw_ahb_qrtr_up(void) { nw_qrtr_set_endpoint(glink_xmit, 0); }

int nw_ahb_start(void)
{
    memset(&g_node, 0, sizeof g_node);
    g_node.name = "wifi";
    memset(g_res, 0, sizeof g_res);
    g_res[0].start = WCN6750_MSI_PA; g_res[0].end = WCN6750_MSI_PA + 0xfff;
    g_res[1].start = (phys_addr_t)(uintptr_t)nw_board_bar();
    g_res[1].end = g_res[1].start + WCN6750_BAR_BYTES - 1;
    lx_plat = lx_plat; /* set by the board before this call */
    nw_qrtr_init();
    nw_qrtr_set_endpoint(glink_xmit, 0);
    struct platform_device_info info;
    memset(&info, 0, sizeof info);
    info.name = "ath11k-ahb";
    info.fwnode = &g_node.fwnode;
    info.dma_mask = 0xffffffffULL;
    platform_device_register_full(&info);
    return ath11k_ahb_driver_init();
}

void nw_ahb_stop(void)
{
    ath11k_ahb_driver_exit();
    platform_device_unregister(&g_pdev);
    nw_qrtr_endpoint_down();
}

/* ---- remaining shim glue for the ath11k stack ---- */

void *lx_ioremap(phys_addr_t pa, size_t n) { return nw_board_map_phys(pa, n); }
void lx_iounmap(void *p) { (void)p; }
void *devm_ioremap(struct device *dev, phys_addr_t pa, size_t n) { (void)dev; return lx_ioremap(pa, n); }
int of_dma_configure(struct device *dev, struct device_node *node, bool force_dma) { (void)dev; (void)node; (void)force_dma; return 0; }

void *dma_alloc_noncoherent(struct device *dev, size_t n, dma_addr_t *bus,
                            enum dma_data_direction dir, gfp_t flags)
{
    (void)dev; (void)dir; (void)flags;
    return lx_plat->dma_alloc(n, bus);
}
void dma_free_noncoherent(struct device *dev, size_t n, void *p, dma_addr_t bus,
                          enum dma_data_direction dir)
{
    (void)dev; (void)dir;
    lx_plat->dma_free(n, p, bus);
}

struct qcom_smem_state;
struct qcom_smem_state *qcom_smem_state_get(struct device *dev, const char *con_id, unsigned *bit)
{
    static int state;
    (void)dev; (void)con_id;
    if (bit) *bit = 0;
    return (struct qcom_smem_state *)&state;
}
void qcom_smem_state_put(struct qcom_smem_state *state) { (void)state; }

int register_pm_notifier(struct notifier_block *notifier) { (void)notifier; return 0; }
int unregister_pm_notifier(struct notifier_block *notifier) { (void)notifier; return 0; }

int device_get_mac_address(struct device *dev, u8 *address)
{
    (void)dev;
    return nw_board_mac(address);
}

int hex_dump_to_buffer(const void *buf, size_t len, int rowsize, int groupsize,
                       char *linebuf, size_t linebuflen, bool ascii)
{
    (void)rowsize; (void)groupsize; (void)ascii;
    const u8 *p = buf; size_t o = 0;
    for (size_t i = 0; i < len && o + 3 < linebuflen; ++i) o += (size_t)snprintf(linebuf + o, linebuflen - o, "%02x", p[i]);
    return (int)o;
}

struct bus_type mhi_bus_type = { .name = "mhi" };

int nw_aes_siv_encrypt(const u8 *key, size_t key_length, const u8 *plain, size_t length,
                       size_t count, const u8 *address[], size_t sizes[], u8 *output)
{
    (void)key; (void)key_length; (void)plain; (void)length; (void)count; (void)address; (void)sizes; (void)output;
    return -1; /* FILS is disabled until the provider is wired. */
}
int nw_aes_siv_decrypt(const u8 *key, size_t key_length, const u8 *cipher, size_t length,
                       size_t count, const u8 *address[], size_t sizes[], u8 *output)
{
    (void)key; (void)key_length; (void)cipher; (void)length; (void)count; (void)address; (void)sizes; (void)output;
    return -1;
}

void *memset32(uint32_t *s, uint32_t v, size_t count)
{
    for (size_t i = 0; i < count; ++i) s[i] = v;
    return s;
}
