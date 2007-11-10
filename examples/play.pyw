from numpy import *
from replot import *

# Plot one cycle of a periodic function
x = linspace(0, 2 * pi, 50)
plot(x, sin(x) + sin(3*x) / 3 + sin(5*x) / 5)

# OK, looks good, let's create a bigger data set
# and play it
from replay import *

x = linspace(0, 440 * 2 * pi, 44100)
play(sin(x) + sin(3*x) / 3 + sin(5*x) / 5)
