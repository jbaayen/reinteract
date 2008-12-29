LIST_END =

SUBDIRS = data dialogs

bin_SCRIPTS = bin/reinteract
dist_noinst_SCRIPTS =				\
	bin/uninst.py				\
	bin/Reinteract.pyw

reinteractpkgdir = $(REINTERACT_PACKAGE_DIR)
reinteractpkg_PYTHON =                                                        \
                    lib/reinteract/__init__.py                                \
		    lib/reinteract/about_dialog.py			      \
		    lib/reinteract/application.py			      \
		    lib/reinteract/application_state.py			      \
		    lib/reinteract/base_window.py			      \
		    lib/reinteract/base_notebook_window.py		      \
		    lib/reinteract/change_range.py			      \
		    lib/reinteract/chunks.py			      	      \
                    lib/reinteract/completion_popup.py                        \
                    lib/reinteract/custom_result.py                           \
                    lib/reinteract/data_format.py                             \
                    lib/reinteract/doc_format.py                              \
                    lib/reinteract/doc_popup.py                               \
                    lib/reinteract/editor.py                                  \
                    lib/reinteract/editor_window.py                           \
                    lib/reinteract/file_list.py                               \
                    lib/reinteract/format_escaped.py                          \
                    lib/reinteract/global_settings.py                         \
                    lib/reinteract/iter_copy_from.py                          \
                    lib/reinteract/library_editor.py                          \
                    lib/reinteract/main.py                                    \
                    lib/reinteract/main_menu.py                               \
                    lib/reinteract/mini_window.py                             \
                    lib/reinteract/new_notebook.py                            \
                    lib/reinteract/notebook.py                                \
                    lib/reinteract/notebook_info.py                           \
                    lib/reinteract/notebook_window.py                         \
                    lib/reinteract/open_notebook.py                           \
                    lib/reinteract/popup.py                                   \
                    lib/reinteract/recorded_object.py                         \
                    lib/reinteract/retokenize.py                              \
                    lib/reinteract/rewrite.py                                 \
                    lib/reinteract/sanitize_textview_ipc.py                   \
                    lib/reinteract/save_file.py                               \
                    lib/reinteract/shell_buffer.py                            \
                    lib/reinteract/shell_view.py                              \
                    lib/reinteract/statement.py                               \
                    lib/reinteract/stdout_capture.py                          \
                    lib/reinteract/test_utils.py                              \
                    lib/reinteract/thread_executor.py                         \
                    lib/reinteract/tokenized_statement.py                     \
                    lib/reinteract/undo_stack.py                              \
                    lib/reinteract/window_builder.py                          \
                    lib/reinteract/worksheet.py                               \
                    lib/reinteract/worksheet_editor.py                        \
                    $(LIST_END)

replaydir = $(pythondir)
replay_PYTHON = lib/replay.py

replotdir = $(pythondir)
replot_PYTHON = lib/replot.py

examplesdir = $(pkgdatadir)/examples
examples_DATA =					\
             examples/basics.rws		\
             examples/imshow.rws		\
             examples/index.rnb			\
             examples/play.rws			\
             examples/plot.rws			\
             examples/plot2.rws			\
	     $(LIST_END)

TOOLS_EXTRA =					\
	tools/common/__init__.py		\
	tools/common/am_parser.py		\
	tools/common/builder.py			\
	tools/common/utils.py

# Input files for the WiX-based Windows installer
WIX_FILES =					\
	tools/build_msi/BrowsePage.wxs		\
	tools/build_msi/BrowsePage2.wxs		\
	tools/build_msi/CancelPage.wxs		\
	tools/build_msi/FatalErrorPage.wxs	\
	tools/build_msi/FeaturesPage.wxs	\
	tools/build_msi/ProgressPage.wxs	\
	tools/build_msi/ReinteractUI.wxs	\
	tools/build_msi/SuccessPage.wxs		\
	tools/build_msi/WelcomePage.wxs		\
	tools/build_msi/Overrides.wxl		\
	tools/build_msi/reinteractBanner.bmp

# Scripts and other files used for Windows installer
WIX_EXTRA =					\
	tools/build_msi/README			\
	tools/build_msi/build_msi.py		\
	tools/build_msi/wrapper.c		\
	tools/compiledir.py

# Scripts and other files used for OS X installer
BUNDLE_EXTRA =							\
	tools/build_bundle/README				\
	tools/build_bundle/build_bundle.py			\
	tools/build_bundle/reinteract-dmg-background.png	\
	tools/build_bundle/reinteract-dmg-background.svg	\
	tools/build_bundle/reinteract.dsstore

BUILD_DEPS_OSX_EXTRA =							\
	tools/build_deps_osx/Python-2.5.2-framework-arch-only.patch	\
	tools/build_deps_osx/Python-2.5.2-framework-arch.patch		\
	tools/build_deps_osx/README					\
	tools/build_deps_osx/build.sh					\
	tools/build_deps_osx/gdk-quartz-eventloop-rework-20080905.patch	\
	tools/build_deps_osx/gdk-window-process-updates-hook.patch	\
	tools/build_deps_osx/gtk-clipboard-quartz-new0.patch		\
	tools/build_deps_osx/i386.cache					\
	tools/build_deps_osx/jhbuildrc-reinteract			\
	tools/build_deps_osx/pango-relocate.patch			\
	tools/build_deps_osx/ppc.cache					\
	tools/build_deps_osx/pycairo-unknown-surface-types.patch	\
	tools/build_deps_osx/reinteract-bootstrap.modules		\
	tools/build_deps_osx/reinteract.modules

# Wrapper binary for OS X that sets the paths and loads the main menu
noinst_PROGRAMS =

if PLATFORM_OSX
noinst_PROGRAMS += ReinteractWrapper

build-local-app: ReinteractWrapper
	rm -rf Reinteract.app
	mkdir -p Reinteract.app/Contents/MacOS
	cp -p ReinteractWrapper Reinteract.app/Contents/MacOS/Reinteract
	mkdir -p Reinteract.app/Contents/Resources
	cp -p $(top_srcdir)/data/Info.plist Reinteract.app/Contents
	cp -pr $(top_srcdir)/data/MainMenu.nib Reinteract.app/Contents/Resources
	cp -p $(top_srcdir)/data/Reinteract.icns Reinteract.app/Contents/Resources
	touch Reinteract.app/Contents/Resources/UNINSTALLED

all-local: build-local-app

if INSTALL_APP
install-exec-hook: build-local-app
	for f in `find Reinteract.app -type f` ; do		\
	    b=`basename $$f` ;					\
	    d=`dirname $$f` ;					\
	    if test $$b = Reinteract ; then			\
		$(MKDIR_P) $(DESTDIR)$(APPDIR)/$$d ;		\
		$(INSTALL_PROGRAM) $$f $(DESTDIR)$(APPDIR)/$$f ;\
	    elif test $$b = UNINSTALLED ; then			\
		: ;						\
	    else						\
		$(MKDIR_P) $(DESTDIR)$(APPDIR)/$$d ;		\
		$(INSTALL_DATA) $$f $(DESTDIR)$(APPDIR)/$$f ;	\
	    fi							\
	done
endif

endif

ReinteractWrapper_SOURCES  =					\
	     src/reinteract_wrapper_osx/main.m			\
	     src/reinteract_wrapper_osx/MenuController.m	\
	     src/reinteract_wrapper_osx/MenuController.h	\
	     src/reinteract_wrapper_osx/pyNativeMainMenu.m	\
	     src/reinteract_wrapper_osx/pyNativeMainMenu.h

if USE_PYTHON_THUNKS
ReinteractWrapper_SOURCES  +=					\
	     src/reinteract_wrapper_osx/ThunkPython.c		\
	     src/reinteract_wrapper_osx/ThunkPython.h
endif

INCLUDES =					\
	$(PYTHON_INCLUDES)			\
	$(WRAPPER_CFLAGS)			\
	-DEXAMPLESDIR=\"$(examplesdir)\"	\
	-DDIALOGSDIR=\"$(pkgdatadir)/dialogs\"

ReinteractWrapper_LDFLAGS = -framework Cocoa $(PYTHON_LIBS)

TESTS=tools/run_tests.sh

EXTRA_DIST =					\
             ChangeLog				\
	     autogen.sh				\
	     epydoc.conf			\
	     bin/reinteract.in			\
	     $(examples_DATA)			\
             README				\
	     $(TOOLS_EXTRA)			\
	     $(WIX_FILES)			\
	     $(WIX_EXTRA)			\
	     $(BUNDLE_EXTRA)			\
	     $(BUILD_DEPS_OSX_EXTRA)		\
	     src/reinteract_wrapper_osx/README	\
	     tools/run_tests.sh			\
             $(LIST_END)

DISTCLEANFILES =                                                              \
                 $(LIST_END)

MAINTAINERCLEANFILES =                                                        \
                       aclocal.m4                                             \
		       ChangeLog					      \
		       config/install-sh				      \
		       config/missing					      \
		       config/py-compile				      \
                       configure                                              \
                       Makefile.in                                            \
		       NEWS						      \
                       $(LIST_END)

api-docs:
	@conf=`cd $(top_srcdir) && pwd`/epydoc.conf ;									\
	out=`pwd`/api-docs ;												\
	modules="" ;													\
	for pkg in $(reinteractpkg_PYTHON) ; do										\
		modules="$$modules `echo $$pkg | sed s@^lib/@@`" ;							\
	done;														\
	cd $(top_srcdir)/lib && PYTHONPATH="$PYTHONPATH:reinteract" epydoc -v --config=$$conf --output=$$out $$modules

distcheck-hook:
	@echo "Checking against files in git"
	@failed=false;							\
	for f in `cd $(srcdir) && git-ls-files -x .gitignore` ; do	\
		if test -e $(distdir)/$$f ; then : ; else		\
			echo File missing from distribution: $$f ;	\
			failed=true ;					\
		fi							\
	done ;								\
	if $$failed ; then						\
		exit 1 ;						\
	fi

.PHONY: api-docs build-local-app
