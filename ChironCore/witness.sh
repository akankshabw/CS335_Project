#!/bin/bash
# Non-interference witness — same public inputs, different secrets.
# differs: :secret=0 vs 1
# Run from the ChironCore/ directory.

echo 'Trace 1: {":pub": 10, ":secret": 0, ":n": 10}'
.venv/bin/python3 chiron.py example/turtle_zigzag_leak.tl -r -d '{":pub": 10, ":secret": 0, ":n": 10}' &

echo 'Trace 2: {":pub": 10, ":secret": 1, ":n": 10}'
.venv/bin/python3 chiron.py example/turtle_zigzag_leak.tl -r -d '{":pub": 10, ":secret": 1, ":n": 10}' &

wait
