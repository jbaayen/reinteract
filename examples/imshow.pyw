from replot import imshow
from numpy import *
import matplotlib

# meshgrid is a handy numpy command for creating x and y coordinate
# arrays for a 2-D grid
xx, yy = meshgrid(linspace(0, 2*pi, 100), linspace(0, 2*pi, 100))

# To get an idea of what these arrays look like, let's look at 
# their upper left corners
xx[0:3,0:3]
yy[0:3,0:3]

# Now use the coordinate arrays to display a function over the range
# [0,2pi] x [0,2pi]
imshow(sin(xx) * cos(2 * yy))

# You can use any of the keyword arguments from:
# http://matplotlib.sourceforge.net/matplotlib.axes.html#Axes-imshow

imshow(sin(xx) * cos(2 * yy), 
       cmap=matplotlib.cm.copper, 
       extent=(0,2*pi,0,2*pi))
