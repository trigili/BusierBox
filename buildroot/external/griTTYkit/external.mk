# griTTYkit Buildroot external tree.
# Payload packaging is handled by scripts/lib/buildroot-build-payload.

include $(sort $(wildcard $(BR2_EXTERNAL_GRIPTYKIT_PATH)/package/*/*.mk))

# Disable KEXGUESS2 in Dropbear so dbclient does not send an optimistic kex
# packet before negotiation completes.  Paramiko (grit-console SSH mode)
# does not implement the RFC 4253 §7.1 wrong-guess skip, so the sntrup761
# guess packet triggers a "Client kex 'e' is out of range" crash.
define GRIPTYKIT_DROPBEAR_LOCALOPTIONS
	echo '#define DROPBEAR_KEXGUESS2 0' >> $(@D)/localoptions.h
endef
DROPBEAR_POST_EXTRACT_HOOKS += GRIPTYKIT_DROPBEAR_LOCALOPTIONS
