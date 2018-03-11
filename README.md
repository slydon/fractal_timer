# fractal_timer
A fractal timer for gw2

Setup: Install tkinter if you don't already have it installed.  If you
want progress graphing, then also install matplotlib.

Usage:
./fractal_timer.py [--state <STATE>] [--reload] [--graph]
  
Valid STATE's are 'daily' and 'marathon'.  Reload tells the fractal state
machine to reload the state file.  Graph tells the fractal state machine
to output a graph file, optional to make matplotlib an optional dependency.
