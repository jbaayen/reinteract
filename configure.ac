AC_INIT(reinteract, 0.4.1)

AC_CONFIG_AUX_DIR(config)

AM_INIT_AUTOMAKE([dist-bzip2 no-dist-gzip])
AM_MAINTAINER_MODE
AM_PATH_PYTHON(2.4)

AC_CONFIG_HEADERS(config.h)

AC_PROG_CC
AC_PROG_OBJC

changequote(,)dnl
if test "x$GCC" = "xyes"; then
  case " $CFLAGS " in
  *[\ \	]-Wall[\ \	]*) ;;
  *) CFLAGS="$CFLAGS -Wall" ;;
  esac

  case " $OBJCFLAGS " in
  *[\ \	]-Wall[\ \	]*) ;;
  *) OBJCFLAGS="$OBJCFLAGS -Wall" ;;
  esac
fi
changequote([,])dnl

APPDIR=
AC_ARG_WITH(appdir,
	    [AC_HELP_STRING([--with-appdir=APPDIR],
	         [On OS X, install Reinteract.app into APPDIR])],
            [if test x$withval = xyes ; then
	        AC_MSG_ERROR([Directory must be specified as argument to --with-appdir])
	     elif test x$withval = xno ; then
	        :
	     else
	        APPDIR=$withval
	     fi])

AM_CONDITIONAL(INSTALL_APP, test "x$APPDIR" != x)
AC_SUBST(APPDIR)

use_python_thunks=false
AC_ARG_ENABLE(python-thunks,
              [AC_HELP_STRING([--enable-python-thunks],
	         [On OS X, lazily locate Python at run-time (default is no)])],
              [if test "x$enableval" != xno ; then use_python_thunks=true ; fi])

if $use_python_thunks ; then
   AC_DEFINE(USE_PYTHON_THUNKS, 1,
             [Define to locate Python lazily at runtime])]
fi

AM_CONDITIONAL(USE_PYTHON_THUNKS, $use_python_thunks)

dnl A macro to get a variable from distutils.sysconfig
dnl reinteract_GET_CONFIG_VAR(SHELL_NAME, SYSCONFIG_NAME)
dnl
AC_DEFUN([reinteract_GET_CONFIG_VAR],
    [$1=`$PYTHON -c "import sys; import distutils.sysconfig; sys.stdout.write(distutils.sysconfig.get_config_var('$2'))"`])

AC_CANONICAL_HOST

platform_osx=false
case $host in
     *-*-darwin*)
	# This will break if someone wants to build the X11 version of reinteract
     	# on OS X. They can just use bin/uninst.py, or they can figure out how
     	# to fix this :-)
        platform_osx=true
        PKG_CHECK_MODULES(WRAPPER, [pygobject-2.0 >= 2.12 gtk+-2.0 >= 2.12])
        JD_CHECK_PYTHON_HEADERS(,[AC_MSG_ERROR(could not find Python headers)])

        if $use_python_thunks ; then : ; else
	    # Need to figure out how to link against Python at compile time
	    AC_MSG_CHECKING([how to link against Python])
	    reinteract_GET_CONFIG_VAR(python_framework_prefix, PYTHONFRAMEWORKPREFIX)
	    if test x$python_framework_prefix = x ; then
	    	reinteract_GET_CONFIG_VAR(python_libdir, LIBDIR)
	        PYTHON_LIBS="-L$python_libdir -lpython$PYTHON_VERSION"
            else
	        PYTHON_LIBS="-F$python_framework_prefix -framework Python"
            fi
	    AC_MSG_RESULT($PYTHON_LIBS)
	    AC_SUBST(PYTHON_LIBS)

	    # Test to see if what we found actually works
	    save_CFLAGS="$CFLAGS"
	    CFLAGS="$CFLAGS $PYTHON_INCLUDES"
	    save_LIBS="$LIBS"
	    LIBS="$LIBS $PYTHON_LIBS"
            AC_LINK_IFELSE(AC_LANG_PROGRAM([#include <Python.h>], [Py_Initialize();]),
	                   :,
		  	   AC_MSG_ERROR([Linking against Python didn't work; see config.log for details]))
	    CFLAGS="$save_CFLAGS"
	    LIBS="$save_LIBS"
	fi
     ;;
esac
AM_CONDITIONAL(PLATFORM_OSX, $platform_osx)

REINTERACT_PACKAGE_DIR=${pythondir}/$PACKAGE_NAME
AC_SUBST(REINTERACT_PACKAGE_DIR)

AC_OUTPUT([ 
  Makefile
  dialogs/Makefile
  data/Makefile
  bin/reinteract
])
