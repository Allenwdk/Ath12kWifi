/* Event constants from the locked Linux suspend.h. Board PM hooks remain external. */
#ifndef NW_LINUX_SUSPEND_H
#define NW_LINUX_SUSPEND_H
#include "lx_ath.h"
#define PM_HIBERNATION_PREPARE 0x0001
#define PM_SUSPEND_PREPARE 0x0003
int unregister_pm_notifier(struct notifier_block *notifier);
#endif
