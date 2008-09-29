#!/bin/bash

basedir=$(cd $(dirname $0) && pwd)

# Compute the JHB_VARIANT directory so we can create the root
# directory
if test "x$JHB_VARIANT" = x ; then
    platform=$(uname -p)
    case $platform in
       i386*) JHB_VARIANT="devel-i386" ;;
       *) JHB_VARIANT="devel-ppc" ;;
    esac
fi

# Sanity check to make sure that something standard was specified
case $JHB_VARIANT in
    devel-i386) ;;
    devel-ppc) ;;
    release-i386) ;;
    release-ppc) ;;
    *)
	echo 2>&1 "Unknown JHB_VARIANT $JHB_VARIANT"
	exit 1
    ;;
esac

export JHB=reinteract

if test -e $HOME/.jhbuildrc-reinteract ; then : ; else
    ln -s $basedir/jhbuildrc-reinteract $HOME/.jhbuildrc-reinteract
fi

if test -d /opt/reinteract/packages ; then : ; else
    mkdir -p /opt/reinteract/packages
fi

if test -d /opt/reinteract/$JHB_VARIANT/source ; then : ; else
    mkdir -p /opt/reinteract/$JHB_VARIANT/source
fi

if test -e /opt/reinteract/$JHB_VARIANT/source/pkgs ; then : ; else
    ln -s /opt/reinteract/packages /opt/reinteract/$JHB_VARIANT/source/pkgs
fi

jhbuild -m $basedir/reinteract-bootstrap.modules build meta-bootstrap

jhbuild build meta-gtk-osx-bootstrap
jhbuild build
