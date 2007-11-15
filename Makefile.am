LIST_END =

reinteractdir = $(bindir)
dist_reinteract_SCRIPTS = bin/reinteract
dist_noinst_SCRIPTS = bin/uninst

reinteractpkgdir = $(REINTERACT_PACKAGE_DIR)
reinteractpkg_PYTHON =                                                        \
                    lib/reinteract/__init__.py                                \
                    lib/reinteract/custom_result.py                           \
                    lib/reinteract/format_escaped.py                          \
                    lib/reinteract/iter_copy_from.py                          \
                    lib/reinteract/main.py                                    \
                    lib/reinteract/notebook.py                                \
                    lib/reinteract/rewrite.py                                 \
                    lib/reinteract/shell_buffer.py                            \
                    lib/reinteract/shell_view.py                              \
                    lib/reinteract/statement.py                               \
                    lib/reinteract/tokenized_statement.py                     \
                    lib/reinteract/tokenize.py                                \
                    lib/reinteract/undo_stack.py                              \
                    lib/reinteract/worksheet.py                               \
                    $(LIST_END)

replaydir = $(pythondir)
replay_PYTHON = lib/replay.py

replotdir = $(pythondir)
replot_PYTHON = lib/replot.py

EXTRA_DIST =                                                                  \
             ChangeLog                                                        \
             examples/basics.pyw                                              \
             examples/imshow.pyw                                              \
             examples/play.pyw                                                \
             examples/plot.pyw                                                \
             README                                                           \
             $(LIST_END)

DISTCLEANFILES =                                                              \
                 $(LIST_END)

MAINTAINERCLEANFILES =                                                        \
                       aclocal.m4                                             \
		       ChangeLog					      \
                       config.guess                                           \
                       config.sub                                             \
                       configure                                              \
                       install-sh                                             \
                       ltmain.sh                                              \
                       Makefile.in                                            \
                       missing                                                \
		       NEWS						      \
                       py-compile                                             \
                       $(LIST_END)
