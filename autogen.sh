#!/bin/sh

(cd $(dirname $0);
    touch ChangeLog NEWS &&
    autoreconf --install --symlink &&
    intltoolize --force &&
    autoreconf &&
    ./configure --enable-maintainer-mode $@
)
