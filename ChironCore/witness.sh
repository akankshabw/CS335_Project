#!/bin/bash
# Non-interference witness — same public inputs, different secrets.
# differs: :temp=1 vs 0
# Run from the ChironCore/ directory.

echo 'Trace 1: {":n": 3, ":pub": 10, ":secret": 0, ":out": 0, ":temp": 1}'
.venv/bin/python3 chiron.py example/safe_report_leaky.tl -r -d '{":n": 3, ":pub": 10, ":secret": 0, ":out": 0, ":temp": 1}' &

echo 'Trace 2: {":n": 3, ":pub": 10, ":secret": 0, ":out": 0, ":temp": 0}'
.venv/bin/python3 chiron.py example/safe_report_leaky.tl -r -d '{":n": 3, ":pub": 10, ":secret": 0, ":out": 0, ":temp": 0}' &

wait
