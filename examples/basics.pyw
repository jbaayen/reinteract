# To start using reinteract, type a Python expression, and hit
# <Control>Return to calculate. (This example is already calculated
# when it was loaded, but try modifying the statement below and
# then hit <Control>Return again to calculate it)
1 + 1

# You can assign and use variables
a = 2
a
a + 3

# As above, the default action when an expression returns a result
# other than N is to display it. You can also use 'print' explicitly
print "Hello", "World"

# Try modifying the value of a; you'll see that when you hit 
# control-return, the value of a + 3 is updated as well.

# You can define functions
def fact(n):
    result = 1
    for i in xrange(0,n):
        result *= (1 + i)
    return result

fact(3)

# And use constructs like for loops and if statements
for i in xrange(0,5):
    print "%d: %d" % (i + 1, fact(i + 1))
