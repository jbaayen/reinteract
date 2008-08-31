from replot import plot
from numpy import *

x = linspace(0, 2*pi, 100)

# Basic plotting of a single data set. (If only
# one parameter is given, then [0,1,2,...] is 
# used for the X values.
plot(x, cos(x))

# You can plot multiple sets of data in a single command
plot(x, cos(x), x, sin(x))

# You can also specify styles for each data set, see 
# http://matplotlib.sourceforge.net/matplotlib.axes.html#Axes-plot
# for more details

plot(x, cos(x), 'r--', # red dashed lines
     x, sin(x), 'bo')  # blue circles
