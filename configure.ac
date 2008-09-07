AC_INIT(reinteract, 0.0.1)

AC_CONFIG_AUX_DIR(config)

AM_INIT_AUTOMAKE([dist-bzip2 dist-zip])
AM_MAINTAINER_MODE
AM_PATH_PYTHON(2.4)

REINTERACT_PACKAGE_DIR=${pythondir}/$PACKAGE_NAME
AC_SUBST(REINTERACT_PACKAGE_DIR)

AC_OUTPUT([ 
  Makefile
  dialogs/Makefile
  data/Makefile
  bin/reinteract
])
