#ifndef NATIVEVMC_H
#define NATIVEVMC_H

/* Rejected cards remain inactive; these reasons never bypass native write guards. */
enum native_vmc_error {
    NATIVE_VMC_OK,
    NATIVE_VMC_INVALID,
    NATIVE_VMC_FRAGMENTED,
    NATIVE_VMC_LBA_RANGE,
    NATIVE_VMC_LAYOUT_UNKNOWN,
    NATIVE_VMC_PFS_LIMIT
};

/* Embedded module images persist across cancelled launches; slot writes overwrite
 * the marker. Cache its word offset, and bound the complete payload on every use. */
static inline int nativeVmcSlotWord(const void *image, int size, int slot, int *cache, int payload)
{
    if (!image || !cache || slot < 0 || slot > 1 || payload <= 0 || size < payload)
        return -1;
    int last = (size - payload) / (int)sizeof(unsigned int);
    if (cache[slot] == -2) {
        cache[slot] = -1;
        const unsigned int *words = (const unsigned int *)image;
        for (int i = 0; i <= last; i++) {
            if (words[i] == 0xC0DEFAC0u + (unsigned int)slot) {
                cache[slot] = i;
                break;
            }
        }
    }
    return cache[slot] >= 0 && cache[slot] <= last ? cache[slot] : -1;
}

#endif
