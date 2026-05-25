# BusierBox Buildroot external tree.
# Payload packaging is handled by scripts/buildroot-build-payload.

# Disable KEXGUESS2 in Dropbear so dbclient does not send an optimistic kex
# packet before negotiation completes.  Paramiko (busierbox-server SSH mode)
# does not implement the RFC 4253 §7.1 wrong-guess skip, so the sntrup761
# guess packet triggers a "Client kex 'e' is out of range" crash.
define BUSIERBOX_DROPBEAR_LOCALOPTIONS
	echo '#define DROPBEAR_KEXGUESS2 0' >> $(@D)/localoptions.h
endef
DROPBEAR_POST_EXTRACT_HOOKS += BUSIERBOX_DROPBEAR_LOCALOPTIONS
