#!/usr/bin/env python3
"""Rebuild the static Living Pulse point illustrations (standard library only).

These are decorative, deterministic SVG geometry. No animation loop, cursor
listeners, WebGL dependency, external image service or tracking is needed.
"""
from pathlib import Path
from math import sin, cos, pi
import random

root = Path(__file__).resolve().parents[1] / 'frontend/public/art'
root.mkdir(parents=True, exist_ok=True)
rng = random.Random(42026)

def color(t):
    t = max(0, min(1, t))
    stops = [(118, 246, 201), (113, 203, 236), (134, 108, 238)]
    k = min(1, int(t * 2))
    v = t * 2 - k
    return '#%02x%02x%02x' % tuple(round(a+(b-a)*v) for a,b in zip(stops[k], stops[k+1]))

points = []
for i in range(200):
    u = 2*pi*i/200
    for j in range(44):
        v = 2*pi*(j + .15*sin(u*9))/44
        tube = .65 + .085*sin(7*u+v) + .028*cos(11*u-2*v)
        radius = 1.83 + .095*sin(5*u)
        x = (radius+tube*cos(v))*cos(u)
        y = (radius+tube*cos(v))*sin(u)
        z = tube*sin(v)
        y,z = y*cos(.32)-z*sin(.32),y*sin(.32)+z*cos(.32)
        x,z = x*cos(-.25)+z*sin(-.25),-x*sin(-.25)+z*cos(-.25)
        x,y = x*cos(.15)-y*sin(.15),x*sin(.15)+y*cos(.15)
        scale = 121 * (1+z*.028)
        sx,sy = 360+x*scale+rng.uniform(-.6,.6),360+y*scale+rng.uniform(-.6,.6)
        points.append((z,sx,sy,.68+(z+1.5)*.25,color((sy-70)/585),.44+(z+1.5)*.18))
points.sort()
svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 720" width="720" height="720">']
for z,x,y,r,c,a in points:
    svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="{c}" opacity="{min(.96,a):.2f}"/>')
for _ in range(145):
    x,y=rng.uniform(15,705),rng.uniform(25,695)
    if ((x-360)**2+(y-360)**2)**.5 < 170:
        continue
    svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rng.uniform(.4,1.8):.2f}" fill="{color(y/720)}" opacity="{rng.uniform(.10,.42):.2f}"/>')
svg.append('</svg>')
(root/'living-pulse-ring.svg').write_text(''.join(svg))
svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 180" width="1440" height="180">']
for i in range(190):
    x=i*1440/189
    for j in range(12):
        y=115+31*sin(x/140+j*.17)+j*3.1+15*cos(x/70+j*.05)
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rng.uniform(.45,1.15):.2f}" fill="{color(x/1440)}" opacity="{rng.uniform(.25,.80):.2f}"/>')
svg.append('</svg>')
(root/'living-pulse-field.svg').write_text(''.join(svg))
print('Static Living Pulse SVG assets rebuilt.')
