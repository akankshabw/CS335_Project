"""
Relational Verifier for Non-Interference.

Tier 1: straight-line programs  → check_non_interference()
Tier 2: single loop, no conditionals in body → check_loop_non_interference()
"""

from z3 import *
from ChironAST import ChironAST
from interfaces.sExecutionInterface import z3Context, handleAssignment, setAttr


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def init_context(params, suffix):
    """
    Create a z3Context where each variable is a Z3 Int named varname+suffix.
    Only variables in params get initialized — others are created on-the-fly
    by handleAssignment when first assigned.
    """
    ctx = z3Context()
    for key in params:
        var = key.replace(":", "")
        setAttr(ctx, var, Int(var + suffix))
    return ctx


def encode_stmts(ctx, stmts):
    """
    Walk a list of IR (stmt, tgt) tuples and update ctx symbolically.
    Silently skips ConditionCommands (handled separately for loops).
    """
    for stmt, tgt in stmts:
        if isinstance(stmt, ChironAST.AssignmentCommand):
            handleAssignment(ctx, stmt)
        elif isinstance(stmt, ChironAST.ConditionCommand):
            pass  # handled at loop level
        # MoveCommand, PenCommand, GotoCommand don't affect variable state


def encode_condition(ctx, cond_stmt):
    """
    Encode a ConditionCommand as a Z3 BoolRef using ctx's variables.
    e.g. ConditionCommand(NEQ(:counter, 0))  →  ctx.counter != 0
    """
    temp = str(cond_stmt).replace(":", "z3Vars.")
    _locals = {"z3Vars": ctx}
    exec(f"exp = {temp}", globals(), _locals)
    return _locals["exp"]


def build_invariant(ctx1, ctx2, inv_var_names):
    """
    Build the relational invariant as a Z3 conjunction:
      INV = ∧ { ctx1.v == ctx2.v  for v in inv_var_names }
    inv_var_names: plain strings without ':', e.g. ["out", "__rep_counter_0"]
    """
    clauses = [getattr(ctx1, v) == getattr(ctx2, v) for v in inv_var_names]
    return And(*clauses)



# ---------------------------------------------------------------------------
# Find loop structure in IR
# ---------------------------------------------------------------------------

def find_loop(ir):
    """
    Scan the IR for a single repeat-loop structure.

    A Chiron loop looks like:
      [head_idx]   ConditionCommand(counter != 0)   tgt > 0
      [...]        body statements
      [head+tgt-1] ConditionCommand(False)           tgt < 0  ← back-edge
      [head+tgt]   ... after loop

    Returns (head_idx, body_start, body_end, exit_idx) or None.
    body_end is exclusive (does not include the back-edge instruction).
    """
    for i, (stmt, tgt) in enumerate(ir):
        if isinstance(stmt, ChironAST.ConditionCommand) and tgt > 0:
            back_idx = i + tgt - 1
            if back_idx < len(ir):
                back_stmt, back_tgt = ir[back_idx]
                # Back-edge is ConditionCommand(False) with negative offset
                if isinstance(back_stmt, ChironAST.ConditionCommand) and back_tgt < 0:
                    return (i, i + 1, back_idx, i + tgt)
    return None


# ---------------------------------------------------------------------------
# Tier 1: straight-line
# ---------------------------------------------------------------------------

def check_non_interference(irHandler, params, low_inputs, low_outputs):
    """
    Non-interference check for straight-line programs (no loops).
    Single Z3 query: encode both traces, constrain low inputs equal,
    ask if low outputs can differ.
    """
    print("\n=== Relational Verifier (Tier 1: straight-line) ===")
    print(f"  Low inputs  : {low_inputs}")
    print(f"  Low outputs : {low_outputs}")

    ctx1 = init_context(params, "_1")
    ctx2 = init_context(params, "_2")

    print("\n  [Trace 1] Encoding...")
    encode_stmts(ctx1, irHandler.ir)
    print("  [Trace 2] Encoding...")
    encode_stmts(ctx2, irHandler.ir)

    solver = Solver()
    for var in low_inputs:
        v = var.replace(":", "")
        solver.add(getattr(ctx1, v) == getattr(ctx2, v))
        print(f"  [Constraint] {v}_1 == {v}_2")

    diverge_clauses = [
        getattr(ctx1, var.replace(":", "")) != getattr(ctx2, var.replace(":", ""))
        for var in low_outputs
    ]
    solver.add(Or(*diverge_clauses))

    print("\n  [Z3] Checking...")
    result = solver.check()
    _report(result, solver, params, low_outputs, ctx1, ctx2)
    print("===================================================\n")
    return str(result)


# ---------------------------------------------------------------------------
# Tier 2: single loop with straight-line body
# ---------------------------------------------------------------------------

def check_loop_non_interference(irHandler, params, low_inputs, low_outputs, inv_vars=None):
    """
    Non-interference check for programs with a single repeat-loop.
    Uses a relational invariant and three Z3 checks:
      1. Initialization  — INV holds when loop is first entered
      2. Preservation    — body execution preserves INV (inductive step)
      3. Consequence     — INV at exit implies low outputs agree

    inv_vars: list of variable names (no ':') that should be equal across
              traces at every loop iteration. Defaults to all low variables
              plus the loop counter.
    """
    print("\n=== Relational Verifier (Tier 2: loop) ===")
    print(f"  Low inputs  : {low_inputs}")
    print(f"  Low outputs : {low_outputs}")

    loop = find_loop(irHandler.ir)
    if loop is None:
        print("  [!] No loop found — falling back to Tier 1.")
        return check_non_interference(irHandler, params, low_inputs, low_outputs)

    head_idx, body_start, body_end, exit_idx = loop
    pre_loop_ir   = irHandler.ir[:head_idx]
    body_ir       = irHandler.ir[body_start:body_end]
    post_loop_ir  = irHandler.ir[exit_idx:]
    loop_cond     = irHandler.ir[head_idx][0]   # ConditionCommand

    print(f"\n  Loop head    : IR[{head_idx}]  condition: {loop_cond}")
    print(f"  Body         : IR[{body_start}:{body_end}]")
    print(f"  Loop exit    : IR[{exit_idx}]")
    print(f"  Post-loop    : IR[{exit_idx}:{len(irHandler.ir)}]  ({len(post_loop_ir)} statements)")

    # Determine invariant variables automatically if not provided
    if inv_vars is None:
        inv_vars = [v.replace(":", "") for v in low_inputs + low_outputs]
        # Add loop counter(s)
        for stmt, _ in irHandler.ir:
            if isinstance(stmt, ChironAST.AssignmentCommand):
                v = str(stmt.lvar).replace(":", "")
                if "__rep_counter_" in v and v not in inv_vars:
                    inv_vars.append(v)

    print(f"  Invariant    : equal across traces for {inv_vars}")

    # ------------------------------------------------------------------
    # Encode pre-loop code for both traces (gives us the loop-entry state)
    # ------------------------------------------------------------------
    ctx1_entry = init_context(params, "_1")
    ctx2_entry = init_context(params, "_2")
    encode_stmts(ctx1_entry, pre_loop_ir)
    encode_stmts(ctx2_entry, pre_loop_ir)

    # Low inputs are equal across traces
    low_input_eq = [
        getattr(ctx1_entry, v.replace(":", "")) == getattr(ctx2_entry, v.replace(":", ""))
        for v in low_inputs
    ]

    # ------------------------------------------------------------------
    # Check 1: Initialization
    # Does INV hold at loop entry (given equal low inputs)?
    # ------------------------------------------------------------------
    print("\n  --- Check 1: Initialization ---")
    s1 = Solver()
    s1.add(*low_input_eq)
    s1.add(Not(build_invariant(ctx1_entry, ctx2_entry, inv_vars)))
    r1 = s1.check()
    _print_check("Initialization", r1,
                 "INV holds at loop entry",
                 "INV does NOT hold at entry — check your invariant or pre-loop code")
    if r1 == sat:
        m = s1.model()
        print("    Counterexample — loop entry state where INV is violated:")
        _show_state(m, inv_vars, ctx1_entry, ctx2_entry)

    # ------------------------------------------------------------------
    # Check 2: Preservation
    # Assume INV + loop condition at head, execute body, check INV still holds.
    # We use fresh Z3 variables for the loop-head state (arbitrary state
    # satisfying INV) so this is truly an inductive argument.
    # ------------------------------------------------------------------
    print("\n  --- Check 2: Preservation (Inductive Step) ---")

    # Fresh symbolic state at loop head (arbitrary, will be constrained by INV)
    ctx1_h = _fresh_ctx(inv_vars + [v.replace(":", "") for v in low_inputs], "_1h")
    ctx2_h = _fresh_ctx(inv_vars + [v.replace(":", "") for v in low_inputs], "_2h")

    # Also need any variables that appear in the body but aren't in inv_vars
    # Copy over all vars from entry context so body can reference them
    _copy_missing_vars(ctx1_entry, ctx1_h, "_1h")
    _copy_missing_vars(ctx2_entry, ctx2_h, "_2h")

    # Execute body on copies of the head context
    ctx1_post = _copy_ctx(ctx1_h)
    ctx2_post = _copy_ctx(ctx2_h)
    encode_stmts(ctx1_post, body_ir)
    encode_stmts(ctx2_post, body_ir)

    s2 = Solver()
    s2.add(build_invariant(ctx1_h, ctx2_h, inv_vars))            # INV holds before body
    s2.add(encode_condition(ctx1_h, loop_cond))                   # loop condition true (trace 1)
    s2.add(encode_condition(ctx2_h, loop_cond))                   # loop condition true (trace 2)
    s2.add(Not(build_invariant(ctx1_post, ctx2_post, inv_vars)))  # INV broken after body?
    r2 = s2.check()
    _print_check("Preservation", r2,
                 "body preserves INV",
                 "body BREAKS INV — your loop leaks or the invariant is too weak")
    if r2 == sat:
        m = s2.model()
        print("    Counterexample — one iteration that breaks INV:")
        print("    Before body (loop head):")
        _show_state(m, inv_vars, ctx1_h, ctx2_h)
        print("    After body:")
        _show_state(m, inv_vars, ctx1_post, ctx2_post)

    # ------------------------------------------------------------------
    # Check 3: Consequence
    # At loop exit, INV holds AND loop condition is false.
    # Encode any post-loop straight-line code, then check if low outputs
    # can diverge.
    # ------------------------------------------------------------------
    print("\n  --- Check 3: Consequence ---")

    # Fresh exit-state variables constrained only by INV + exit condition
    ctx1_e = _fresh_ctx(inv_vars + [v.replace(":", "") for v in low_inputs + low_outputs], "_1e")
    ctx2_e = _fresh_ctx(inv_vars + [v.replace(":", "") for v in low_inputs + low_outputs], "_2e")
    _copy_missing_vars(ctx1_entry, ctx1_e, "_1e")
    _copy_missing_vars(ctx2_entry, ctx2_e, "_2e")

    # Encode post-loop code on top of the exit state
    ctx1_final = _copy_ctx(ctx1_e)
    ctx2_final = _copy_ctx(ctx2_e)
    if post_loop_ir:
        encode_stmts(ctx1_final, post_loop_ir)
        encode_stmts(ctx2_final, post_loop_ir)

    diverge_at_final = Or(*[
        getattr(ctx1_final, v.replace(":", "")) != getattr(ctx2_final, v.replace(":", ""))
        for v in low_outputs
    ])

    s3 = Solver()
    s3.add(build_invariant(ctx1_e, ctx2_e, inv_vars))   # INV at loop exit
    s3.add(Not(encode_condition(ctx1_e, loop_cond)))     # loop exited (trace 1)
    s3.add(Not(encode_condition(ctx2_e, loop_cond)))     # loop exited (trace 2)
    s3.add(diverge_at_final)                             # outputs differ after post-loop?
    r3 = s3.check()
    _print_check("Consequence", r3,
                 "INV at exit + post-loop code implies non-interference",
                 "non-interference fails after post-loop code — invariant too weak or post-loop leaks")
    if r3 == sat:
        m = s3.model()
        print("    Counterexample — exit state where outputs diverge:")
        print("    At loop exit (INV holds here):")
        _show_state(m, inv_vars, ctx1_e, ctx2_e)
        if post_loop_ir:
            print("    After post-loop code:")
            _show_state(m, [v.replace(":", "") for v in low_outputs], ctx1_final, ctx2_final)

    # ------------------------------------------------------------------
    # Overall verdict
    # ------------------------------------------------------------------
    print("\n  --- Overall ---")
    all_unsat = all(r == unsat for r in [r1, r2, r3])
    if all_unsat:
        print("  NON-INTERFERENCE HOLDS (all 3 checks passed)")
    else:
        failed = [name for name, r in [("Init", r1), ("Preservation", r2), ("Consequence", r3)] if r != unsat]
        print(f"  CANNOT PROVE non-interference — failed checks: {failed}")
        print("  Either: (a) the program leaks, or (b) the invariant is too weak.")

    print("===========================================\n")
    return "unsat" if all_unsat else "sat"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fresh_ctx(var_names, suffix):
    """Create a context with fresh Z3 Int vars for each name in var_names."""
    ctx = z3Context()
    for v in set(var_names):
        setAttr(ctx, v, Int(v + suffix))
    return ctx


def _copy_ctx(ctx):
    """Shallow-copy a z3Context so encode_stmts can diverge from the original."""
    new_ctx = z3Context()
    for attr, val in vars(ctx).items():
        setAttr(new_ctx, attr, val)
    return new_ctx


def _copy_missing_vars(src_ctx, dst_ctx, suffix):
    """
    Copy variables that exist on src_ctx but not dst_ctx.
    Used so body references to non-invariant variables still resolve.
    """
    for attr, val in vars(src_ctx).items():
        if not hasattr(dst_ctx, attr):
            setAttr(dst_ctx, attr, Int(attr + suffix))


def _show_state(model, var_names, ctx1, ctx2):
    """
    Print the concrete values of var_names in both traces, evaluated against
    the Z3 model. Used to display counterexamples for loop checks.
    """
    for v in var_names:
        val1 = model.eval(getattr(ctx1, v), model_completion=True)
        val2 = model.eval(getattr(ctx2, v), model_completion=True)
        tag = " <-- DIFFERS" if str(val1) != str(val2) else ""
        print(f"      {v}: trace1={val1}, trace2={val2}{tag}")


def _print_check(name, result, ok_msg, fail_msg):
    if result == unsat:
        print(f"  [PASS] {name}: {ok_msg}")
    elif result == sat:
        print(f"  [FAIL] {name}: {fail_msg}")
    else:
        print(f"  [?]    {name}: Z3 returned UNKNOWN")


def _report(result, solver, params, low_outputs, ctx1, ctx2):
    if result == unsat:
        print("\n    NON-INTERFERENCE HOLDS")
        print("    No choice of secret inputs can cause public outputs to differ.")
    elif result == sat:
        m = solver.model()
        print("\n    VIOLATION FOUND — Counterexample:")
        all_display = list(params.keys()) + [v for v in low_outputs if v not in params]
        for var in all_display:
            v = var.replace(":", "")
            val1 = m.eval(getattr(ctx1, v))
            val2 = m.eval(getattr(ctx2, v))
            tag = " <-- LEAK" if var in low_outputs and str(val1) != str(val2) else ""
            print(f"    {var}: trace1={val1}, trace2={val2}{tag}")
        print()
        print("    With same low inputs, the low outputs differ → information leak.")
    else:
        print(f"\n  ? Z3 returned UNKNOWN: {result}")