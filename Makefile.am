LIST_END =

SUBDIRS = data dialogs

reinteractdir = $(bindir)
dist_bin = bin/reinteract
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
                    lib/reinteract/mini_window.py                             \
                    lib/reinteract/new_notebook.py                            \
                    lib/reinteract/notebook.py                                \
                    lib/reinteract/notebook_info.py                           \
                    lib/reinteract/notebook_window.py                         \
                    lib/reinteract/open_notebook.py                           \
                    lib/reinteract/popup.py                                   \
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

examplesdir = $(docdir)/examples
examples_DATA =					\
             examples/basics.rws		\
             examples/imshow.rws		\
             examples/index.rnb			\
             examples/play.rws			\
             examples/plot.rws			\
 	     $(LIST_END)

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


EXTRA_DIST =					\
             ChangeLog				\
	     autogen.sh				\
	     epydoc.conf			\
	     bin/reinteract.in			\
	     $(examples_DATA)			\
             README				\
	     $(WIX_FILES)			\
	     $(WIX_EXTRA)			\
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

.PHONY: api-docs
