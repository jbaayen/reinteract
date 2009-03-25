#!/bin/bash
#
# Copyright 2009 Owen Taylor
#
# This file is part of Reinteract and distributed under the terms
# of the BSD license. See the file COPYING in the Reinteract
# distribution for full details.
#
########################################################################

# Script to build a universal binary of Reinteract to use in the bundle
# and then build the binary

if [ -n "$JHBUILD_PREFIX" ] ; then
    echo 1>&2 "JHBuild is already running"
    exit 1
fi

scriptdir=$(cd $(dirname $0) && pwd)
toolsdir=$(dirname $scriptdir)
topdir=$(dirname $toolsdir)

libdir=/opt/reinteract/release-i386/install/lib

# These names cause the system frameworks to try and link against
# the single-arch versions of these libraries instead of of the
# system versions. The real fix is probably to get GTK+ to use
# the system libraries.
echo "Moving image libraries away"
for i in png jpeg tiff ; do
    mv $libdir/lib$i.dylib $libdir/lib$i.dylib.save
done

export JHB=reinteract JHB_VARIANT=release-i386

jhbuild run env										\
       OBJC='gcc -arch i386 -arch ppc'							\
       CC='gcc -arch i386 -arch ppc'							\
       CFLAGS='-O2'									\
       CPP='gcc -E'									\
    sh -c "cd $topdir && ./autogen.sh --enable-python-thunks && make clean && make"
status=$?

echo "Restoring image libraries"
for i in png jpeg tiff ; do
    mv $libdir/lib$i.dylib.save $libdir/lib$i.dylib
done

[ $status = 0 ] || exit 1

jhbuild run python \
    $scriptdir/build_bundle.py --add-arch=/opt/reinteract/release-ppc/install
