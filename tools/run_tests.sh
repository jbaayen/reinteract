#!/bin/sh

cd $srcdir/lib/reinteract

status=0
for f in *.py ; do
    if grep '^if __name__' $f | grep -v INTERACTIVE &> /dev/null ; then
	echo -n "$f .. "
	python $f
	if [ $? = 0 ] ; then
	    echo "OK"
	else
	    echo "FAIL"
	    status=1
	fi
    fi
done

exit $status
