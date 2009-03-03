DIALOGS =					\
	open-notebook.xml			\
	new-notebook.xml			\
	notebook-properties.xml			\
	preferences.xml				\
	save-file.xml

dialogsdir=$(pkgdatadir)/dialogs
dialogs_DATA=$(DIALOGS)

EXTRA_DIST=$(dialogs_DATA)

update-dialogs:
	for f in $(DIALOGS) ; do									\
          glade=$${f%.xml}.glade ;									\
          gtk-builder-convert $(srcdir)/$$glade -  | grep -v '<requires-version' > $(srcdir)/$$f  ;	\
        done

dist-hook:
	for f in $(DIALOGS) ; do		\
          glade=$${f%.xml}.glade ;		\
          cp $(srcdir)/$$glade $(distdir) ;	\
        done

distclean-hook:
	rm -f $(DIALOGS)

.PHONY: update-dialogs
