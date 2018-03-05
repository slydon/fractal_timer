#!/usr/bin/env python3
"""
A tkinter gui for timing gw2 fractal runs and marathons.

Date: March 4, 2018
Author: Sean Lydon
License: BSD

Setup: Install tkinter if you don't already have it installed.  If you
want progress graphing, then also install matplotlib.

Usage:
./fractal_timer.py [--state <STATE>] [--reload] [--graph]

Valid STATE's are 'daily' and 'marathon'.  Reload tells the fractal state
machine to reload the state file.  Graph tells the fractal state machine
to output a graph file, optional to make matplotlib an optional dependency.


Copyright (c) 2018, Sean Lydon
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import atexit
import argparse
import ctypes
import json
import logging
import mmap
import os
import threading
from datetime import timedelta
from tkinter import Tk, Frame, StringVar, Label, Button, TOP, BOTTOM, BOTH, X
from tkinter.font import Font
from time import time

# From manually entering the zones
MAP_TO_NAME = {
     956: "Aetherblade",
     951: "Aquatic Ruins",
     960: "Captain Mai Trin Boss",
    1164: "Chaos",
     952: "Cliffside",
     959: "Molten Boss",
     955: "Molten Furnace",
    1177: "Nightmare",
    1205: "Shattered Observatory",
     948: "Snowblind",
     958: "Solid Ocean",
     949: "Swampland",
     957: "Thaumanova Reactor",
    1267: "Twilight Oasis",
     947: "Uncategorized",
     953: "Underground Facility",
     950: "Urban Battleground",
     954: "Volcanic"    
}

# From https://wiki.guildwars2.com/wiki/Fractals_of_the_Mists
MAP_TO_LEVELS = {
     956: [14, 46, 65, 71, 96],
     951: [7, 26, 61, 76],
     960: [18, 42, 73, 95],
    1164: [13, 30, 38, 54, 63, 88, 98],
     952: [6, 22, 33, 47, 69, 82, 94],
     959: [10, 40, 70, 90],
     955: [9, 23, 39, 58, 83],
    1177: [24, 49, 74, 99, 101],
    1205: [25, 50, 75, 100, 102],
     948: [3, 27, 37, 51, 68, 86, 93],
     958: [20, 35, 45, 60, 80],
     949: [5, 21, 32, 56, 67, 77, 89],
     957: [15, 34, 48, 55, 64, 84, 97],
    1267: [16, 41, 59, 87],
     947: [2, 12, 36, 44, 62, 79, 91],
     953: [8, 17, 29, 43, 53, 81],
     950: [4, 11, 31, 57, 66, 78, 85],
     954: [1, 19, 28, 52, 72, 92]    
}

LEVEL_TO_MAP = {l: m for m, v in MAP_TO_LEVELS.items() for l in v}

# Thanks to https://github.com/TheTerrasque/gw2lib
# and https://wiki.guildwars2.com/wiki/API:MumbleLink
def get_player_map(memfile):
    """Since I only need identity, just read that part for map_id"""
    memfile.seek(592)
    raw = ctypes.create_string_buffer(memfile.read(512))
    data = ctypes.cast(ctypes.pointer(raw), ctypes.POINTER(ctypes.c_wchar * 256)).contents.value
    return json.loads(data)['map_id']

def strtime(start, end):
    return str(timedelta(seconds=end - start))

def ifN(v, d):
    """Return value if value is not None else default"""
    return v if v is not None else d

class FractalState(object):
    """Base FractalState implementation used for daily fractals."""
    def __init(self):
        self.start = None
        self.end = None
        self.current_map = None
        self.current_map_name = ''
        self.current_start = None
        self.current_end = None

    def total_time(self, now):
        return strtime(self.start, ifN(self.end, now))

    def instance_time(self, now):
        return strtime(self.current_start, ifN(self.current_end, now)) if self.current_start else ''

    def update(self, current_map):
        now = int(time())

        if current_map != self.current_map:
            # stop, start, or noop
            if current_map in MAP_TO_NAME:
                self.current_map = current_map
                self.current_map_name = MAP_TO_NAME[current_map]
                self.current_start = now
                self.current_end = None
                self.log('instance start', now)
            elif self.current_map is not None:
                self.current_map = None
                self.current_end = now
                self.log('instance stop', now)

        return self.total_time(now), self.current_map_name, self.instance_time(now)
            

    def stop(self):
        now = int(time())
        self.current_end = now
        self.end = now
        self.log('stop', now)
        return self.total_time(now), self.current_map_name, self.instance_time(now)

    def start(self):
        now = int(time())
        self.current_end = None
        self.current_start = None
        self.current_map = None
        self.current_map_name = ''
        self.end = None
        self.start = now
        self.log('start', now)
        return self.total_time(now), self.current_map_name, self.instance_time(now)

    def log(self, action, now):
        logging.info('%s total: %s instance: %s cur_map: %s cur_label: %s', action, self.total_time(now),
            self.instance_time(now), self.current_map, self.current_map_name)


def generate_graph_fn():
    """Generate a graphing function so we don't require matplotlib if we don't graph"""
    import matplotlib.pyplot as plt
    def graph(state):
        ydata = []
        xdata = []
        for i, data in enumerate(state['levels']):
            if data['start'] is None or data['end'] is None:
                break
            ydata.append((data['end'] - data['start']) / 60)
            xdata.append(i+1)
        def make_graph():
            plt.plot(xdata, ydata, 'b-')
            plt.xticks(range(1, 104, 6))
            plt.yticks(range(0, 41, 5))
            plt.title('Fractal Marathon')
            plt.ylabel('Minutes per fractal')
            plt.xlabel('Fractal number')
            plt.savefig('progress.png')
        threading.Thread(target=make_graph).start()
    return graph


class MarathonState(FractalState):
    """MarathonState is used for tracking fractal marathons"""
    def __init__(self, reload_state=True, graph=True):
        # State:
        # {
        #    "start": <time>,
        #    "end": <time>,
        #    "levels": [(<time>, <time>), (<time>, <time>), ...]
        # }
        self.state = {'start': None, 'end': None, 'levels': [{'start': None, 'end': None} for _ in range(102)]}
        if reload_state and os.path.exists('state.json'):
            with open('state.json') as fp:
                self.state = json.load(fp)
        completed_levels = [i for i, x in enumerate(self.state['levels']) if x['end'] is not None]
        self.level = max(completed_levels) + 1 if completed_levels else 0
        self.graph = lambda *args: None
        if graph:
            self.graph = generate_graph_fn()
        self.graph(self.state)

    def total_time(self, now):
        return strtime(self.state['start'], ifN(self.state['end'], now)) if self.state['start'] else ''

    def label(self):
        x = self.level
        if x == 0:
            return ''
        return '{} - {}{}'.format(MAP_TO_NAME[LEVEL_TO_MAP[x]], x if x <= 100 else x - 2, 'CM' if x > 100 else '')

    def instance_time(self, now):
        s = self.state['levels'][self.level-1]['start']
        e = self.state['levels'][self.level-1]['end']
        return strtime(s, ifN(e, now)) if s else ''

    def save_state(self):
        with open('state.json', 'w') as fp:
            json.dump(self.state, fp)

    def update(self, current_map):
        now = int(time())

        # continue or reset
        if current_map == LEVEL_TO_MAP.get(self.level):
            # reset case
            if self.state['levels'][self.level-1]['end'] is not None:
                self.state['levels'][self.level-1]['end'] = None
                self.log('instance reset', now)
                self.graph(self.state)
        # stop, start, or noop
        else:
            # stop case
            if self.state['levels'][self.level-1]['start'] is not None and self.state['levels'][self.level-1]['end'] is None:
                self.state['levels'][self.level-1]['end'] = now
                self.log('instance stop', now)
                self.graph(self.state)
            # start case
            if current_map == LEVEL_TO_MAP.get(self.level + 1):
                self.level += 1
                self.state['levels'][self.level-1]['start'] = now
                self.log('instance start', now)

        return self.total_time(now), self.label(), self.instance_time(now)


    def stop(self):
        now = int(time())
        self.state['end'] = now
        self.log('stop', now)
        return self.total_time(now), self.label(), self.instance_time(now)

    def start(self):
        now = int(time())
        self.state['start'] = ifN(self.state['start'], now)
        self.log('start', now)
        return self.total_time(now), self.label(), self.instance_time(now)

    def log(self, action, now):
        self.save_state()
        logging.info("%s total %s level(%d) %s instance %s", action, self.total_time(now), self.level, self.label(), self.instance_time(now))


class FractalTimer(Frame):
    """FractalTimer is a tkinter gui that handles timers and watched the current map"""
    def __init__(self, root, title, args):
        Frame.__init__(self, root)
        self.parent = root
        self.parent.title(title)

        self.memfile = mmap.mmap(-1, 5460, "MumbleLink")
        self.running = False

        if args.state == 'marathon':
            self.state_machine = MarathonState(args.reload, args.graph)
        else:
            self.state_machine = FractalState()

        self.toggle_button_text = StringVar()
        self.total_time_elapsed = StringVar()
        self.sub_instance_text = StringVar()
        self.sub_time_elapsed = StringVar()
        self.toggle_button_text.set('Start')
        self.init_ui()

    def init_ui(self):
        width = 350
        height = 130
        x = (self.parent.winfo_screenwidth() // 2) - (width // 2)
        y = (self.parent.winfo_screenheight() // 2) - (height // 2)
        self.parent.geometry('%dx%d+%d+%d' % (width, height, x, y))

        font = Font(family="impact", size=20)
        self.pack(fill=BOTH, expand=True)

        # Total Time Elapsed
        toggle_button = Button(self, textvariable=self.toggle_button_text, command=self.toggle_timer)
        toggle_button.pack(side=TOP, fill=X)
        total_time_label = Label(self, textvariable=self.total_time_elapsed, font=font)
        total_time_label.pack(side=TOP, padx=0, pady=0, fill=X)

        # Time elapsed since sub-timer reset
        sub_time_label = Label(self, textvariable=self.sub_time_elapsed, font=font)
        sub_time_label.pack(side=BOTTOM, padx=0, pady=0, fill=X)
        sub_instance_label = Label(self, textvariable=self.sub_instance_text, font=font)
        sub_instance_label.pack(side=BOTTOM, padx=0, pady=0, fill=X)

        # Start the updater
        self.tick_tock()

    def toggle_timer(self):
        if self.running:
            self.running = False
            self.toggle_button_text.set('Start')
            self.update_labels(*self.state_machine.stop())
        else:
            self.running = True
            self.toggle_button_text.set('Stop')
            self.update_labels(*self.state_machine.start())

    def update_labels(self, tt, il, it):
        self.total_time_elapsed.set(tt)
        self.sub_time_elapsed.set(it)
        self.sub_instance_text.set(il)

    def tick_tock(self):
        if self.running:
            self.update_labels(*self.state_machine.update(get_player_map(self.memfile)))
        self.parent.after(250, self.tick_tock)


def main():
    parser = argparse.ArgumentParser(description='Fractal Timer')
    parser.add_argument('--state', default='daily', metavar='STATE', type=str, help='which state machine to use')
    parser.add_argument('--graph', action='store_true', help='generate a graph from the marathon state machine')
    parser.add_argument('--reload', action='store_true', help='reload the previous state for marathon state machine')
    args = parser.parse_args()
    logging.basicConfig(filename='fractal.log', level=logging.INFO, format='[%(asctime)-15s]: %(message)s')
    timer = FractalTimer(Tk(), 'Fractal Timer', args)
    atexit.register(lambda: logging.info('exit'))
    timer.parent.mainloop()


if __name__ == '__main__':
    main()
