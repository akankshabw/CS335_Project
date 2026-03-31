#!/bin/bash
# Non-interference witness — same public inputs, different secrets.
# differs: :secret=180 vs 0
# Run from the ChironCore/ directory.

echo 'Trace 1: {":secret": 180, ":pub": 10}'
.venv/bin/python3 chiron.py example/turtle_turn_leak.tl -r -d '{":secret": 180, ":pub": 10}' &

echo 'Trace 2: {":secret": 0, ":pub": 10}'
.venv/bin/python3 chiron.py example/turtle_turn_leak.tl -r -d '{":secret": 0, ":pub": 10}' &

wait
