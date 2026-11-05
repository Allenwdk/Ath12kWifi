/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef NW_LINUX_IOMMU_H
#define NW_LINUX_IOMMU_H
#include "lx_os.h"
struct iommu_domain;
#define IOMMU_READ (1 << 0)
#define IOMMU_WRITE (1 << 1)
struct iommu_domain *iommu_paging_domain_alloc(struct device *dev);
void iommu_domain_free(struct iommu_domain *domain);
int iommu_attach_device(struct iommu_domain *domain, struct device *dev);
void iommu_detach_device(struct iommu_domain *domain, struct device *dev);
int iommu_map(struct iommu_domain *domain, unsigned long iova, phys_addr_t paddr, size_t size, int prot, gfp_t flags);
size_t iommu_unmap(struct iommu_domain *domain, unsigned long iova, size_t size);
#endif
