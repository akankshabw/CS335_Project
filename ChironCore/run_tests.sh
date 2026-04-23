#!/bin/bash
# Run all relational verifier examples (no turtle programs) and dump output to output.txt
# Activate kachua env before running: conda activate kachua && bash run_tests.sh

cd "$(dirname "$0")"

OUT="output.txt"
> "$OUT"   # truncate/create

run() {
    local label="$1"
    shift
    echo "================================================================" >> "$OUT"
    echo "TEST: $label" >> "$OUT"
    echo "CMD:  python3 $*" >> "$OUT"
    echo "----------------------------------------------------------------" >> "$OUT"
    python3 "$@" 2>&1 >> "$OUT"
    echo "" >> "$OUT"
}

# ----------------------------------------------------------------
# Non-interference -- Tier 1 (straight-line)
# ----------------------------------------------------------------

run "ni_safe" \
    chiron.py example/ni_safe.tl -rv \
    -d '{":pub":0, ":secret":0, ":out":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

run "ni_safe2" \
    chiron.py example/ni_safe2.tl -rv \
    -d '{":pub":0, ":secret":0, ":out":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

run "ni_safe3" \
    chiron.py example/ni_safe3.tl -rv \
    -d '{":pub":0, ":secret":0, ":out":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

run "ni_safe4" \
    chiron.py example/ni_safe4.tl -rv \
    -d '{":pub":0, ":secret":0, ":out":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

run "ni_leak" \
    chiron.py example/ni_leak.tl -rv \
    -d '{":pub":0, ":secret":0, ":out":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

run "ni_leak2" \
    chiron.py example/ni_leak2.tl -rv \
    -d '{":pub":0, ":secret":0, ":out":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

run "ni_leak3" \
    chiron.py example/ni_leak3.tl -rv \
    -d '{":pub":0, ":secret":0, ":out":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

run "ni_leak4" \
    chiron.py example/ni_leak4.tl -rv \
    -d '{":pub":0, ":secret":0, ":out":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

# ----------------------------------------------------------------
# Non-interference -- Tier 2 (single loop)
# ----------------------------------------------------------------

run "loop_safe" \
    chiron.py example/loop_safe.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

run "loop_leak" \
    chiron.py example/loop_leak.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

run "loop_postloop_safe" \
    chiron.py example/loop_postloop_safe.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

run "loop_postloop_leak" \
    chiron.py example/loop_postloop_leak.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

run "leaky_nontrivial" \
    chiron.py example/leaky_nontrivial.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0, ":temp":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

run "safe_report_leaky" \
    chiron.py example/safe_report_leaky.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0, ":temp":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

# ----------------------------------------------------------------
# Non-interference -- Tier 2 with non-trivial invariants (annotated)
# ----------------------------------------------------------------

run "safe_annotated" \
    chiron.py example/safe_annotated.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0, ":temp":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

run "annot_sum_parts" \
    chiron.py example/annot_sum_parts.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0, ":a":0, ":b":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

run "annot_running_diff" \
    chiron.py example/annot_running_diff.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0, ":x":0, ":y":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

run "annot_double_masked" \
    chiron.py example/annot_double_masked.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0, ":acc":0, ":mask":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

run "annot_cancel_loop" \
    chiron.py example/annot_cancel_loop.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0, ":temp":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

run "annot_leaky" \
    chiron.py example/annot_leaky.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0, ":acc":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

# ----------------------------------------------------------------
# Non-interference -- Tier 2 with .inv sidecar invariants
# ----------------------------------------------------------------

run "safe_nontrivial_inv" \
    chiron.py example/safe_nontrivial_inv.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0, ":temp":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

run "safe_sum_inv" \
    chiron.py example/safe_sum_inv.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0, ":a":0, ":b":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

run "safe_masked_counter" \
    chiron.py example/safe_masked_counter.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0, ":counter":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

run "safe_running_diff" \
    chiron.py example/safe_running_diff.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0, ":x":0, ":y":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

run "safe_cancel_loop" \
    chiron.py example/safe_cancel_loop.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0, ":temp":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

# ----------------------------------------------------------------
# Non-interference -- Tier 3 (conditionals)
# ----------------------------------------------------------------

run "cond_safe" \
    chiron.py example/cond_safe.tl -rv \
    -d '{":pub":0, ":secret":0, ":out":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

run "cond_leak" \
    chiron.py example/cond_leak.tl -rv \
    -d '{":pub":0, ":secret":0, ":out":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

run "cond_safe_both_branches" \
    chiron.py example/cond_safe_both_branches.tl -rv \
    -d '{":pub":0, ":secret":0, ":out":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

run "cond_implicit_leak" \
    chiron.py example/cond_implicit_leak.tl -rv \
    -d '{":pub":0, ":secret":0, ":out":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

run "cond_nested_leak" \
    chiron.py example/cond_nested_leak.tl -rv \
    -d '{":pub":0, ":secret":0, ":out":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

run "cond_nested_safe" \
    chiron.py example/cond_nested_safe.tl -rv \
    -d '{":pub":0, ":secret":0, ":out":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

run "cond_nested_deep" \
    chiron.py example/cond_nested_deep.tl -rv \
    -d '{":pub":0, ":secret":0, ":out":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

run "loop_cond_leak" \
    chiron.py example/loop_cond_leak.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

run "loop_cond_safe" \
    chiron.py example/loop_cond_safe.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

# ----------------------------------------------------------------
# Non-interference -- Timing side-channel
# ----------------------------------------------------------------

run "timing_leak" \
    chiron.py example/timing_leak.tl -rvl \
    -d '{":pub":0, ":secret":0, ":out":0, ":temp":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

run "timing_value_leak" \
    chiron.py example/timing_value_leak.tl -rvl \
    -d '{":pub":0, ":secret":0, ":out":0}' \
    --low_in '[":pub"]' --low_out '[":out"]'

run "timing_safe" \
    chiron.py example/timing_safe.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":out":0}' \
    --low_in '[":pub",":n"]' --low_out '[":out"]'

# ----------------------------------------------------------------
# Non-interference -- Tier 2b (multiple sequential loops)
# ----------------------------------------------------------------

run "multi_loop_safe" \
    chiron.py example/multi_loop_safe.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":m":3, ":out1":0, ":out2":0}' \
    --low_in '[":pub",":n",":m"]' --low_out '[":out1",":out2"]'

run "multi_loop_leak" \
    chiron.py example/multi_loop_leak.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":m":3, ":out1":0, ":out2":0}' \
    --low_in '[":pub",":n",":m"]' --low_out '[":out1",":out2"]'

run "multi_loop_inv_safe" \
    chiron.py example/multi_loop_inv_safe.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":m":3, ":acc":0, ":total":0}' \
    --low_in '[":pub",":n",":m"]' --low_out '[":total"]'

run "multi_loop_annot_safe" \
    chiron.py example/multi_loop_annot_safe.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":sum":0, ":diff":0, ":temp":0}' \
    --low_in '[":pub",":n"]' --low_out '[":sum",":diff"]'

run "multi_loop_inbw_leak" \
    chiron.py example/multi_loop_inbw_leak.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":sum":0, ":diff":0, ":temp":0}' \
    --low_in '[":pub",":n"]' --low_out '[":sum",":diff"]'

run "ml_between_cancel_safe" \
    chiron.py example/ml_between_cancel_safe.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":m":3, ":out":0, ":carry":0, ":k":0}' \
    --low_in '[":pub",":n",":m"]' --low_out '[":out"]'

run "ml_carry_leak" \
    chiron.py example/ml_carry_leak.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":m":3, ":out":0, ":carry":0}' \
    --low_in '[":pub",":n",":m"]' --low_out '[":out"]'

run "ml_double_accum_safe" \
    chiron.py example/ml_double_accum_safe.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":m":3, ":acc1":0, ":acc2":0}' \
    --low_in '[":pub",":n",":m"]' --low_out '[":acc1",":acc2"]'

run "ml_implicit_flow_leak" \
    chiron.py example/ml_implicit_flow_leak.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":m":3, ":out":0, ":flag":0}' \
    --low_in '[":pub",":n",":m"]' --low_out '[":out"]'

run "ml_secret_masked_safe" \
    chiron.py example/ml_secret_masked_safe.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":m":3, ":out":0, ":temp":0}' \
    --low_in '[":pub",":n",":m"]' --low_out '[":out"]'

run "ml_three_loops_safe" \
    chiron.py example/ml_three_loops_safe.tl -rvl \
    -d '{":pub":0, ":secret":0, ":n":5, ":m":3, ":l":2, ":a":0, ":b":0, ":out":0}' \
    --low_in '[":pub",":n",":m",":l"]' --low_out '[":out"]'

# ----------------------------------------------------------------
# Symmetry-2
# ----------------------------------------------------------------

run "sym_safe" \
    chiron.py example/sym_safe.tl \
    --sym '[":a",":b"]' --low_out '[":out"]' \
    -d '{":a":0, ":b":0, ":out":0}'

run "sym_leak" \
    chiron.py example/sym_leak.tl \
    --sym '[":a",":b"]' --low_out '[":out"]' \
    -d '{":a":0, ":b":0, ":out":0}'

run "sym_cond_max" \
    chiron.py example/sym_cond_max.tl \
    --sym '[":a",":b"]' --low_out '[":out"]' \
    -d '{":a":0, ":b":0, ":out":0}'

run "sym_cond_asym" \
    chiron.py example/sym_cond_asym.tl \
    --sym '[":a",":b"]' --low_out '[":out"]' \
    -d '{":a":0, ":b":0, ":out":0}'

run "sym_nested_cond_sym" \
    chiron.py example/sym_nested_cond_sym.tl \
    --sym '[":a",":b"]' --low_out '[":out"]' \
    -d '{":a":0, ":b":0, ":out":0}'

run "sym_multiout_partial" \
    chiron.py example/sym_multiout_partial.tl \
    --sym '[":a",":b"]' --low_out '[":out1",":out2"]' \
    -d '{":a":0, ":b":0, ":out1":0, ":out2":0}'

run "sym_loop_cond_sym" \
    chiron.py example/sym_loop_cond_sym.tl \
    --sym '[":a",":b"]' --low_out '[":out"]' \
    -d '{":a":0, ":b":0, ":n":0, ":out":0}'

run "sym_loop_cond_asym" \
    chiron.py example/sym_loop_cond_asym.tl \
    --sym '[":a",":b"]' --low_out '[":out"]' \
    -d '{":a":0, ":b":0, ":n":0, ":out":0}'

run "sym_loop_commute" \
    chiron.py example/sym_loop_commute.tl \
    --sym '[":a",":b"]' --low_out '[":out"]' \
    -d '{":a":0, ":b":0, ":n":0, ":m":0, ":out":0}'

run "sym_loop_asym" \
    chiron.py example/sym_loop_asym.tl \
    --sym '[":a",":b"]' --low_out '[":out"]' \
    -d '{":a":0, ":b":0, ":n":0, ":m":0, ":out":0}'

# ----------------------------------------------------------------
# Monotonicity
# ----------------------------------------------------------------

run "mono_safe" \
    chiron.py example/mono_safe.tl \
    --mono ':x' --low_out '[":out"]' \
    -d '{":x":0, ":pub":0, ":out":0, ":temp":0}'

run "mono_unsafe" \
    chiron.py example/mono_unsafe.tl \
    --mono ':x' --low_out '[":out"]' \
    -d '{":x":0, ":pub":0, ":out":0}'

run "mono_loop_safe" \
    chiron.py example/mono_loop_safe.tl \
    --mono ':x' --low_out '[":out"]' \
    -d '{":x":0, ":n":0, ":out":0}'

run "mono_loop_unsafe" \
    chiron.py example/mono_loop_unsafe.tl \
    --mono ':x' --low_out '[":out"]' \
    -d '{":x":0, ":n":0, ":out":0}'

run "mono_multiloop_safe" \
    chiron.py example/mono_multiloop_safe.tl \
    --mono ':x' --low_out '[":out"]' \
    -d '{":x":0, ":n":0, ":m":0, ":out":0}'

# ----------------------------------------------------------------

echo "Done. Output written to $OUT"
