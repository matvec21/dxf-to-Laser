import ezdxf as dxf
import numpy as np

from tkinter import *
from tkinter import filedialog as fd

speed = 250
laser_power = 650
merge_distance = 0.01
flat_parts = 36
darktheme = False

def intersect(A, B, C, D): # thanks Adam
    def ccw(A, B, C):
        return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

    return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)

class Segment:
    def __init__(self):
        self.parent = None
        self.childs = []

        self.points = []
        self.closed = False

    def lines(self):
        return [[self.points[i], self.points[i + 1]] for i in range(len(self.points) - 1)]

    def bounds(self):
        bounds = np.array([float('inf'), float('inf'), float('-inf'), float('-inf')])

        for point in self.points:
            bounds[0] = np.minimum(bounds[0], point[0])
            bounds[1] = np.minimum(bounds[1], point[1])
            bounds[2] = np.maximum(bounds[2], point[0])
            bounds[3] = np.maximum(bounds[3], point[1])

        return bounds

    def length(self):
        length = 0
        for line in self.lines():
            length += magnitude(line - line[0])
        return length

    def draw(self, canvas, color, k):
        for line in self.lines():
            canvas.create_line(*(line[0] * k + 20), *(line[1] * k + 20), width = 3, fill = color)

class Process:
    def __init__(self):
        self.filename = ''
        self.parsed = []

        self.all_segments = []
        self.main_segments = []

        self.size = []

    def flat(self, obj, _list):
        if obj.dxftype() in ('ARC', 'CIRCLE'):
            points = list(obj.flattening(0.36 / flat_parts))
        else:
            points = list(obj.flattening(float('inf'), flat_parts))

        for i in range(len(points) - 1):
            _list.append(np.array([points[i].vec2, points[i + 1].vec2]))

    def load(self, file):
        self.filename = file
        data = dxf.readfile(file).modelspace()
        self.parsed = []

        l = len(data)
        count = 0

        for e in data:
            count += 1
            dtype = e.dxftype()

            if dtype == 'LINE':
                self.parsed.append(np.array([e.dxf.start.vec2, e.dxf.end.vec2]))

            elif dtype in ('CIRCLE', 'ARC', 'ELLIPSE', 'SPLINE'):
                self.flat(e, self.parsed)

            elif dtype == 'LWPOLYLINE':
                points = e.get_points()
                for i in range(len(points) - 1):
                    self.parsed.append(np.array([points[i][:2], points[i + 1][:2]]))

            elif dtype == 'INSERT':
                for line in e.block():
                    self.parsed.append(np.array([line.dxf.start.vec2, line.dxf.end.vec2]))

            elif dtype == 'IMAGE':
                self.process_image(e)

            x0, y0, x1, y1 = canvas.coords(progress_bar)
            canvas.coords(progress_bar, x0, y0, 55 + 490 / 3 * (count + 1) / l, y1)
            win.update()

    def update_bounds(self):
        bounds = np.array([float('inf'), float('inf'), float('-inf'), float('-inf')])

        for line in self.parsed:
            for pos in line:
                bounds[0] = np.minimum(bounds[0], pos[0])
                bounds[1] = np.minimum(bounds[1], pos[1])
                bounds[2] = np.maximum(bounds[2], pos[0])
                bounds[3] = np.maximum(bounds[3], pos[1])

        self.size = np.array([bounds[2] - bounds[0], bounds[3] - bounds[1]])
        self.update_center(bounds)

    def update_center(self, bounds):
        for line in self.parsed:
            for i in range(2):
                line[i] -= bounds[:2]

    def create_segments(self):
        self.all_segments.clear()

        class Pointer:
            def __init__(self, l):
                self.l = l

            def __getitem__(self, i):
                return self.l[i]

        pointers = [Pointer(line) for line in self.parsed]
        l = len(pointers)

        while pointers:
            pointer = pointers[0]
            pointers.remove(pointer)

            segment = Segment()
            [segment.points.append(pos) for pos in pointer]
            self.all_segments.append(segment)
            last = pointer[1]

            while 1:
                stop = True
                for next in pointers:
                    ok = True
                    if magnitude(next[1] - last) < merge_distance:
                        segment.points.append(next[0])
                    elif magnitude(next[0] - last) < merge_distance:
                        segment.points.append(next[1])
                    else:
                        ok = False

                    if ok:
                        last = segment.points[-1]
                        pointers.remove(next)

                        if len(pointers) % 10 == 0:
                            x0, y0, x1, y1 = canvas.coords(progress_bar)
                            canvas.coords(progress_bar, x0, y0, 55 + 490 / 3 * (1 - len(pointers) / l + 1), y1)
                            win.update()

                        stop = False
                        break
                if stop:
                    break

            if magnitude(segment.points[0] - segment.points[-1]) < merge_distance:
                segment.points[-1] = segment.points[0].copy()
                segment.closed = True

    def point_in_segment(self, point, segment):
        ray = [point, self.size + 10]

        intersects = 0
        for line in segment.lines():
            if intersect(*ray, *line):
                intersects += 1

        return intersects % 2 == 1

    def create_hierarchy(self):
        self.main_segments.clear()

        l = len(self.all_segments)
        for s1 in self.all_segments:
            x0, y0, x1, y1 = canvas.coords(progress_bar)
            canvas.coords(progress_bar, x0, y0, 55 + 490 / 3 * (self.all_segments.index(s1) / l + 2), y1)
            win.update()

            if not s1.closed:
                continue

            for s2 in self.all_segments:
                if s1 == s2 or not s2.closed:
                    continue

                if self.point_in_segment(s2.points[0], s1):
                    s1.childs.append(s2)
                    s2.parent = s1

                    if s1.parent is not None and s2 in s1.parent.childs:
                        s1.parent.childs.remove(s2)

        for segment in self.all_segments:
            if segment.parent is None:
                self.main_segments.append(segment)

    def process_image(self, e): # TODO
        pos = e.dxf.insert
        angle = np.math.atan2(*list(e.dxf.u_pixel.vec2)[::-1])

        file = e.image_def.dxf.filename
        size = e.dxf.image_size
        factor = e.image_def.dxf.pixel_size
#        print(e.image_def.dxf.filename, np.rad2deg(angle), size, factor)

    def _update_canvas(self, segment, level, colors, k):
        segment.draw(canvas, colors[level], k)
        if segment.childs:
            [self._update_canvas(child, level + 1, colors, k) for child in segment.childs]

    def update_canvas(self):
        canvas.delete('all')

        k = 560 / self.size[0]
        h = (self.size[1] * k + 40)

        pos = k * 10
        while pos < 560:
            canvas.create_line(20 + pos, 20, 20 + pos, 580, fill = 'gray15' if darktheme else 'gray75')
            canvas.create_line(20, 20 + pos, 580, 20 + pos, fill = 'gray15' if darktheme else 'gray75')
            pos += k * 10
        canvas.create_text(20 + k * 10, 10, text = '%imm' % (10), fill = 'gray18' if darktheme else 'gray72')

        canvas.create_line(20, 20, 600 - 20, 20, arrow = LAST, fill = 'royal blue', width = 3)
        canvas.create_line(20, 20, 20, h - 20, arrow = LAST, fill = 'lime', width = 3)

        canvas.create_text(551, 11, text = 'Ширина %.3f' % self.size[0], fill = 'black')
        canvas.create_text(550, 10, text = 'Ширина %.3f' % self.size[0], fill = 'royal blue')

        canvas.create_text(11, h - 50, text = 'Высота %.3f' % self.size[1], fill = 'black', angle = 90)
        canvas.create_text(10, h - 50, text = 'Высота %.3f' % self.size[1], fill = 'lime', angle = 90)

        colors = ['#%0.2X%0.2X%0.2X' % tuple(np.random.randint(0, 255, size = (3, ))) for i in range(10)]

        for segment in self.main_segments:
            self._update_canvas(segment, 0, colors, k)

        win.geometry('%ix%i' % (600, h + 120))
        canvas.configure(width = 600, height = h)
        timel.place(x = 40, y = h + 91)
        updateb.place(x = 449, y = h + 91)
        colorsb.place(x = 299, y = h + 91)

    def get_closest(self, segments, point):
        mins, mind = None, float('inf')
        for segment in segments:
            for pos in [segment.points[0]]: # segment.bounds():
                d = magnitude(pos - point)
                if mind > d:
                    mind = d
                    mins = segment
        return mins

    def create_path(self, segments, start):
        class Path:
            def __init__(self, segment):
                self.s = segment
                self.start = segment.points[0]
                self.end = segment.points[-1]
                self.min = float('inf')
                self.path = []

        paths = [Path(s) for s in segments if s != start]

        start = Path(start)
        start.min = 0
        paths.insert(0, start)

        for path1 in paths:
            for path2 in paths:
                if path1 == path2:
                    continue

                d = path1.min + magnitude(path1.end - path2.start)
                if d < path2.min:
                    path2.min = d
                    path2.path = path1.path.copy() + [path1.s]

    def calculate_time(self):
        time, last = 0, np.zeros(2)

        layers, next = [], [s for s in self.main_segments if s.closed]
        while next:
            layers.append(next)

            l = []
            for segment in next:
                l.extend([s for s in segment.childs if s.closed])
            next = l

        nonclosed = [s for s in self.all_segments if not s.closed]
        if nonclosed:
            self.sort_by_distance(nonclosed, last)
            last = nonclosed[-1].points[-1]

        for layer in reversed(layers):
            self.sort_by_distance(layer, last)
            last = layer[-1].points[-1]

        last = np.zeros(2)
        for layer in [nonclosed] + layers:
            for segment in layer:
                time += magnitude(last - segment.points[0]) + segment.length()
                last = segment.points[-1]

        return time / speed * 60

    def sort_by_distance(self, list, point):
        sorted = []
        last = point
        segments = list.copy()

        while segments:
            closest = self.get_closest(segments, last)
            segments.remove(closest)
            sorted.append(closest)
            last = closest.points[-1]

        list.clear()
        list.extend(sorted)

    def generate_gcode(self):
        def disable_laser():
            return 'G0M5\n'

        def enable_laser():
            return 'G1M3F1\n'

        def pos(point, first = False):
            if not first:
                return 'X%.4fY%.4f\n' % tuple(point)
            else:
                return 'G1X%.4fY%.4fF%.4f\n' % (*point, speed)

        def offset(point):
            cmd = disable_laser()
            cmd += 'G0X%.4fY%.4f\n' % tuple(point)
            cmd += enable_laser()
            return cmd

        def add(a):
            cmd = pos(a[0], True)
            for p in a[1:]:
                cmd += pos(p)
            return cmd

        cmd = ''
        if not self.main_segments:
            return 'Error'

        saveb.configure(text = 'Генерируем...')
        win.update()

        layers, next = [], [s for s in self.main_segments if s.closed]
        while next:
            layers.append(next)

            l = []
            for segment in next:
                l.extend([s for s in segment.childs if s.closed])
            next = l

        last = np.zeros(2)
        nonclosed = [s for s in self.all_segments if not s.closed]
        if nonclosed:
            self.sort_by_distance(nonclosed, last)
            last = nonclosed[-1].points[-1]

        for layer in reversed(layers):
            self.sort_by_distance(layer, last)
            last = layer[-1].points[-1]

        first = True
        for segment in nonclosed:
            if not first:
                cmd += offset(segment.points[0])
            else:
                cmd += start_strokes % (laser_power, *segment.points[0])
                first = False
            cmd += add(segment.points[1:])

        for layer in reversed(layers):
            for segment in layer:
                if not first:
                    cmd += offset(segment.points[0])
                else:
                    cmd += start_strokes % (laser_power, *segment.points[0])
                    first = False
                cmd += add(segment.points[1:])

        cmd += end_strokes
        return cmd

def magnitude(v):
    return np.sqrt(np.sum(np.power(v, 2)))

def choose_file():
    file = fd.askopenfilename(filetypes = [('DXF Files', '*.dxf'), ('All files', '*.*')])
    if file == '':
        return

    process.filename = file
    reload()

def reload():
    global progress_bar

    canvas.delete('all')
    canvas.create_rectangle(50, int(canvas['height']) // 2 - 30, 550, int(canvas['height']) // 2 + 30, fill = 'black')
    progress_bar = canvas.create_rectangle(55, int(canvas['height']) // 2 - 25, 55, int(canvas['height']) // 2 + 25, fill = 'gray85')
    win.update()

    process.load(process.filename)
    process.update_bounds()
    process.create_segments()
    process.create_hierarchy()
    process.update_canvas()

    t = process.calculate_time()
    timel.configure(text = 'Расчетное время %02i:%02i' % (t // 60, t % 60))

    saveb.configure(state = NORMAL, text = 'Сохранить GCODE', fg = 'white' if darktheme else 'SystemButtonText')

def save_gcode():
    if not process.all_segments:
        return

    file = fd.asksaveasfilename(filetypes = [('GCODE Files', '*.nc'), ('All files', '*.*')])
    if file == '':
        return

    if file[-3:] != '.nc':
        file += '.nc'

    cmd = process.generate_gcode()

    file = open(file, 'w')
    file.write(cmd)
    file.close()

    saveb.configure(text = 'Успешно!', fg = 'lime')

def change_theme():
    save_settings()

    if darktheme == 1:
        change_dark_theme()
    else:
        change_light_theme()

    if process.main_segments:
        process.update_canvas()

def change_dark_theme():
    win.configure(bg = 'gray21')
    canvas.configure(bg = 'gray12', highlightbackground = 'black')
    for c in win.winfo_children():
        _class = c.winfo_class()
        if _class in ('Button', 'Entry'):
            c.configure(bg = 'gray5', fg = 'white')
        elif _class in ('Checkbutton', 'Label'):
            c.configure(bg = 'gray21', fg = 'gray80')

        if _class == 'Entry':
            c.configure(insertbackground = 'white')

def change_light_theme():
    win.configure(bg = 'SystemButtonFace')
    canvas.configure(bg = 'lightgrey', highlightbackground = 'grey')
    for c in win.winfo_children():
        _class = c.winfo_class()
        if _class in ('Button', 'Label', 'Checkbutton'):
            c.configure(bg = 'SystemButtonFace', fg = 'SystemButtonText')
        elif _class in ('Entry', ):
            c.configure(bg = 'SystemWindow', fg = 'SystemWindowText')

        if _class == 'Entry':
            c.configure(insertbackground = 'black')

def save_settings(*a):
    file = open('settings.dat', 'w')
    file.write(speed_entry_sv.get() + '\n' + laser_power_entry_sv.get() + '\n' + merge_distance_entry_sv.get() + '\n' + flat_parts_entry_sv.get() + '\n' + str(darktheme_var.get()))
    file.close()

    load_settings()

def load_settings():
    global speed, laser_power, merge_distance, flat_parts, darktheme

    try:
        file = open('settings.dat', 'r')
    except:
        return
    data = file.read().split('\n')
    file.close()

    try:
        speed = float(data[0])
        laser_power = int(data[1])
        merge_distance = float(data[2])
        flat_parts = int(data[3])
        darktheme = int(data[4])
    except:
        pass

process = Process()

win = Tk()
#win.title('GCODE Converter')
win.title('ROBOTECA Laser')
win.geometry('600x700')

import os, sys

datafile = 'icon.ico'
if not hasattr(sys, 'frozen'):
    datafile = os.path.join(os.path.dirname(__file__), datafile)
else:
    datafile = os.path.join(sys.prefix, datafile)
win.iconbitmap(default = datafile)

Button(text = 'Выбрать DXF файл', command = choose_file).place(x = 30, y = 15)
saveb = Button(text = 'Сохранить GCODE', command = save_gcode, state = DISABLED)
saveb.place(x = 30, y = 43)

load_settings()

speed_entry_sv = StringVar()
speed_entry_sv.set(str(speed))
laser_power_entry_sv = StringVar()
laser_power_entry_sv.set(str(laser_power))
merge_distance_entry_sv = StringVar()
merge_distance_entry_sv.set(str(merge_distance))
flat_parts_entry_sv = StringVar()
flat_parts_entry_sv.set(str(flat_parts))
darktheme_var = IntVar()
darktheme_var.set(darktheme)

Label(text = 'Скорость (мм/мин)').place(x = 424, y = 2)

speed_entry_sv.trace_add('write', save_settings)
speed_entry = Entry(width = 6, textvariable = speed_entry_sv)
speed_entry.place(x = 550, y = 2)

Label(text = 'Мощность лазера (промилли)').place(x = 364, y = 62)

laser_power_entry_sv.trace_add('write', save_settings)
laser_power_entry = Entry(width = 6, textvariable = laser_power_entry_sv)
laser_power_entry.place(x = 550, y = 62)

Label(text = 'Макс. расстояние соединения').place(x = 365, y = 22)

merge_distance_entry_sv.trace_add('write', save_settings)
merge_distance_entry = Entry(width = 6, textvariable = merge_distance_entry_sv)
merge_distance_entry.place(x = 550, y = 22)

Label(text = 'Кол. точек эллипса').place(x = 425, y = 42)

flat_parts_entry_sv.trace_add('write', save_settings)
flat_parts_entry = Entry(width = 6, textvariable = flat_parts_entry_sv)
flat_parts_entry.place(x = 550, y = 42)

darktheme_check = Checkbutton(text = 'Темная тема\n(+21% к крутости)', variable = darktheme_var, command = change_theme)
darktheme_check.place(x = 195, y = 23)

canvas = Canvas(width = 600, height = 600, highlightthickness = 2, highlightbackground = 'grey', bg = 'lightgrey')
canvas.place(x = 0, y = 84)

timel = Label(text = '', width = 20, bg = 'lightblue')
timel.place(x = 40, y = -100)

updateb = Button(text = 'Обновить', width = 20, command = reload)
updateb.place(x = 449, y = -100)

colorsb = Button(text = 'Новые цвета', width = 20, command = process.update_canvas)
colorsb.place(x = 299, y = -100)

if darktheme:
    change_dark_theme()

start_strokes = '''G0M5.000
G0X0.000Y0.000S%04iM3
G0X%.4fY%.4fM5.000
G1M3.000F1.0'''

end_strokes = '''G0M5.000
G0X0.000Y0.000
G0M5.000
G0X0Y0
M30'''

win.mainloop()
