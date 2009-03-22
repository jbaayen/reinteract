icondir = $(datadir)/icons/hicolor/scalable/apps
icon_DATA = reinteract.svg

desktopdir = $(datadir)/applications
desktop_DATA = reinteract.desktop

mimedir = $(datadir)/mime/packages
mime_DATA = reinteract.xml

# Install the ICO to use in the About dialog
pkgdata_DATA=					\
	Reinteract.ico

EXTRA_DIST=					\
	$(desktop_DATA)				\
	$(icon_DATA)				\
	$(mime_DATA)				\
	Info.plist				\
	MainMenu.nib/classes.nib		\
	MainMenu.nib/info.nib			\
	MainMenu.nib/keyedobjects.nib		\
	Reinteract.ico				\
	Reinteract.icns

# Calling update-mime-database is necessary to get the associations
# in reinteract.xml to work properly on a XDG-compliant system; however
# it makes things hard on packagers since there are a bunch of stray
# files in the install root (and it complicates 'make uninstall')
#
# We could have --disable-update-mime or something in configure.ac,
# but just skip it. Most people will be using packaged versions anyways.
#
# install-data-hook:
# 	-update-mime-database $(DESTDIR)$(datadir)/mime > /dev/null 2>&1
#
# uninstall-hook:
# 	-update-mime-database $(DESTDIR)$(datadir)/mime > /dev/null 2>&1
