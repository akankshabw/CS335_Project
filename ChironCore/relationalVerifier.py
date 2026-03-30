"""
Relational Verifier for Non-Interference.

Tier 1: straight-line / conditional programs -> check_non_interference()
Tier 2: single loop (body may contain conditionals) -> check_loop_non_interference()

Turtle extension:
  When turtle_x or turtle_y appears in low_outputs, the verifier runs two checks:
    1. Final-position safety  -- can the turtle end at a different (x,y)?
    2. Path safety            -- can any individual move-step amount differ?
  Path safety is strictly stronger: path-safe => position-safe, not vice versa.
  Both checks trigger automatically when turtle_x or turtle_y is in low_outputs.
"""

import os
import re
from z3 import *
from ChironAST import ChironAST
from interfaces.sExecutionInterface import (
    z3Context, handleAssignment, setAttr, convertExp
)


# ---------------------------------------------------------------------------
# Turtle helpers
# ---------------------------------------------------------------------------

def _is_turtle_check(low_outputs):
    """Return True when turtle_x or turtle_y is declared as a low output."""
    lows = {v.replace(":", "") for v in low_outputs}
    return bool(lows & {"turtle_x", "turtle_y"})


def _init_turtle(ctx):
    """
    Lazily initialise turtle geometric state to origin (0,0) heading East (0 deg).
    Heading convention (same as Python turtle):
      0=East  90=North  180=West  270=South
    No-op if already initialised.
    """
    if not hasattr(ctx, 'turtle_x'): setattr(ctx, 'turtle_x', IntVal(0))
    if not hasattr(ctx, 'turtle_y'): setattr(ctx, 'turtle_y', IntVal(0))
    if not hasattr(ctx, 'turtle_h'): setattr(ctx, 'turtle_h', IntVal(0))


def _count_turtle_steps(ctx):
    """Return the number of turtle_step_N attributes already on ctx."""
    n = 0
    while hasattr(ctx, f'turtle_step_{n}'):
        n += 1
    return n


def handle_move(ctx, stmt):
    """
    Symbolically execute one MoveCommand:
      - Updates turtle_x, turtle_y, turtle_h on ctx.
      - Saves the step amount as ctx.turtle_step_N for path-safety checks.

    Heading normalisation: ((h % 360) + 360) % 360 keeps value in [0,359]
    even when turns produce negative values.
    """
    _init_turtle(ctx)

    # Evaluate the move expression in the current context
    amt_str = str(stmt.expr).replace(":", "z3Vars.")
    amt = convertExp(ctx, amt_str)
    # convertExp returns a plain Python int for literal constants (e.g. "90").
    # Wrap in IntVal so Z3 can handle it uniformly everywhere.
    if isinstance(amt, (int, float)):
        amt = IntVal(int(amt))

    # Record step amount (path-safety check uses this later)
    idx = _count_turtle_steps(ctx)
    setattr(ctx, f'turtle_step_{idx}', amt)

    # Normalised heading guaranteed in [0, 359]
    h = (ctx.turtle_h % 360 + 360) % 360
    x, y = ctx.turtle_x, ctx.turtle_y

    if stmt.direction == "forward":
        ctx.turtle_x = If(h == 0,   x + amt, If(h == 180, x - amt, x))
        ctx.turtle_y = If(h == 90,  y + amt, If(h == 270, y - amt, y))
    elif stmt.direction == "backward":
        ctx.turtle_x = If(h == 0,   x - amt, If(h == 180, x + amt, x))
        ctx.turtle_y = If(h == 90,  y - amt, If(h == 270, y + amt, y))
    elif stmt.direction == "right":
        ctx.turtle_h = ctx.turtle_h - amt
    elif stmt.direction == "left":
        ctx.turtle_h = ctx.turtle_h + amt


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def init_context(params, suffix):
    """
    Create a z3Context where each variable is a Z3 Int named varname+suffix.
    Only variables in params get initialized; others are created on-the-fly
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
    Handles AssignmentCommand, MoveCommand, and ConditionCommand (if/if-else).

    Conditional IR layout (built by builder.py):
      if-else: [cond, tgt=len(then)+2] then... [BoolFalse, tgt2=len(else)+1] else...
      if-only: [cond, tgt=len(then)+1] then...
    Both branches are symbolically executed and merged with Z3 If.
    """
    i = 0
    while i < len(stmts):
        stmt, tgt = stmts[i]
        if isinstance(stmt, ChironAST.AssignmentCommand):
            handleAssignment(ctx, stmt)
            i += 1
        elif isinstance(stmt, ChironAST.MoveCommand):
            handle_move(ctx, stmt)
            i += 1
        elif isinstance(stmt, ChironAST.ConditionCommand):
            # Skip loop backedges (negative tgt) and unconditional jumps (BoolFalse)
            if tgt <= 0 or str(stmt) == 'False':
                i += 1
                continue

            # Check for if-else vs if-only by looking for BoolFalse jump
            jump_idx = i + tgt - 1
            is_if_else = (jump_idx < len(stmts) and
                          isinstance(stmts[jump_idx][0], ChironAST.ConditionCommand) and
                          str(stmts[jump_idx][0]) == 'False' and
                          stmts[jump_idx][1] > 0)

            cond_z3 = encode_condition(ctx, stmt)

            if is_if_else:
                then_stmts = stmts[i + 1 : jump_idx]
                tgt2 = stmts[jump_idx][1]
                else_stmts = stmts[i + tgt : i + tgt + tgt2 - 1]

                ctx_then = _copy_ctx(ctx)
                encode_stmts(ctx_then, then_stmts)

                ctx_else = _copy_ctx(ctx)
                encode_stmts(ctx_else, else_stmts)

                _merge_contexts(ctx, cond_z3, ctx_then, ctx_else)
                i = i + tgt + tgt2 - 1
            else:
                # if-only (no else branch)
                then_stmts = stmts[i + 1 : i + tgt]

                ctx_then = _copy_ctx(ctx)
                encode_stmts(ctx_then, then_stmts)

                ctx_else = _copy_ctx(ctx)  # unchanged original
                _merge_contexts(ctx, cond_z3, ctx_then, ctx_else)
                i = i + tgt
        else:
            i += 1


def encode_condition(ctx, cond_stmt):
    """
    Encode a ConditionCommand as a Z3 BoolRef using ctx's variables.
    e.g. ConditionCommand(NEQ(:counter, 0))  ->  ctx.counter != 0
    """
    temp = str(cond_stmt).replace(":", "z3Vars.")
    _locals = {"z3Vars": ctx}
    exec(f"exp = {temp}", globals(), _locals)
    return _locals["exp"]


def _parse_inv_file(progfl):
    """
    Look for a sidecar <progfl>.inv file (replace .tl with .inv).
    Each non-blank, non-comment line is a Chiron expression whose value
    must be equal across both traces, e.g.:
        :out
        :__rep_counter_1
        :temp - :secret
    Returns a list of expression strings, or None if no sidecar exists.
    """
    if not progfl:
        return None
    inv_path = progfl.replace(".tl", ".inv")
    if not os.path.exists(inv_path):
        return None
    exprs = []
    with open(inv_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                exprs.append(line)
    return exprs if exprs else None


def _extract_inv_vars(inv_exprs):
    """
    Extract plain variable names (colon stripped) from a list of Chiron
    expression strings, e.g. [":out", ":temp - :secret"] -> ["out", "temp", "secret"].
    """
    vars_found = set()
    for expr in inv_exprs:
        for m in re.finditer(r':([a-zA-Z_][a-zA-Z0-9_]*)', expr):
            vars_found.add(m.group(1))
    return list(vars_found)


def build_relational_invariant(ctx1, ctx2, inv_exprs):
    """
    Build invariant from expression strings: assert expr(trace1) == expr(trace2).
    e.g. ":temp - :secret" asserts (temp_1 - secret_1) == (temp_2 - secret_2).
    """
    clauses = []
    for expr_str in inv_exprs:
        e_str = expr_str.replace(":", "z3Vars.")
        e1 = convertExp(ctx1, e_str)
        e2 = convertExp(ctx2, e_str)
        if isinstance(e1, (int, float)): e1 = IntVal(int(e1))
        if isinstance(e2, (int, float)): e2 = IntVal(int(e2))
        clauses.append(e1 == e2)
    return And(*clauses)


def _show_relational_state(model, inv_exprs, ctx1, ctx2):
    """Print expression values for both traces — relational invariant counterexample."""
    for expr_str in inv_exprs:
        e_str = expr_str.replace(":", "z3Vars.")
        e1 = _z3_wrap(convertExp(ctx1, e_str))
        e2 = _z3_wrap(convertExp(ctx2, e_str))
        v1 = model.eval(e1, model_completion=True)
        v2 = model.eval(e2, model_completion=True)
        tag = " <-- DIFFERS" if str(v1) != str(v2) else ""
        print(f"      ({expr_str}): trace1={v1}, trace2={v2}{tag}")


def build_invariant(ctx1, ctx2, inv_var_names):
    """
    Build the relational invariant as a Z3 conjunction:
      INV = /\\ { ctx1.v == ctx2.v  for v in inv_var_names }
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
      [head+tgt-1] ConditionCommand(False)           tgt < 0  <- back-edge
      [head+tgt]   ... after loop

    Returns (head_idx, body_start, body_end, exit_idx) or None.
    body_end is exclusive (does not include the back-edge instruction).
    """
    for i, (stmt, tgt) in enumerate(ir):
        if isinstance(stmt, ChironAST.ConditionCommand) and tgt > 0:
            back_idx = i + tgt - 1
            if back_idx < len(ir):
                back_stmt, back_tgt = ir[back_idx]
                if isinstance(back_stmt, ChironAST.ConditionCommand) and back_tgt < 0:
                    return (i, i + 1, back_idx, i + tgt)
    return None


# ---------------------------------------------------------------------------
# Tier 1: straight-line
# ---------------------------------------------------------------------------

def check_non_interference(irHandler, params, low_inputs, low_outputs, progfl=None):
    """
    Non-interference check for straight-line programs (no loops).

    For regular programs:  single Z3 query on final variable values.
    For turtle programs (turtle_x or turtle_y in low_outputs):
      Check A -- Final-position safety: can the turtle end at a different (x,y)?
      Check B -- Path safety: can any individual step amount differ?

    progfl: path to the .tl file (used to generate witness.sh on leak).
    """
    is_turtle = _is_turtle_check(low_outputs)

    print("\n=== Relational Verifier (Tier 1: straight-line) ===")
    print(f"  Low inputs  : {low_inputs}")
    print(f"  Low outputs : {low_outputs}")
    if is_turtle:
        print("  Turtle mode : final-position check + path-safety check")

    ctx1 = init_context(params, "_1")
    ctx2 = init_context(params, "_2")

    # For turtle programs, ensure turtle_x/y/h exist on contexts before encoding
    if is_turtle:
        _init_turtle(ctx1)
        _init_turtle(ctx2)

    print("\n  [Trace 1] Encoding...")
    encode_stmts(ctx1, irHandler.ir)
    print("  [Trace 2] Encoding...")
    encode_stmts(ctx2, irHandler.ir)

    # Build low-input equality constraints (shared by both sub-checks)
    low_input_eq = []
    for var in low_inputs:
        v = var.replace(":", "")
        low_input_eq.append(getattr(ctx1, v) == getattr(ctx2, v))
        print(f"  [Constraint] {v}_1 == {v}_2")

    # ------------------------------------------------------------------
    # Check A: Final-state / final-position safety
    # ------------------------------------------------------------------
    label_a = "Final-Position Safety" if is_turtle else "Output Safety"
    print(f"\n  --- Check A: {label_a} ---")
    s_pos = Solver()
    s_pos.add(*low_input_eq)
    diverge_clauses = [
        getattr(ctx1, var.replace(":", "")) != getattr(ctx2, var.replace(":", ""))
        for var in low_outputs
    ]
    s_pos.add(Or(*diverge_clauses))
    r_pos = s_pos.check()
    _report(r_pos, s_pos, params, low_outputs, ctx1, ctx2)

    # ------------------------------------------------------------------
    # Check B: Path safety (turtle programs only)
    # ------------------------------------------------------------------
    r_path = None
    s_path = None
    if is_turtle:
        n_steps = _count_turtle_steps(ctx1)
        print(f"\n  --- Check B: Path Safety ({n_steps} move step(s)) ---")
        if n_steps == 0:
            print("  [INFO] No move commands found — path check skipped.")
        else:
            s_path = Solver()
            s_path.add(*low_input_eq)
            step_diffs = [
                getattr(ctx1, f'turtle_step_{i}') != getattr(ctx2, f'turtle_step_{i}')
                for i in range(n_steps)
            ]
            s_path.add(Or(*step_diffs))
            r_path = s_path.check()
            _report_path(r_path, s_path, n_steps, ctx1, ctx2, step_offset=0)

    # Write witness script if any leak found (turtle programs only)
    if is_turtle and progfl:
        if r_pos == sat:
            _write_witness_script(progfl, params, s_pos.model(),
                                  suffix1="_1", suffix2="_2",
                                  low_inputs=low_inputs)
        elif r_path == sat:
            _write_witness_script(progfl, params, s_path.model(),
                                  suffix1="_1", suffix2="_2",
                                  low_inputs=low_inputs)

    print("===================================================\n")
    # Overall: safe only if both checks pass
    if is_turtle:
        all_safe = (r_pos == unsat) and (r_path is None or r_path == unsat)
        return "unsat" if all_safe else "sat"
    return str(r_pos)


# ---------------------------------------------------------------------------
# Tier 2: single loop with straight-line body
# ---------------------------------------------------------------------------

def check_loop_non_interference(irHandler, params, low_inputs, low_outputs, inv_vars=None, progfl=None):
    """
    Non-interference check for programs with a single repeat-loop.
    Uses a relational invariant and three Z3 checks:
      1.  Initialization  -- INV holds when loop is first entered
      2.  Preservation    -- body execution preserves INV (inductive step)
      2b. Path (body)     -- [turtle] body step amounts equal given INV  [turtle only]
      3.  Consequence     -- INV at exit implies low outputs agree
      3b. Path (post)     -- [turtle] post-loop step amounts equal given INV at exit  [turtle only]
    """
    is_turtle = _is_turtle_check(low_outputs)

    print("\n=== Relational Verifier (Tier 2: loop) ===")
    print(f"  Low inputs  : {low_inputs}")
    print(f"  Low outputs : {low_outputs}")
    if is_turtle:
        print("  Turtle mode : position + path checks on body and post-loop")

    loop = find_loop(irHandler.ir)
    if loop is None:
        print("  [!] No loop found — falling back to Tier 1.")
        return check_non_interference(irHandler, params, low_inputs, low_outputs)

    head_idx, body_start, body_end, exit_idx = loop
    pre_loop_ir   = irHandler.ir[:head_idx]
    body_ir       = irHandler.ir[body_start:body_end]
    post_loop_ir  = irHandler.ir[exit_idx:]
    loop_cond     = irHandler.ir[head_idx][0]

    print(f"\n  Loop head    : IR[{head_idx}]  condition: {loop_cond}")
    print(f"  Body         : IR[{body_start}:{body_end}]")
    print(f"  Loop exit    : IR[{exit_idx}]")
    print(f"  Post-loop    : IR[{exit_idx}:{len(irHandler.ir)}]  ({len(post_loop_ir)} statements)")

    # Check for a relational invariant sidecar (.inv file)
    inv_exprs = _parse_inv_file(progfl)  # list of expr strings, or None

    # Build invariant variable list (used when no sidecar, or to seed _fresh_ctx)
    if inv_vars is None:
        if inv_exprs is not None:
            # Variables to create fresh Z3 vars for = all vars mentioned in expressions
            inv_vars = _extract_inv_vars(inv_exprs)
            for v in [v.replace(":", "") for v in low_inputs]:
                if v not in inv_vars:
                    inv_vars.append(v)
        else:
            inv_vars = [v.replace(":", "") for v in low_inputs + low_outputs]
            for stmt, _ in irHandler.ir:
                if isinstance(stmt, ChironAST.AssignmentCommand):
                    v = str(stmt.lvar).replace(":", "")
                    if "__rep_counter_" in v and v not in inv_vars:
                        inv_vars.append(v)
            if is_turtle and 'turtle_h' not in inv_vars:
                inv_vars.append('turtle_h')

    if inv_exprs is not None:
        print(f"  Invariant    : relational expressions {inv_exprs}  (from .inv sidecar)")
    else:
        print(f"  Invariant    : equal across traces for {inv_vars}")

    def _build_inv(c1, c2):
        if inv_exprs is not None:
            rel = build_relational_invariant(c1, c2, inv_exprs)
            # Low inputs are always equal — include even if not in .inv file
            low_eq = [getattr(c1, v.replace(":", "")) == getattr(c2, v.replace(":", ""))
                      for v in low_inputs]
            return And(rel, *low_eq) if low_eq else rel
        return build_invariant(c1, c2, inv_vars)

    def _show_inv(m, c1, c2):
        if inv_exprs is not None:
            _show_relational_state(m, inv_exprs, c1, c2)
        else:
            _show_state(m, inv_vars, c1, c2)

    # ------------------------------------------------------------------
    # Encode pre-loop code (gives loop-entry state)
    # ------------------------------------------------------------------
    ctx1_entry = init_context(params, "_1")
    ctx2_entry = init_context(params, "_2")
    if is_turtle:
        _init_turtle(ctx1_entry)
        _init_turtle(ctx2_entry)
    encode_stmts(ctx1_entry, pre_loop_ir)
    encode_stmts(ctx2_entry, pre_loop_ir)

    low_input_eq = [
        getattr(ctx1_entry, v.replace(":", "")) == getattr(ctx2_entry, v.replace(":", ""))
        for v in low_inputs
    ]

    # ------------------------------------------------------------------
    # Check 1: Initialization
    # ------------------------------------------------------------------
    print("\n  --- Check 1: Initialization ---")
    s1 = Solver()
    s1.add(*low_input_eq)
    s1.add(Not(_build_inv(ctx1_entry, ctx2_entry)))
    r1 = s1.check()
    _print_check("Initialization", r1,
                 "INV holds at loop entry",
                 "INV does NOT hold at entry — check your invariant or pre-loop code")
    if r1 == sat:
        m = s1.model()
        print("    Counterexample — loop entry state where INV is violated:")
        _show_inv(m, ctx1_entry, ctx2_entry)
        _show_high_inputs(m, params, low_inputs, ctx1_entry, ctx2_entry)

    # ------------------------------------------------------------------
    # Check 2: Preservation (position invariant)
    # ------------------------------------------------------------------
    print("\n  --- Check 2: Preservation (Inductive Step) ---")

    ctx1_h = _fresh_ctx(inv_vars + [v.replace(":", "") for v in low_inputs], "_1h")
    ctx2_h = _fresh_ctx(inv_vars + [v.replace(":", "") for v in low_inputs], "_2h")
    _copy_missing_vars(ctx1_entry, ctx1_h, "_1h")
    _copy_missing_vars(ctx2_entry, ctx2_h, "_2h")

    ctx1_post = _copy_ctx(ctx1_h)
    ctx2_post = _copy_ctx(ctx2_h)

    # Remember how many steps existed before body encoding (pre-loop or copied)
    pre_body_steps = _count_turtle_steps(ctx1_post)

    encode_stmts(ctx1_post, body_ir)
    encode_stmts(ctx2_post, body_ir)

    n_body_steps = _count_turtle_steps(ctx1_post) - pre_body_steps

    s2 = Solver()
    s2.add(_build_inv(ctx1_h, ctx2_h))
    s2.add(encode_condition(ctx1_h, loop_cond))
    s2.add(encode_condition(ctx2_h, loop_cond))
    s2.add(Not(_build_inv(ctx1_post, ctx2_post)))
    r2 = s2.check()
    _print_check("Preservation", r2,
                 "body preserves INV",
                 "body BREAKS INV — your loop leaks or the invariant is too weak")
    if r2 == sat:
        m = s2.model()
        print("    Counterexample — one iteration that breaks INV:")
        _show_high_inputs(m, params, low_inputs, ctx1_h, ctx2_h)
        print("    Before body (loop head):")
        _show_inv(m, ctx1_h, ctx2_h)
        print("    After body:")
        _show_inv(m, ctx1_post, ctx2_post)

    # ------------------------------------------------------------------
    # Check 2b: Path safety in loop body  [turtle only]
    # ------------------------------------------------------------------
    r2_path = None
    s2_path = None
    if is_turtle and n_body_steps > 0:
        print(f"\n  --- Check 2b: Path Safety in Body ({n_body_steps} step(s) per iteration) ---")
        body_step_diffs = [
            getattr(ctx1_post, f'turtle_step_{pre_body_steps + i}') !=
            getattr(ctx2_post, f'turtle_step_{pre_body_steps + i}')
            for i in range(n_body_steps)
        ]
        s2_path = Solver()
        s2_path.add(_build_inv(ctx1_h, ctx2_h))
        s2_path.add(encode_condition(ctx1_h, loop_cond))
        s2_path.add(encode_condition(ctx2_h, loop_cond))
        s2_path.add(Or(*body_step_diffs))
        r2_path = s2_path.check()
        _report_path(r2_path, s2_path, n_body_steps, ctx1_post, ctx2_post,
                     step_offset=pre_body_steps)

    # ------------------------------------------------------------------
    # Check 3: Consequence (position)
    # ------------------------------------------------------------------
    print("\n  --- Check 3: Consequence ---")

    ctx1_e = _fresh_ctx(inv_vars + [v.replace(":", "") for v in low_inputs + low_outputs], "_1e")
    ctx2_e = _fresh_ctx(inv_vars + [v.replace(":", "") for v in low_inputs + low_outputs], "_2e")
    _copy_missing_vars(ctx1_entry, ctx1_e, "_1e")
    _copy_missing_vars(ctx2_entry, ctx2_e, "_2e")

    ctx1_final = _copy_ctx(ctx1_e)
    ctx2_final = _copy_ctx(ctx2_e)

    pre_post_steps = _count_turtle_steps(ctx1_final)

    if post_loop_ir:
        encode_stmts(ctx1_final, post_loop_ir)
        encode_stmts(ctx2_final, post_loop_ir)

    n_post_steps = _count_turtle_steps(ctx1_final) - pre_post_steps

    diverge_at_final = Or(*[
        getattr(ctx1_final, v.replace(":", "")) != getattr(ctx2_final, v.replace(":", ""))
        for v in low_outputs
    ])

    s3 = Solver()
    s3.add(_build_inv(ctx1_e, ctx2_e))
    s3.add(Not(encode_condition(ctx1_e, loop_cond)))
    s3.add(Not(encode_condition(ctx2_e, loop_cond)))
    s3.add(diverge_at_final)
    r3 = s3.check()
    _print_check("Consequence", r3,
                 "INV at exit + post-loop code implies non-interference",
                 "non-interference fails after post-loop code — invariant too weak or post-loop leaks")
    if r3 == sat:
        m = s3.model()
        print("    Counterexample — exit state where outputs diverge:")
        _show_high_inputs(m, params, low_inputs, ctx1_e, ctx2_e)
        print("    At loop exit (INV holds here):")
        _show_inv(m, ctx1_e, ctx2_e)
        if post_loop_ir:
            print("    After post-loop code:")
            _show_state(m, [v.replace(":", "") for v in low_outputs], ctx1_final, ctx2_final)

    # ------------------------------------------------------------------
    # Check 3b: Path safety in post-loop code  [turtle only]
    # ------------------------------------------------------------------
    r3_path = None
    s3_path = None
    if is_turtle and n_post_steps > 0:
        print(f"\n  --- Check 3b: Path Safety in Post-loop ({n_post_steps} step(s)) ---")
        post_step_diffs = [
            getattr(ctx1_final, f'turtle_step_{pre_post_steps + i}') !=
            getattr(ctx2_final, f'turtle_step_{pre_post_steps + i}')
            for i in range(n_post_steps)
        ]
        s3_path = Solver()
        s3_path.add(_build_inv(ctx1_e, ctx2_e))
        s3_path.add(Not(encode_condition(ctx1_e, loop_cond)))
        s3_path.add(Not(encode_condition(ctx2_e, loop_cond)))
        s3_path.add(Or(*post_step_diffs))
        r3_path = s3_path.check()
        _report_path(r3_path, s3_path, n_post_steps, ctx1_final, ctx2_final,
                     step_offset=pre_post_steps)

    # ------------------------------------------------------------------
    # Overall verdict
    # ------------------------------------------------------------------
    print("\n  --- Overall ---")
    position_checks = [r1, r2, r3]
    all_pos_pass = all(r == unsat for r in position_checks)

    if all_pos_pass:
        print("  POSITION NON-INTERFERENCE: HOLDS (all 3 checks passed)")
    else:
        failed = [n for n, r in [("Init", r1), ("Preservation", r2), ("Consequence", r3)]
                  if r != unsat]
        print(f"  POSITION NON-INTERFERENCE: FAILS — failed checks: {failed}")
        print("  Either: (a) the program leaks, or (b) the invariant is too weak.")

    if is_turtle:
        path_checks = [(n, r) for n, r in [("Body", r2_path), ("Post-loop", r3_path)]
                       if r is not None]
        if not path_checks:
            print("  PATH NON-INTERFERENCE: no turtle moves in body or post-loop")
        elif all(r == unsat for _, r in path_checks):
            print("  PATH NON-INTERFERENCE: HOLDS")
        else:
            failed_p = [n for n, r in path_checks if r != unsat]
            print(f"  PATH NON-INTERFERENCE: FAILS — {failed_p}")

    print("===========================================\n")

    path_results = [r for r in [r2_path, r3_path] if r is not None]
    all_safe = all_pos_pass and all(r == unsat for r in path_results)

    # Write witness script for the first failing check (turtle programs only)
    if is_turtle and progfl and not all_safe:
        witness_model = None
        wit_suffix1, wit_suffix2 = "_1", "_2"
        # Position checks: s1 uses _1/_2 (entry), s2 uses _1h/_2h, s3 uses _1e/_2e
        for r, s, sf1, sf2 in [
            (r1,      s1,      "_1",  "_2"),
            (r2,      s2,      "_1h", "_2h"),
            (r3,      s3,      "_1e", "_2e"),
        ]:
            if r == sat:
                witness_model = s.model()
                wit_suffix1, wit_suffix2 = sf1, sf2
                break
        # Path checks: s2_path uses _1h/_2h, s3_path uses _1e/_2e
        if witness_model is None:
            for r, s, sf1, sf2 in [
                (r2_path, s2_path, "_1h", "_2h"),
                (r3_path, s3_path, "_1e", "_2e"),
            ]:
                if r == sat and s is not None:
                    witness_model = s.model()
                    wit_suffix1, wit_suffix2 = sf1, sf2
                    break
        if witness_model:
            _write_witness_script(progfl, params, witness_model,
                                  suffix1=wit_suffix1, suffix2=wit_suffix2,
                                  low_inputs=low_inputs)

    return "unsat" if all_safe else "sat"


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
    Copy variables that exist on src_ctx but not dst_ctx as fresh Z3 Ints.
    Used so body references to non-invariant variables still resolve.
    """
    for attr, val in vars(src_ctx).items():
        if not hasattr(dst_ctx, attr):
            setAttr(dst_ctx, attr, Int(attr + suffix))


def _merge_contexts(ctx, cond_z3, ctx_then, ctx_else):
    """
    Merge two branch contexts back into ctx using Z3 If on the condition.
    For each variable: ctx.v = If(cond, ctx_then.v, ctx_else.v).
    Variables unchanged in both branches keep their original value.
    """
    all_attrs = set(vars(ctx_then).keys()) | set(vars(ctx_else).keys())
    for v in all_attrs:
        then_val = getattr(ctx_then, v, None)
        else_val = getattr(ctx_else, v, None)
        if then_val is None and else_val is None:
            continue
        if then_val is None:
            setAttr(ctx, v, else_val)
        elif else_val is None:
            setAttr(ctx, v, then_val)
        elif then_val is else_val:
            # Same object — neither branch modified it
            setAttr(ctx, v, then_val)
        else:
            setAttr(ctx, v, If(cond_z3, then_val, else_val))


def _z3_wrap(val):
    """Ensure val is a Z3 expression — wrap plain Python ints/floats in IntVal."""
    if isinstance(val, (int, float)):
        return IntVal(int(val))
    return val


def _show_high_inputs(model, params, low_inputs, ctx1, ctx2):
    """Show the secret (high) input values that Z3 chose to cause the leak."""
    low_set = {v.replace(":", "") for v in low_inputs}
    high_vars = [k.replace(":", "") for k in params if k.replace(":", "") not in low_set]
    if not high_vars:
        return
    print("    Secret inputs (high):")
    for v in high_vars:
        v1 = model.eval(_z3_wrap(getattr(ctx1, v, IntVal(0))), model_completion=True)
        v2 = model.eval(_z3_wrap(getattr(ctx2, v, IntVal(0))), model_completion=True)
        tag = " <-- DIFFERS" if str(v1) != str(v2) else ""
        print(f"      {v}: trace1={v1}, trace2={v2}{tag}")


def _show_state(model, var_names, ctx1, ctx2):
    """
    Print concrete values of var_names in both traces evaluated against model.
    """
    for v in var_names:
        val1 = model.eval(_z3_wrap(getattr(ctx1, v)), model_completion=True)
        val2 = model.eval(_z3_wrap(getattr(ctx2, v)), model_completion=True)
        tag = " <-- DIFFERS" if str(val1) != str(val2) else ""
        print(f"      {v}: trace1={val1}, trace2={val2}{tag}")


def _print_check(name, result, ok_msg, fail_msg):
    if result == unsat:
        print(f"  [PASS] {name}: {ok_msg}")
    elif result == sat:
        print(f"  [FAIL] {name}: {fail_msg}")
    else:
        print(f"  [?]    {name}: Z3 returned UNKNOWN")


def _write_witness_script(progfl, params, model, suffix1="_1", suffix2="_2",
                          low_inputs=None):
    """
    Write witness.sh — a bash script that runs two concrete executions
    side-by-side (with &) using the Z3 counterexample values, so the
    information leak is visible in the turtle window.

    suffix1/suffix2: Z3 variable suffixes used in the model (e.g. "_1h" for
                     inductive-step models in Tier 2).
    low_inputs:      Variables that must be equal — use original params value
                     for these so the script uses sensible readable inputs.
    """
    low_set = {v.replace(":", "") for v in (low_inputs or [])}

    def get_trace_params(suffix):
        d = {}
        for k in params:
            v = k.replace(":", "")
            if v in low_set:
                # Keep original value — low inputs are equal across traces
                d[k] = params[k]
            else:
                val = model.eval(Int(v + suffix), model_completion=True)
                try:
                    d[k] = int(str(val))
                except Exception:
                    d[k] = params[k]
        return d

    params1 = get_trace_params(suffix1)
    params2 = get_trace_params(suffix2)

    def fmt(d):
        parts = ", ".join(f'"{k}": {v}' for k, v in d.items())
        return "{" + parts + "}"

    diffs = [k for k in params if params1.get(k) != params2.get(k)]
    diff_comment = "differs: " + ", ".join(
        f"{k}={params1[k]} vs {params2[k]}" for k in diffs
    )

    lines = [
        "#!/bin/bash",
        "# Non-interference witness — same public inputs, different secrets.",
        f"# {diff_comment}",
        "# Run from the ChironCore/ directory.",
        "",
        f"echo 'Trace 1: {fmt(params1)}'",
        f".venv/bin/python3 chiron.py {progfl} -r -d '{fmt(params1)}' &",
        "",
        f"echo 'Trace 2: {fmt(params2)}'",
        f".venv/bin/python3 chiron.py {progfl} -r -d '{fmt(params2)}' &",
        "",
        "wait",
        "",
    ]

    script_path = "witness.sh"
    with open(script_path, "w") as f:
        f.write("\n".join(lines))
    os.chmod(script_path, 0o755)

    print(f"\n  [WITNESS] Script written: {script_path}")
    print(f"  Run:     bash witness.sh")
    print(f"  Trace 1: {fmt(params1)}")
    print(f"  Trace 2: {fmt(params2)}")


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
            val1 = m.eval(_z3_wrap(getattr(ctx1, v)), model_completion=True)
            val2 = m.eval(_z3_wrap(getattr(ctx2, v)), model_completion=True)
            tag = " <-- LEAK" if var in low_outputs and str(val1) != str(val2) else ""
            print(f"    {var}: trace1={val1}, trace2={val2}{tag}")
        print()
        print("    With same low inputs, the low outputs differ -> information leak.")
    else:
        print(f"\n  ? Z3 returned UNKNOWN: {result}")


def _report_path(result, solver, n_steps, ctx1, ctx2, step_offset=0):
    """Report path-safety check result with per-step counterexample."""
    if result == unsat:
        print(f"  [PASS] Path safety: all {n_steps} move-step amount(s) equal across traces.")
    elif result == sat:
        m = solver.model()
        print(f"  [FAIL] Path leak — move-step amounts can differ across traces:")
        for i in range(n_steps):
            attr = f'turtle_step_{step_offset + i}'
            v1 = m.eval(getattr(ctx1, attr), model_completion=True)
            v2 = m.eval(getattr(ctx2, attr), model_completion=True)
            tag = " <-- LEAK" if str(v1) != str(v2) else ""
            print(f"    step {i}: trace1={v1},  trace2={v2}{tag}")
    else:
        print("  [?] Path check returned UNKNOWN")
