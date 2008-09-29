AC_INIT(reinteract, 0.4.0)

AC_CONFIG_AUX_DIR(config)

AM_INIT_AUTOMAKE([dist-bzip2 no-dist-gzip])
AM_MAINTAINER_MODE
AM_PATH_PYTHON(2.4)

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
