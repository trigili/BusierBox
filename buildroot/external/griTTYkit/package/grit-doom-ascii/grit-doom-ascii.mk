################################################################################
#
# grit-doom-ascii
#
################################################################################

GRIT_DOOM_ASCII_VERSION = 0.3.1
GRIT_DOOM_ASCII_SOURCE = doom-ascii-$(GRIT_DOOM_ASCII_VERSION).tar.gz
GRIT_DOOM_ASCII_SITE = $(call github,wojciech-graj,doom-ascii,$(GRIT_DOOM_ASCII_VERSION))
GRIT_DOOM_ASCII_LICENSE = GPL-2.0+
GRIT_DOOM_ASCII_LICENSE_FILES = LICENSE

define GRIT_DOOM_ASCII_BUILD_CMDS
	$(MAKE) -C $(@D) \
		CC="$(TARGET_CC)" \
		PLATFORM=grit \
		LDFLAGS="$(TARGET_LDFLAGS) -static"
endef

define GRIT_DOOM_ASCII_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/_grit/game/doom-ascii \
		$(TARGET_DIR)/usr/bin/doom
	$(INSTALL) -D -m 0644 $(@D)/_grit/game/.default.cfg \
		$(TARGET_DIR)/usr/share/grit/doom/.default.cfg
endef

$(eval $(generic-package))
