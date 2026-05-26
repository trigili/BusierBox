################################################################################
#
# busierbox-doom-ascii
#
################################################################################

BUSIERBOX_DOOM_ASCII_VERSION = 0.3.1
BUSIERBOX_DOOM_ASCII_SOURCE = doom-ascii-$(BUSIERBOX_DOOM_ASCII_VERSION).tar.gz
BUSIERBOX_DOOM_ASCII_SITE = $(call github,wojciech-graj,doom-ascii,$(BUSIERBOX_DOOM_ASCII_VERSION))
BUSIERBOX_DOOM_ASCII_LICENSE = GPL-2.0+
BUSIERBOX_DOOM_ASCII_LICENSE_FILES = LICENSE

define BUSIERBOX_DOOM_ASCII_BUILD_CMDS
	$(MAKE) -C $(@D) \
		CC="$(TARGET_CC)" \
		PLATFORM=busierbox \
		LDFLAGS="$(TARGET_LDFLAGS) -static"
endef

define BUSIERBOX_DOOM_ASCII_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/_busierbox/game/doom-ascii \
		$(TARGET_DIR)/usr/bin/doom
	$(INSTALL) -D -m 0644 $(@D)/_busierbox/game/.default.cfg \
		$(TARGET_DIR)/usr/share/busierbox/doom/.default.cfg
endef

$(eval $(generic-package))
