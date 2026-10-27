#ifndef __RAPOPSLAUNCH_H__
#define __RAPOPSLAUNCH_H__
#ifdef RETROACHIEVEMENTS
/* Writes <root>POPS/MODULE_9.IRX for a tracked USB VCD launch. Prepare only after the source and
   POPStarter launch paths are validated. 0: launch (tracked or not), -1: do not launch. */
int raPopsPrepare(const char *root, const char *watchRoot, const char *vcdPath, int slotFree);
#endif
#endif
