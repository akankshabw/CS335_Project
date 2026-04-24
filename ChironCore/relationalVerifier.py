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


def _check_axis_aligned(ir):
    """
    Warn if any turn command uses a literal amount that is not a multiple of 90.
    Our symbolic turtle model is only sound for axis-aligned programs (headings
    restricted to {0, 90, 180, 270}).  Non-axis turns (e.g. left 72) would leave
    x/y unchanged in our encoding, silently producing wrong results.

    Returns True if safe to proceed, False if a non-axis literal turn is found.
    """
    for stmt, _ in ir:
        if isinstance(stmt, ChironAST.MoveCommand) and stmt.direction in ("left", "right"):
            expr = stmt.expr
            if isinstance(expr, ChironAST.Num):
                amt = int(expr.val)
                if amt % 90 != 0:
                    print(f"\n  [WARNING] Non-axis turn detected: {stmt.direction} {amt}")
                    print("  The turtle model is only sound for turns that are multiples of 90.")
                    print("  Turtle verification results for this program are UNSOUND.\n")
                    exit(1)
    return True


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
    """Return the number of turtle move steps already recorded on ctx."""
    n = 0
    while hasattr(ctx, f'turtle_step_{n}_dx'):
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

    # Normalised heading guaranteed in [0, 359]
    h = (ctx.turtle_h % 360 + 360) % 360
    x, y = ctx.turtle_x, ctx.turtle_y

    if stmt.direction == "forward":
        dx = If(h == 0,   amt, If(h == 180, -amt, IntVal(0)))
        dy = If(h == 90,  amt, If(h == 270, -amt, IntVal(0)))
        ctx.turtle_x = x + dx
        ctx.turtle_y = y + dy
    elif stmt.direction == "backward":
        dx = If(h == 0,  -amt, If(h == 180,  amt, IntVal(0)))
        dy = If(h == 90, -amt, If(h == 270,  amt, IntVal(0)))
        ctx.turtle_x = x + dx
        ctx.turtle_y = y + dy
    elif stmt.direction == "right":
        ctx.turtle_h = ctx.turtle_h - amt
        dx, dy = IntVal(0), IntVal(0)
    elif stmt.direction == "left":
        ctx.turtle_h = ctx.turtle_h + amt
        dx, dy = IntVal(0), IntVal(0)
    else:
        dx, dy = IntVal(0), IntVal(0)

    # Record displacement vector (dx, dy) for path-safety checks.
    # Comparing only the scalar amount would miss cases where same amount
    # but different heading produces a different drawn segment.
    idx = _count_turtle_steps(ctx)
    setattr(ctx, f'turtle_step_{idx}_dx', dx)
    setattr(ctx, f'turtle_step_{idx}_dy', dy)


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
        elif isinstance(stmt, ChironAST.InvariantAnnotation):
            i += 1  # metadata — not executable
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
      INV = /\ { ctx1.v == ctx2.v  for v in inv_var_names }
    inv_var_names: plain strings without ':', e.g. ["out", "__rep_counter_0"]
    """
    clauses = [getattr(ctx1, v) == getattr(ctx2, v) for v in inv_var_names]
    return And(*clauses)


# ---------------------------------------------------------------------------
# Find loop structure in IR
# ---------------------------------------------------------------------------

def find_loop(ir):
    """
    Scan the IR for the first repeat-loop structure.

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


def find_all_loops(ir):
    """
    Return a list of all sequential (non-nested) repeat-loop structures in ir,
    each as (head_idx, body_start, body_end, exit_idx), in program order.

    Nested loops are not supported — if a loop body itself contains a loop head
    the inner loop is skipped (the outer loop's exit_idx jumps past it).
    """
    loops = []
    i = 0
    while i < len(ir):
        stmt, tgt = ir[i]
        if isinstance(stmt, ChironAST.ConditionCommand) and tgt > 0:
            back_idx = i + tgt - 1
            if back_idx < len(ir):
                back_stmt, back_tgt = ir[back_idx]
                if isinstance(back_stmt, ChironAST.ConditionCommand) and back_tgt < 0:
                    exit_idx = i + tgt
                    loops.append((i, i + 1, back_idx, exit_idx))
                    i = exit_idx   # skip past this loop entirely
                    continue
        i += 1
    return loops


def _annotations_for_loop(ir, head_idx):
    """
    Collect @@ InvariantAnnotation nodes that belong to a specific loop.

    builder.py places annotations immediately before the loop's counter-init
    assignment (which is at head_idx - 1).  We scan backward from head_idx - 1
    collecting consecutive InvariantAnnotation nodes, stopping at the first
    non-annotation instruction or the previous loop's exit.

    Returns a list of expression strings (colon-prefixed, e.g. ':acc1'), or [].
    """
    exprs = []
    # Walk backward from the counter-init slot
    j = head_idx - 2   # head_idx-1 is the counter init; annotations sit before it
    while j >= 0:
        stmt, _ = ir[j]
        if isinstance(stmt, ChironAST.InvariantAnnotation):
            exprs.append(str(stmt.expr))
            j -= 1
        else:
            break
    exprs.reverse()   # restore program order
    return exprs


def _parse_inv_file_multi(progfl):
    """
    Parse a multi-loop .inv sidecar file.

    Convention: invariant expressions for each loop are separated by a blank line.
    Lines starting with '#' are comments and are ignored.

    Example for a 2-loop program:
        # loop 1
        :out1
        :temp - :secret

        # loop 2
        :out2

    Returns a list of groups: [ [expr, ...], [expr, ...], ... ]
    Each group corresponds to one loop (by position).  Missing groups (file has
    fewer groups than loops) will fall back to auto-generated invariants.
    Returns None if no sidecar file exists.
    """
    if not progfl:
        return None
    inv_path = progfl.replace(".tl", ".inv")
    if not os.path.exists(inv_path):
        return None

    groups = []
    current = []
    with open(inv_path) as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                if current:
                    groups.append(current)
                    current = []
            else:
                current.append(stripped)
    if current:
        groups.append(current)

    return groups if groups else None


def _vars_in_expr(expr):
    """
    Recursively collect all Var names (without ':') from a ChironAST expression.
    e.g. Sum(Var(':n'), Num(1))  ->  {'n'}
    """
    if isinstance(expr, ChironAST.Var):
        return {str(expr).replace(":", "")}
    result = set()
    for attr in vars(expr).values():
        if isinstance(attr, (ChironAST.Var,)) or hasattr(attr, '__dict__'):
            result |= _vars_in_expr(attr)
    return result


def _get_loop_bound_expr(ir, head_idx):
    """
    Return the RHS expression that sets the loop counter, i.e. the bound.

    builder.py emits:
      [head_idx-1]  :__rep_counter_N = <bound_expr>   (init)
      [head_idx]    ConditionCommand(counter > 0)      (loop head)

    Returns a ChironAST expression node, or None if not found.
    """
    if head_idx == 0:
        return None
    init_stmt, _ = ir[head_idx - 1]
    if isinstance(init_stmt, ChironAST.AssignmentCommand):
        lvar = str(init_stmt.lvar).replace(":", "")
        if "__rep_counter_" in lvar:
            return init_stmt.rexpr
    return None


def _check_secret_bound(ir, head_idx, params, low_inputs):
    """
    Detect whether the loop bound expression depends on any high (secret) variable.

    Returns (is_tainted, bound_expr_str, tainted_vars) where:
      is_tainted    -- True if bound uses at least one secret variable
      bound_expr_str -- string representation of the bound expression
      tainted_vars  -- set of secret variable names found in the bound
    """
    low_set = {v.replace(":", "") for v in low_inputs}
    high_set = {k.replace(":", "") for k in params if k.replace(":", "") not in low_set}

    bound_expr = _get_loop_bound_expr(ir, head_idx)
    if bound_expr is None:
        return False, "?", set()

    bound_vars = _vars_in_expr(bound_expr)
    tainted = bound_vars & high_set
    return bool(tainted), str(bound_expr), tainted


def _body_writes_low_output(body_ir, low_outputs):
    """
    Return True if any assignment in the loop body writes to a low output variable.
    This distinguishes a pure timing side-channel (body never touches low outputs)
    from a value leak where the secret bound also causes a direct output divergence.
    """
    low_set = {v.replace(":", "") for v in low_outputs}
    for stmt, _ in body_ir:
        if isinstance(stmt, ChironAST.AssignmentCommand):
            lvar = str(stmt.lvar).replace(":", "")
            if lvar in low_set:
                return True
    return False


# ---------------------------------------------------------------------------
# Tier 2b: multiple sequential loops
# ---------------------------------------------------------------------------

def _verify_one_loop(loop_idx, loop, full_ir, ctx1_entry, ctx2_entry,
                     params, low_inputs, low_outputs,
                     inv_exprs, inv_source, is_turtle,
                     entry_assumptions=None):
    """
    Run the three-check inductive proof for one loop.

    ctx1_entry / ctx2_entry  -- the REAL concrete symbolic state at loop entry,
                                 built by encoding all preceding code linearly.
                                 Used directly for Check 1 (no fresh vars needed).
    inv_exprs                -- list of relational expression strings, or None
                                 for auto-generated equality invariants.

    Returns (r1, r2, r3, all_pass).
    The caller is responsible for maintaining ctx1/ctx2 across loops.
    """
    head_idx, body_start, body_end, exit_idx = loop
    body_ir   = full_ir[body_start:body_end]
    loop_cond = full_ir[head_idx][0]

    label = f"Loop {loop_idx + 1}"
    print(f"\n  {'='*10} {label} {'='*10}")
    print(f"  Loop head : IR[{head_idx}]  condition: {loop_cond}")
    print(f"  Body      : IR[{body_start}:{body_end}]")
    print(f"  Exit      : IR[{exit_idx}]")

    # Collect counter var for this loop only
    auto_counters = []
    for stmt, _ in full_ir[head_idx - 1:exit_idx]:
        if isinstance(stmt, ChironAST.AssignmentCommand):
            v = str(stmt.lvar).replace(":", "")
            if "__rep_counter_" in v and v not in auto_counters:
                auto_counters.append(v)

    # Build inv_vars list (for fresh ctx in Check 2 / Check 3)
    if inv_exprs is not None:
        inv_vars = _extract_inv_vars(inv_exprs)
        for v in auto_counters:
            if v not in inv_vars: inv_vars.append(v)
        for v in [x.replace(":", "") for x in low_inputs]:
            if v not in inv_vars: inv_vars.append(v)
        for v in [x.replace(":", "") for x in low_outputs]:
            if v not in inv_vars: inv_vars.append(v)
        print(f"  Invariant : relational expressions {inv_exprs}  ({inv_source})")
    else:
        inv_vars = [v.replace(":", "") for v in low_inputs + low_outputs]
        for v in auto_counters:
            if v not in inv_vars: inv_vars.append(v)
        if is_turtle and 'turtle_h' not in inv_vars:
            inv_vars.append('turtle_h')
        print(f"  Invariant : equal across traces for {inv_vars}  (auto-generated)")

    def _build_inv(c1, c2):
        if inv_exprs is not None:
            rel = build_relational_invariant(c1, c2, inv_exprs)
            auto_eq = [getattr(c1, v.replace(":", "")) == getattr(c2, v.replace(":", ""))
                       for v in low_inputs]
            auto_eq += [getattr(c1, v) == getattr(c2, v) for v in auto_counters]
            inv_expr_vars = set(_extract_inv_vars(inv_exprs))
            for v in [x.replace(":", "") for x in low_outputs]:
                if v not in inv_expr_vars:
                    auto_eq.append(getattr(c1, v) == getattr(c2, v))
            return And(rel, *auto_eq) if auto_eq else rel
        return build_invariant(c1, c2, inv_vars)

    def _show_inv(m, c1, c2):
        if inv_exprs is not None:
            _show_relational_state(m, inv_exprs, c1, c2)
        else:
            _show_state(m, inv_vars, c1, c2)

    # Low-input equality on the real entry context
    low_input_eq = [
        getattr(ctx1_entry, v.replace(":", "")) == getattr(ctx2_entry, v.replace(":", ""))
        for v in low_inputs
    ]

    # ------------------------------------------------------------------
    # Check 1: Initialization — use the REAL symbolic entry state directly.
    # ctx1_entry / ctx2_entry are concrete Z3 expressions, not fresh vars,
    # so this faithfully reflects what the program state actually is.
    # For loop k>1 we also add the previous loop's exit invariant (applied
    # to the same ctx, which has been updated with between-loop code) so
    # that Z3 knows what was proven true at the end of the previous loop.
    # ------------------------------------------------------------------
    print(f"\n  --- {label} Check 1: Initialization ---")
    s1 = Solver()
    s1.add(*low_input_eq)
    if entry_assumptions:
        s1.add(*entry_assumptions)
    s1.add(Not(_build_inv(ctx1_entry, ctx2_entry)))
    r1 = s1.check()
    _print_check("Initialization", r1,
                 "INV holds at loop entry",
                 "INV does NOT hold at entry — check your invariant or pre-loop / between-loop code")
    if r1 == sat:
        m = s1.model()
        print("    Counterexample — loop entry state where INV is violated:")
        _show_inv(m, ctx1_entry, ctx2_entry)
        _show_high_inputs(m, params, low_inputs, ctx1_entry, ctx2_entry)

    # ------------------------------------------------------------------
    # Check 2: Preservation (inductive step) — fresh symbolic vars
    # ------------------------------------------------------------------
    print(f"\n  --- {label} Check 2: Preservation ---")
    ctx1_h = _fresh_ctx(inv_vars + [v.replace(":", "") for v in low_inputs], "_1h")
    ctx2_h = _fresh_ctx(inv_vars + [v.replace(":", "") for v in low_inputs], "_2h")
    _copy_missing_vars(ctx1_entry, ctx1_h, "_1h")
    _copy_missing_vars(ctx2_entry, ctx2_h, "_2h")

    ctx1_post = _copy_ctx(ctx1_h)
    ctx2_post = _copy_ctx(ctx2_h)
    encode_stmts(ctx1_post, body_ir)
    encode_stmts(ctx2_post, body_ir)

    s2 = Solver()
    s2.add(_build_inv(ctx1_h, ctx2_h))
    s2.add(encode_condition(ctx1_h, loop_cond))
    s2.add(encode_condition(ctx2_h, loop_cond))
    s2.add(Not(_build_inv(ctx1_post, ctx2_post)))
    r2 = s2.check()
    _print_check("Preservation", r2,
                 "body preserves INV",
                 "body BREAKS INV — loop leaks or invariant too weak")
    if r2 == sat:
        m = s2.model()
        print("    Counterexample — one iteration that breaks INV:")
        _show_high_inputs(m, params, low_inputs, ctx1_h, ctx2_h)
        print("    Before body:")
        _show_inv(m, ctx1_h, ctx2_h)
        print("    After body:")
        _show_inv(m, ctx1_post, ctx2_post)

    # ------------------------------------------------------------------
    # Check 3: Consequence — fresh symbolic exit vars
    # ------------------------------------------------------------------
    print(f"\n  --- {label} Check 3: Consequence ---")
    ctx1_e = _fresh_ctx(inv_vars + [v.replace(":", "") for v in low_inputs + low_outputs], "_1e")
    ctx2_e = _fresh_ctx(inv_vars + [v.replace(":", "") for v in low_inputs + low_outputs], "_2e")
    _copy_missing_vars(ctx1_entry, ctx1_e, "_1e")
    _copy_missing_vars(ctx2_entry, ctx2_e, "_2e")

    diverge_at_exit = Or(*[
        getattr(ctx1_e, v.replace(":", "")) != getattr(ctx2_e, v.replace(":", ""))
        for v in low_outputs
    ])
    s3 = Solver()
    s3.add(_build_inv(ctx1_e, ctx2_e))
    s3.add(Not(encode_condition(ctx1_e, loop_cond)))
    s3.add(Not(encode_condition(ctx2_e, loop_cond)))
    s3.add(diverge_at_exit)
    r3 = s3.check()
    _print_check("Consequence", r3,
                 "INV at exit implies non-interference on low outputs",
                 "non-interference fails at exit — invariant too weak or loop leaks")
    if r3 == sat:
        m = s3.model()
        print("    Counterexample — exit state where low outputs diverge:")
        _show_high_inputs(m, params, low_inputs, ctx1_e, ctx2_e)
        print("    At loop exit (INV holds here):")
        _show_inv(m, ctx1_e, ctx2_e)

    all_pass = (r1 == unsat) and (r2 == unsat) and (r3 == unsat)
    return r1, r2, r3, _build_inv, loop_cond, all_pass


def check_multi_loop_non_interference(irHandler, loops, params, low_inputs, low_outputs,
                                      inv_groups, progfl=None):
    """
    Non-interference check for programs with multiple sequential (non-nested) loops.

    Design: one real symbolic context (ctx1, ctx2) is encoded linearly through
    the entire program — pre-loop code, between-loop code, counter inits, etc.
    This means Check 1 for each loop sees the ACTUAL symbolic state, so any
    secret-dependent computation in between-loop code is correctly reflected.

    Check 2 (preservation) and Check 3 (consequence) use fresh symbolic vars
    as in the single-loop case.

    inv_groups: list of (inv_exprs, inv_source) per loop.
    """
    is_turtle = _is_turtle_check(low_outputs)

    print("\n=== Relational Verifier (Tier 2b: multiple sequential loops) ===")
    print(f"  Low inputs  : {low_inputs}")
    print(f"  Low outputs : {low_outputs}")
    print(f"  Loops found : {len(loops)}")

    full_ir = irHandler.ir

    # -- Start with a real symbolic context and encode everything before loop 1 --
    ctx1 = init_context(params, "_1")
    ctx2 = init_context(params, "_2")
    if is_turtle:
        _init_turtle(ctx1)
        _init_turtle(ctx2)

    first_head = loops[0][0]
    pre_ir = full_ir[:first_head]
    if pre_ir:
        print(f"\n  [Pre-loop code] IR[0:{first_head}]")
        encode_stmts(ctx1, pre_ir)
        encode_stmts(ctx2, pre_ir)

    all_safe = True
    # Accumulated exit-invariant constraints from previous loops.
    # These are added to Check 1 of the next loop so Z3 knows what was proven.
    prev_exit_constraints = []
    prev_loop_cond = None

    for k, loop in enumerate(loops):
        head_idx, body_start, body_end, exit_idx = loop

        # -- Encode between-loop code on the real ctx --
        if k > 0:
            prev_exit = loops[k - 1][3]
            between_ir = full_ir[prev_exit : head_idx - 1]  # up to but not incl. counter-init
            if between_ir:
                print(f"\n  [Between-loop code] IR[{prev_exit}:{head_idx - 1}]")
                encode_stmts(ctx1, between_ir)
                encode_stmts(ctx2, between_ir)

        # -- Encode the counter-init on the real ctx --
        encode_stmts(ctx1, full_ir[head_idx - 1 : head_idx])
        encode_stmts(ctx2, full_ir[head_idx - 1 : head_idx])

        inv_exprs, inv_source = inv_groups[k]

        # Timing side-channel check
        is_tainted, bound_str, tainted_vars = _check_secret_bound(
            full_ir, head_idx, params, low_inputs
        )
        if is_tainted:
            body_ir_k = full_ir[body_start:body_end]
            if _body_writes_low_output(body_ir_k, low_outputs):
                print(f"\n  [!] WARNING (Loop {k+1}): bound '{bound_str}' is non low")
                print(f"  Body writes a low output — VALUE LEAK. Continuing with invariant checks...\n")
            else:
                print(f"\n  [!] TIMING SIDE-CHANNEL (Loop {k+1}): bound '{bound_str}' is non low")
                print(f"  Body does not write any low output — pure timing/termination leak.")
                print(f"\n  NON-INTERFERENCE: FAILS (timing side-channel in loop {k+1})")
                print("=================================================================\n")
                return "sat"

        # -- Run the 3-check proof for this loop --
        # ctx1/ctx2 are the real symbolic entry state — Check 1 uses them directly.
        # prev_exit_constraints carries what was proven at the end of the previous loop.
        r1, r2, r3, loop_build_inv, loop_cond, loop_safe = _verify_one_loop(
            k, loop, full_ir, ctx1, ctx2,
            params, low_inputs, low_outputs,
            inv_exprs, inv_source, is_turtle,
            entry_assumptions=prev_exit_constraints
        )
        if not loop_safe:
            all_safe = False

        # -- Build constraints for the next loop's Check 1 --
        # We know: loop's INV holds at exit AND loop condition is false.
        # These are expressed on the CURRENT ctx1/ctx2 (which will be updated
        # with between-loop code before the next loop's Check 1 runs).
        prev_exit_constraints = [
            loop_build_inv(ctx1, ctx2),
            Not(encode_condition(ctx1, loop_cond)),
            Not(encode_condition(ctx2, loop_cond)),
        ]

    # -- Encode any post-last-loop straight-line code and do a final check --
    last_exit = loops[-1][3]
    post_ir = full_ir[last_exit:]
    if post_ir:
        print(f"\n  [Post-loop code] IR[{last_exit}:{len(full_ir)}]")
        encode_stmts(ctx1, post_ir)
        encode_stmts(ctx2, post_ir)

    print(f"\n  --- Final output check (after all loops) ---")
    low_input_eq = [
        getattr(ctx1, v.replace(":", "")) == getattr(ctx2, v.replace(":", ""))
        for v in low_inputs
    ]
    diverge_final = Or(*[
        getattr(ctx1, v.replace(":", "")) != getattr(ctx2, v.replace(":", ""))
        for v in low_outputs
    ])
    sf = Solver()
    sf.add(*low_input_eq)
    # Also assume the last loop's exit invariant holds
    if prev_exit_constraints:
        sf.add(*prev_exit_constraints)
    sf.add(diverge_final)
    rf = sf.check()
    _print_check("Final outputs", rf,
                 "low outputs agree after all loops and post-loop code",
                 "low outputs can diverge — leak in post-loop code or invariants too weak")
    if rf == sat:
        m = sf.model()
        _show_state(m, [v.replace(":", "") for v in low_outputs], ctx1, ctx2)
        all_safe = False

    print(f"\n  --- Overall ---")
    if all_safe:
        print("  NON-INTERFERENCE: HOLDS (all loops verified)")
    else:
        print("  NON-INTERFERENCE: FAILS (see failed checks above)")
    print("=================================================================\n")
    return "unsat" if all_safe else "sat"


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
    if is_turtle:
        _check_axis_aligned(irHandler.ir)

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
                clause
                for i in range(n_steps)
                for clause in [
                    getattr(ctx1, f'turtle_step_{i}_dx') != getattr(ctx2, f'turtle_step_{i}_dx'),
                    getattr(ctx1, f'turtle_step_{i}_dy') != getattr(ctx2, f'turtle_step_{i}_dy'),
                ]
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
# Symmetry checking
# ---------------------------------------------------------------------------

def check_symmetry(irHandler, params, swap, low_outputs):
    """
    Symmetry check: run the program twice with two inputs swapped between traces.

    Trace 1: normal inputs.
    Trace 2: same inputs, but swap[0] and swap[1] are exchanged.

    Assert that the low outputs are the same in both traces.
    If UNSAT  -> program is symmetric w.r.t. this swap.
    If SAT    -> program treats the two inputs asymmetrically; counterexample shown.

    swap: list of two variable name strings, e.g. [':a', ':b']
    """
    v0 = swap[0].replace(":", "")
    v1 = swap[1].replace(":", "")

    print("\n=== Symmetry Check ===")
    print(f"  Swapped inputs : {swap[0]} <-> {swap[1]}")
    print(f"  Low outputs    : {low_outputs}")

    # Both traces use independent symbolic vars (a_1, b_1) and (a_2, b_2).
    # We encode the program identically in both, then constrain the *inputs*:
    #   Trace 1: a_1 = A,  b_1 = B   (some values A, B)
    #   Trace 2: a_2 = B,  b_2 = A   (swapped)
    # This is expressed as: a_1 == b_2  AND  b_1 == a_2
    # All other inputs are equal: c_1 == c_2 for c not in {v0, v1}
    ctx1 = init_context(params, "_1")
    ctx2 = init_context(params, "_2")

    print("\n  [Trace 1] Encoding (normal inputs)...")
    encode_stmts(ctx1, irHandler.ir)
    print("  [Trace 2] Encoding (swapped inputs)...")
    encode_stmts(ctx2, irHandler.ir)

    # All non-swapped, non-output inputs are equal across traces
    out_set = {v.replace(":", "") for v in low_outputs}
    non_swap = [k for k in params
                if k.replace(":", "") not in (v0, v1)
                and k.replace(":", "") not in out_set]
    other_eq = [
        getattr(ctx1, k.replace(":", "")) == getattr(ctx2, k.replace(":", ""))
        for k in non_swap
    ]

    # The swap: trace1 sees (A, B), trace2 sees (B, A)
    # Expressed as cross-equalities on the initial Z3 vars
    swap_eq = [
        Int(v0 + "_1") == Int(v1 + "_2"),
        Int(v1 + "_1") == Int(v0 + "_2"),
    ]

    diverge = Or(*[
        getattr(ctx1, v.replace(":", "")) != getattr(ctx2, v.replace(":", ""))
        for v in low_outputs
    ])

    s = Solver()
    s.add(*other_eq)
    s.add(*swap_eq)
    s.add(diverge)
    result = s.check()

    if result == unsat:
        print("\n  SYMMETRIC: outputs are identical when inputs are swapped.")
        print(f"  f(..., {swap[0]}={swap[0]}, {swap[1]}={swap[1]}, ...) == "
              f"f(..., {swap[0]}={swap[1]}, {swap[1]}={swap[0]}, ...)")
    elif result == sat:
        m = s.model()
        print("\n  ASYMMETRIC: outputs differ when inputs are swapped. Counterexample:")
        for k in params:
            v = k.replace(":", "")
            v1_val = m.eval(_z3_wrap(getattr(ctx1, v)), model_completion=True)
            v2_val = m.eval(_z3_wrap(getattr(ctx2, v)), model_completion=True)
            tag = " <-- swapped" if v in (v0, v1) else ""
            print(f"    {k}: trace1={v1_val}, trace2={v2_val}{tag}")
        shown = {k.replace(":", "") for k in params}
        extra_outs = [var for var in low_outputs if var.replace(":", "") not in shown]
        if extra_outs:
            print("  Outputs (not listed above):")
            for var in extra_outs:
                v = var.replace(":", "")
                o1 = m.eval(_z3_wrap(getattr(ctx1, v)), model_completion=True)
                o2 = m.eval(_z3_wrap(getattr(ctx2, v)), model_completion=True)
                tag = " <-- DIFFERS" if str(o1) != str(o2) else ""
                print(f"    {var}: trace1={o1}, trace2={o2}{tag}")
    else:
        print(f"  Z3 returned UNKNOWN")

    print("======================\n")
    return str(result)


# ---------------------------------------------------------------------------
# Generic relational 2-safety engine (shared by symmetry-2 and monotonicity)
# ---------------------------------------------------------------------------
#
# A "property" is described by a PropSpec namedtuple:
#
#   input_constraints(ctx1, ctx2, params) -> [z3 expr]
#       Constraints that relate the two traces' INPUTS.
#       e.g. symmetry: a_1==b_2, b_1==a_2, others equal
#            monotonicity: x_1 <= x_2, others equal
#
#   build_inv(c1, c2, inv_vars, inv_exprs, auto_counters, low_outputs) -> z3 expr
#       Loop invariant.  Must be consistent with input_constraints so that
#       Check 1 (Init) is satisfiable for correct programs.
#
#   divergence(ctx1, ctx2, low_outputs) -> z3 expr
#       The "bad" post-condition whose absence we prove.
#       e.g. symmetry: any output differs
#            monotonicity: any output decreases (out_1 > out_2)
#
#   name        : short display name, e.g. "SYMMETRY-2"
#   init_label  : Check-1 pass/fail messages
#   cons_label  : Check-3 pass/fail messages
#   final_label : overall pass/fail messages

from collections import namedtuple

PropSpec = namedtuple("PropSpec", [
    "name",
    "input_constraints",
    "build_inv",
    "divergence",
    "init_pass_msg",
    "init_fail_msg",
    "cons_pass_msg",
    "cons_fail_msg",
    "overall_pass_msg",
    "overall_fail_msg",
    "inv_label",
])


def _collect_inv_groups(ir, all_loops, progfl):
    """Return a list of (inv_exprs, inv_source) per loop — shared by all properties."""
    sidecar_groups = _parse_inv_file_multi(progfl)
    groups = []
    for k, lp in enumerate(all_loops):
        ann = _annotations_for_loop(ir, lp[0])
        if ann:
            groups.append((ann, f"from @@ annotations (loop {k+1})"))
        elif sidecar_groups and k < len(sidecar_groups):
            groups.append((sidecar_groups[k], f"from .inv sidecar (group {k+1})"))
        else:
            groups.append((None, "auto-generated"))
    return groups


def _resolve_inv_for_loop(ir, head_idx, exit_idx, progfl):
    """Return (inv_exprs, inv_source, auto_counters) for a single loop."""
    auto_counters = []
    for stmt, _ in ir[head_idx - 1:exit_idx]:
        if isinstance(stmt, ChironAST.AssignmentCommand):
            v = str(stmt.lvar).replace(":", "")
            if "__rep_counter_" in v and v not in auto_counters:
                auto_counters.append(v)

    annotated = [str(stmt.expr) for stmt, _ in ir
                 if isinstance(stmt, ChironAST.InvariantAnnotation)]
    if annotated:
        return annotated, "from @@ annotations", auto_counters

    inv_exprs = _parse_inv_file(progfl)
    inv_source = "from .inv sidecar" if inv_exprs else None
    return inv_exprs, inv_source, auto_counters


def _build_inv_vars(inv_exprs, auto_counters, low_outputs, extra_vars=()):
    """Build the inv_vars list given an invariant specification."""
    lo_stripped = [v.replace(":", "") for v in low_outputs]
    if inv_exprs is not None:
        iv = _extract_inv_vars(inv_exprs)
        for v in auto_counters + lo_stripped + list(extra_vars):
            if v not in iv:
                iv.append(v)
    else:
        seen = set()
        iv = []
        for v in list(extra_vars) + lo_stripped + auto_counters:
            if v not in seen:
                seen.add(v)
                iv.append(v)
    return iv


def _show_inv_generic(m, inv_exprs, inv_vars, c1, c2):
    if inv_exprs is not None:
        _show_relational_state(m, inv_exprs, c1, c2)
    else:
        _show_state(m, inv_vars, c1, c2)


def _check_relational_loop(prop, irHandler, params, low_outputs,
                            inv_exprs, inv_source, auto_counters,
                            pre_loop_ir, body_ir, post_loop_ir,
                            loop_cond, head_idx, exit_idx,
                            entry_assumptions=None, label=""):
    """
    Run the 3-check inductive proof for ONE loop under a given PropSpec.

    Returns (r1, r2, r3, build_inv_fn, loop_cond, all_pass).
    `entry_assumptions` is a list of extra Z3 constraints for Check 1
    (used when chaining multiple loops).
    """
    # Determine inv_vars for fresh contexts
    # We pass extra_vars = all vars mentioned in input_constraints that aren't outputs
    out_set = {v.replace(":", "") for v in low_outputs}
    all_param_vars = [k.replace(":", "") for k in params if k.replace(":", "") not in out_set]
    iv = _build_inv_vars(inv_exprs, auto_counters, low_outputs, extra_vars=all_param_vars)

    if inv_exprs is not None:
        inv_label = f"relational expressions {inv_exprs}  ({inv_source})"
    else:
        inv_label = prop.inv_label if hasattr(prop, 'inv_label') else f"equal across traces for {iv}"
    if label:
        print(f"  Invariant : {inv_label}")

    def build_inv(c1, c2):
        return prop.build_inv(c1, c2, iv, inv_exprs, auto_counters, low_outputs)

    def show_inv(m, c1, c2):
        _show_inv_generic(m, inv_exprs, iv, c1, c2)

    # Encode entry state
    ctx1_entry = init_context(params, "_1")
    ctx2_entry = init_context(params, "_2")
    encode_stmts(ctx1_entry, pre_loop_ir)
    encode_stmts(ctx2_entry, pre_loop_ir)

    input_cs = prop.input_constraints(ctx1_entry, ctx2_entry, params)

    all_pass = True

    # Check 1: Initialization
    pfx = f"  --- {label} " if label else "  --- "
    print(f"\n{pfx}Check 1: Initialization ---")
    s1 = Solver()
    s1.add(*input_cs)
    if entry_assumptions:
        s1.add(*entry_assumptions)
    s1.add(Not(build_inv(ctx1_entry, ctx2_entry)))
    r1 = s1.check()
    _print_check("Initialization", r1, prop.init_pass_msg, prop.init_fail_msg)
    if r1 == sat:
        show_inv(s1.model(), ctx1_entry, ctx2_entry)
        all_pass = False

    # Check 2: Preservation
    print(f"\n{pfx}Check 2: Preservation ---")
    ctx1_h = _fresh_ctx(iv, "_1h")
    ctx2_h = _fresh_ctx(iv, "_2h")
    _copy_missing_vars(ctx1_entry, ctx1_h, "_1h")
    _copy_missing_vars(ctx2_entry, ctx2_h, "_2h")
    ctx1_post = _copy_ctx(ctx1_h)
    ctx2_post = _copy_ctx(ctx2_h)
    encode_stmts(ctx1_post, body_ir)
    encode_stmts(ctx2_post, body_ir)

    s2 = Solver()
    s2.add(build_inv(ctx1_h, ctx2_h))
    s2.add(encode_condition(ctx1_h, loop_cond))
    s2.add(encode_condition(ctx2_h, loop_cond))
    s2.add(Not(build_inv(ctx1_post, ctx2_post)))
    r2 = s2.check()
    _print_check("Preservation", r2, "body preserves INV", "body BREAKS INV — invariant too weak or loop violates property")
    if r2 == sat:
        m = s2.model()
        print("    Counterexample — one iteration that breaks INV:")
        print("    Before body:"); show_inv(m, ctx1_h, ctx2_h)
        print("    After body:");  show_inv(m, ctx1_post, ctx2_post)
        all_pass = False

    # Check 3: Consequence
    print(f"\n{pfx}Check 3: Consequence ---")
    ctx1_e = _fresh_ctx(iv, "_1e")
    ctx2_e = _fresh_ctx(iv, "_2e")
    _copy_missing_vars(ctx1_entry, ctx1_e, "_1e")
    _copy_missing_vars(ctx2_entry, ctx2_e, "_2e")
    ctx1_final = _copy_ctx(ctx1_e)
    ctx2_final = _copy_ctx(ctx2_e)
    encode_stmts(ctx1_final, post_loop_ir)
    encode_stmts(ctx2_final, post_loop_ir)

    s3 = Solver()
    s3.add(build_inv(ctx1_e, ctx2_e))
    s3.add(Not(encode_condition(ctx1_e, loop_cond)))
    s3.add(Not(encode_condition(ctx2_e, loop_cond)))
    s3.add(prop.divergence(ctx1_final, ctx2_final, low_outputs))
    r3 = s3.check()
    _print_check("Consequence", r3, prop.cons_pass_msg, prop.cons_fail_msg)
    if r3 == sat:
        show_inv(s3.model(), ctx1_e, ctx2_e)
        all_pass = False

    return r1, r2, r3, build_inv, loop_cond, all_pass


def _check_relational_multi_loop(prop, irHandler, loops, params, low_outputs,
                                  inv_groups, prop_header):
    """
    Generic multi-loop 3-check engine for any PropSpec.
    Encodes inter-loop code on a real symbolic ctx pair and runs
    _check_relational_loop per loop, chaining exit invariants.
    """
    full_ir = irHandler.ir
    out_set = {v.replace(":", "") for v in low_outputs}

    ctx1 = init_context(params, "_1")
    ctx2 = init_context(params, "_2")

    first_head = loops[0][0]
    pre_ir = full_ir[:first_head]
    if pre_ir:
        print(f"\n  [Pre-loop code] IR[0:{first_head}]")
        encode_stmts(ctx1, pre_ir)
        encode_stmts(ctx2, pre_ir)

    input_cs = prop.input_constraints(ctx1, ctx2, params)

    all_safe = True
    prev_exit_constraints = []

    for k, loop in enumerate(loops):
        head_idx, body_start, body_end, exit_idx = loop
        body_ir   = full_ir[body_start:body_end]
        loop_cond = full_ir[head_idx][0]
        label     = f"Loop {k + 1}"

        if k > 0:
            prev_exit = loops[k - 1][3]
            between_ir = full_ir[prev_exit : head_idx - 1]
            if between_ir:
                print(f"\n  [Between-loop code] IR[{prev_exit}:{head_idx - 1}]")
                encode_stmts(ctx1, between_ir)
                encode_stmts(ctx2, between_ir)

        encode_stmts(ctx1, full_ir[head_idx - 1 : head_idx])
        encode_stmts(ctx2, full_ir[head_idx - 1 : head_idx])

        inv_exprs, inv_source = inv_groups[k]

        auto_counters = []
        for stmt, _ in full_ir[head_idx - 1:exit_idx]:
            if isinstance(stmt, ChironAST.AssignmentCommand):
                v = str(stmt.lvar).replace(":", "")
                if "__rep_counter_" in v and v not in auto_counters:
                    auto_counters.append(v)

        all_param_vars = [k2.replace(":", "") for k2 in params if k2.replace(":", "") not in out_set]
        iv = _build_inv_vars(inv_exprs, auto_counters, low_outputs, extra_vars=all_param_vars)

        if inv_exprs is not None:
            inv_label = f"relational expressions {inv_exprs}  ({inv_source})"
        else:
            inv_label = prop.inv_label if hasattr(prop, 'inv_label') else f"equal across traces for {iv}"

        print(f"\n  {'='*10} {label} {'='*10}")
        print(f"  Invariant : {inv_label}")
        print(f"  Loop head : IR[{head_idx}]  condition: {loop_cond}")
        print(f"  Body      : IR[{body_start}:{body_end}]")

        def build_inv(c1, c2, _iv=iv, _ie=inv_exprs, _ac=auto_counters):
            return prop.build_inv(c1, c2, _iv, _ie, _ac, low_outputs)

        def show_inv(m, c1, c2, _ie=inv_exprs, _iv=iv):
            _show_inv_generic(m, _ie, _iv, c1, c2)

        # Check 1: Initialization
        print(f"\n  --- {label} Check 1: Initialization ---")
        s1 = Solver()
        s1.add(*input_cs)
        if prev_exit_constraints:
            s1.add(*prev_exit_constraints)
        s1.add(Not(build_inv(ctx1, ctx2)))
        r1 = s1.check()
        _print_check("Initialization", r1, prop.init_pass_msg, prop.init_fail_msg)
        if r1 == sat:
            show_inv(s1.model(), ctx1, ctx2)
            all_safe = False

        # Check 2: Preservation
        print(f"\n  --- {label} Check 2: Preservation ---")
        ctx1_h = _fresh_ctx(iv, "_1h")
        ctx2_h = _fresh_ctx(iv, "_2h")
        _copy_missing_vars(ctx1, ctx1_h, "_1h")
        _copy_missing_vars(ctx2, ctx2_h, "_2h")
        ctx1_post = _copy_ctx(ctx1_h)
        ctx2_post = _copy_ctx(ctx2_h)
        encode_stmts(ctx1_post, body_ir)
        encode_stmts(ctx2_post, body_ir)

        s2 = Solver()
        s2.add(build_inv(ctx1_h, ctx2_h))
        s2.add(encode_condition(ctx1_h, loop_cond))
        s2.add(encode_condition(ctx2_h, loop_cond))
        s2.add(Not(build_inv(ctx1_post, ctx2_post)))
        r2 = s2.check()
        _print_check("Preservation", r2, "body preserves INV", "body BREAKS INV")
        if r2 == sat:
            m = s2.model()
            print("    Before body:"); show_inv(m, ctx1_h, ctx2_h)
            print("    After body:");  show_inv(m, ctx1_post, ctx2_post)
            all_safe = False

        # Check 3: Consequence
        print(f"\n  --- {label} Check 3: Consequence ---")
        ctx1_e = _fresh_ctx(iv, "_1e")
        ctx2_e = _fresh_ctx(iv, "_2e")
        _copy_missing_vars(ctx1, ctx1_e, "_1e")
        _copy_missing_vars(ctx2, ctx2_e, "_2e")

        s3 = Solver()
        s3.add(build_inv(ctx1_e, ctx2_e))
        s3.add(Not(encode_condition(ctx1_e, loop_cond)))
        s3.add(Not(encode_condition(ctx2_e, loop_cond)))
        s3.add(prop.divergence(ctx1_e, ctx2_e, low_outputs))
        r3 = s3.check()
        _print_check("Consequence", r3, prop.cons_pass_msg, prop.cons_fail_msg)
        if r3 == sat:
            show_inv(s3.model(), ctx1_e, ctx2_e)
            all_safe = False

        if not ((r1 == unsat) and (r2 == unsat) and (r3 == unsat)):
            all_safe = False

        prev_exit_constraints = [
            build_inv(ctx1, ctx2),
            Not(encode_condition(ctx1, loop_cond)),
            Not(encode_condition(ctx2, loop_cond)),
        ]

    # Final output check after all loops
    last_exit = loops[-1][3]
    post_ir = full_ir[last_exit:]
    if post_ir:
        print(f"\n  [Post-loop code] IR[{last_exit}:{len(full_ir)}]")
        encode_stmts(ctx1, post_ir)
        encode_stmts(ctx2, post_ir)

    print(f"\n  --- Final output check (after all loops) ---")
    s_fin = Solver()
    s_fin.add(*input_cs)
    if prev_exit_constraints:
        s_fin.add(*prev_exit_constraints)
    s_fin.add(prop.divergence(ctx1, ctx2, low_outputs))
    r_fin = s_fin.check()
    _print_check("Final outputs", r_fin, prop.cons_pass_msg, prop.cons_fail_msg)
    if r_fin == sat:
        m = s_fin.model()
        for v in low_outputs:
            vn = v.replace(":", "")
            o1 = m.eval(_z3_wrap(getattr(ctx1, vn)), model_completion=True)
            o2 = m.eval(_z3_wrap(getattr(ctx2, vn)), model_completion=True)
            tag = " <-- DIFFERS" if str(o1) != str(o2) else ""
            print(f"    {v}: trace1={o1}, trace2={o2}{tag}")
        all_safe = False

    print(f"\n  --- Overall ---")
    print(f"  {prop.name}: {'HOLDS (all loops verified)' if all_safe else 'FAILS (see failed checks above)'}")
    print("=================================================================\n")
    return "unsat" if all_safe else "sat"


# ---------------------------------------------------------------------------
# Symmetry-2: thin wrapper over the generic engine
# ---------------------------------------------------------------------------

def _sym_build_inv(c1, c2, inv_vars, inv_exprs, auto_counters, low_outputs, v0, v1):
    """Relational invariant for symmetry: cross-equalities for (v0,v1), simple eq for rest."""
    if inv_exprs is not None:
        rel = build_relational_invariant(c1, c2, inv_exprs)
        auto_eq = [getattr(c1, v) == getattr(c2, v) for v in auto_counters]
        inv_expr_vars = set(_extract_inv_vars(inv_exprs))
        for v in [x.replace(":", "") for x in low_outputs]:
            if v not in inv_expr_vars:
                auto_eq.append(getattr(c1, v) == getattr(c2, v))
        return And(rel, *auto_eq) if auto_eq else rel
    clauses = [getattr(c1, v0) == getattr(c2, v1), getattr(c1, v1) == getattr(c2, v0)]
    for v in inv_vars:
        if v not in (v0, v1):
            clauses.append(getattr(c1, v) == getattr(c2, v))
    return And(*clauses)


def _make_sym_prop(swap, low_outputs):
    v0 = swap[0].replace(":", "")
    v1 = swap[1].replace(":", "")
    out_set = {v.replace(":", "") for v in low_outputs}

    def input_constraints(ctx1, ctx2, params):
        cs = [Int(v0 + "_1") == Int(v1 + "_2"), Int(v1 + "_1") == Int(v0 + "_2")]
        for k in params:
            vk = k.replace(":", "")
            if vk not in (v0, v1) and vk not in out_set:
                cs.append(getattr(ctx1, vk) == getattr(ctx2, vk))
        return cs

    def build_inv(c1, c2, inv_vars, inv_exprs, auto_counters, low_outputs):
        return _sym_build_inv(c1, c2, inv_vars, inv_exprs, auto_counters, low_outputs, v0, v1)

    def divergence(ctx1, ctx2, low_outputs):
        return Or(*[getattr(ctx1, v.replace(":", "")) != getattr(ctx2, v.replace(":", ""))
                    for v in low_outputs])

    prop = PropSpec(
        name="SYMMETRY-2",
        input_constraints=input_constraints,
        build_inv=build_inv,
        divergence=divergence,
        init_pass_msg="INV holds at loop entry under swap",
        init_fail_msg="INV does NOT hold at entry — check invariant or pre-loop code",
        cons_pass_msg="outputs agree despite swap",
        cons_fail_msg="outputs diverge — program is asymmetric",
        overall_pass_msg=f"SYMMETRY-2: HOLDS (f(...,{swap[0]},{swap[1]},...) == f(...,{swap[1]},{swap[0]},...))",
        overall_fail_msg=f"SYMMETRY-2: FAILS (outputs differ when {swap[0]} <-> {swap[1]})",
        inv_label=f"{v0}_1=={v1}_2, {v1}_1=={v0}_2, others equal  (auto-generated)",
    )
    return prop


def check_symmetry_all_tiers(irHandler, params, swap, low_outputs, progfl=None):
    """
    Symmetry-2 safety: swapping two inputs must not change outputs.
    Auto-dispatches across Tier 1 / Tier 2 / Tier 2b.
    """
    if len(swap) != 2:
        raise ValueError('--sym requires exactly two variable names, e.g. \'[":a", ":b"]\'')

    v0, v1 = swap[0].replace(":", ""), swap[1].replace(":", "")
    all_loops = find_all_loops(irHandler.ir)

    print(f"\n=== Symmetry-2 Verifier ===")
    print(f"  Swapped inputs : {swap[0]} <-> {swap[1]}")
    print(f"  Low outputs    : {low_outputs}")

    if not all_loops:
        print("  [Tier dispatch] No loops — Tier 1 (straight-line).")
        return check_symmetry(irHandler, params, swap, low_outputs)

    prop = _make_sym_prop(swap, low_outputs)

    if len(all_loops) == 1:
        print("  [Tier dispatch] Single loop — Tier 2.")
        loop = all_loops[0]
        head_idx, body_start, body_end, exit_idx = loop
        inv_exprs, inv_source, auto_counters = _resolve_inv_for_loop(
            irHandler.ir, head_idx, exit_idx, progfl)
        r1, r2, r3, _, _, all_pass = _check_relational_loop(
            prop, irHandler, params, low_outputs,
            inv_exprs, inv_source, auto_counters,
            irHandler.ir[:head_idx],
            irHandler.ir[body_start:body_end],
            irHandler.ir[exit_idx:],
            irHandler.ir[head_idx][0],
            head_idx, exit_idx,
        )
        print(f"\n  --- Overall ---")
        if all_pass:
            print(f"  {prop.overall_pass_msg}")
        else:
            print(f"  {prop.overall_fail_msg}")
        print("===========================================\n")
        return "unsat" if all_pass else "sat"

    print(f"  [Tier dispatch] {len(all_loops)} loops — Tier 2b (multi-loop).")
    inv_groups = _collect_inv_groups(irHandler.ir, all_loops, progfl)
    return _check_relational_multi_loop(prop, irHandler, all_loops, params, low_outputs,
                                        inv_groups, prop.name)


# ---------------------------------------------------------------------------
# Monotonicity: thin wrapper over the generic engine
# ---------------------------------------------------------------------------
#
# Property: if input x increases (x_1 <= x_2), all low outputs must not decrease
#           (out_1 <= out_2 for every low output).
#
# Trace 1: smaller input value.  Trace 2: larger input value.
# Input constraints: mono_var_1 <= mono_var_2, all other inputs equal.
# Divergence (violation): exists out s.t. out_1 > out_2.
# Auto-invariant: out_1 <= out_2, counters equal, mono_var_1 <= mono_var_2.

def _mono_build_inv(c1, c2, inv_vars, inv_exprs, auto_counters, low_outputs, mono_var):
    """
    Relational invariant for monotonicity.

    When annotated: use user expressions (user must encode the ordering relation).
    Auto-generated:
      - mono_var_1 <= mono_var_2  (input ordering is preserved through the loop)
      - out_1 <= out_2            for every low output
      - counter_1 == counter_2    loop counters are equal (same public bound)
      - v_1 == v_2                for all other invariant vars
    """
    if inv_exprs is not None:
        rel = build_relational_invariant(c1, c2, inv_exprs)
        auto_eq = [getattr(c1, v) == getattr(c2, v) for v in auto_counters]
        inv_expr_vars = set(_extract_inv_vars(inv_exprs))
        for v in [x.replace(":", "") for x in low_outputs]:
            if v not in inv_expr_vars:
                auto_eq.append(getattr(c1, v) == getattr(c2, v))
        return And(rel, *auto_eq) if auto_eq else rel

    clauses = []
    # Input ordering maintained throughout
    clauses.append(getattr(c1, mono_var) <= getattr(c2, mono_var))
    # Output ordering: smaller input -> smaller-or-equal output
    for v in low_outputs:
        vn = v.replace(":", "")
        clauses.append(getattr(c1, vn) <= getattr(c2, vn))
    # Counters and other tracked vars are equal
    for v in inv_vars:
        if v != mono_var and v not in {o.replace(":", "") for o in low_outputs}:
            clauses.append(getattr(c1, v) == getattr(c2, v))
    return And(*clauses)


def _make_mono_prop(mono_var_str, low_outputs):
    mono_var = mono_var_str.replace(":", "")
    out_set = {v.replace(":", "") for v in low_outputs}

    def input_constraints(ctx1, ctx2, params):
        # Trace 1 has the smaller value of mono_var; trace 2 has the larger.
        cs = [Int(mono_var + "_1") <= Int(mono_var + "_2")]
        for k in params:
            vk = k.replace(":", "")
            if vk != mono_var and vk not in out_set:
                cs.append(getattr(ctx1, vk) == getattr(ctx2, vk))
        return cs

    def build_inv(c1, c2, inv_vars, inv_exprs, auto_counters, low_outputs):
        return _mono_build_inv(c1, c2, inv_vars, inv_exprs, auto_counters, low_outputs, mono_var)

    def divergence(ctx1, ctx2, low_outputs):
        # Violation: some output is SMALLER in trace 2 than trace 1
        # i.e. the larger input produced a smaller output
        return Or(*[getattr(ctx1, v.replace(":", "")) > getattr(ctx2, v.replace(":", ""))
                    for v in low_outputs])

    prop = PropSpec(
        name="MONOTONICITY",
        input_constraints=input_constraints,
        build_inv=build_inv,
        divergence=divergence,
        init_pass_msg="INV holds at loop entry (output ordering matches input ordering)",
        init_fail_msg="INV does NOT hold at entry — outputs already inverted before loop",
        cons_pass_msg="larger input produces larger-or-equal output",
        cons_fail_msg="larger input produces smaller output — monotonicity violated",
        overall_pass_msg=f"MONOTONICITY: HOLDS ({mono_var_str}_1 <= {mono_var_str}_2 => all outputs non-decreasing)",
        overall_fail_msg=f"MONOTONICITY: FAILS (increasing {mono_var_str} can decrease an output)",
        inv_label=(f"{mono_var}_1 <= {mono_var}_2, "
                   f"outputs non-decreasing, others equal  (auto-generated)"),
    )
    return prop


def check_monotonicity(irHandler, params, mono_var, low_outputs, progfl=None):
    """
    Monotonicity check: increasing mono_var must not decrease any low output.
    Auto-dispatches across Tier 1 / Tier 2 / Tier 2b.

    mono_var: string like ':x'
    """
    all_loops = find_all_loops(irHandler.ir)

    print(f"\n=== Monotonicity Verifier ===")
    print(f"  Monotone input : {mono_var}")
    print(f"  Low outputs    : {low_outputs}")

    prop = _make_mono_prop(mono_var, low_outputs)

    if not all_loops:
        print("  [Tier dispatch] No loops — Tier 1 (straight-line).")
        # Tier 1: direct Z3 query, no invariant needed
        ctx1 = init_context(params, "_1")
        ctx2 = init_context(params, "_2")
        encode_stmts(ctx1, irHandler.ir)
        encode_stmts(ctx2, irHandler.ir)
        input_cs = prop.input_constraints(ctx1, ctx2, params)
        s = Solver()
        s.add(*input_cs)
        s.add(prop.divergence(ctx1, ctx2, low_outputs))
        result = s.check()
        if result == unsat:
            print(f"\n  {prop.overall_pass_msg}")
        elif result == sat:
            m = s.model()
            print(f"\n  {prop.overall_fail_msg}  Counterexample:")
            mv = mono_var.replace(":", "")
            v1_val = m.eval(_z3_wrap(getattr(ctx1, mv)), model_completion=True)
            v2_val = m.eval(_z3_wrap(getattr(ctx2, mv)), model_completion=True)
            print(f"    {mono_var}: trace1={v1_val}, trace2={v2_val}  (trace1 <= trace2)")
            for v in low_outputs:
                vn = v.replace(":", "")
                o1 = m.eval(_z3_wrap(getattr(ctx1, vn)), model_completion=True)
                o2 = m.eval(_z3_wrap(getattr(ctx2, vn)), model_completion=True)
                tag = " <-- DECREASES" if str(o1) > str(o2) else ""
                print(f"    {v}: trace1={o1}, trace2={o2}{tag}")
        print("=============================\n")
        return str(result)

    if len(all_loops) == 1:
        print("  [Tier dispatch] Single loop — Tier 2.")
        loop = all_loops[0]
        head_idx, body_start, body_end, exit_idx = loop
        inv_exprs, inv_source, auto_counters = _resolve_inv_for_loop(
            irHandler.ir, head_idx, exit_idx, progfl)
        r1, r2, r3, _, _, all_pass = _check_relational_loop(
            prop, irHandler, params, low_outputs,
            inv_exprs, inv_source, auto_counters,
            irHandler.ir[:head_idx],
            irHandler.ir[body_start:body_end],
            irHandler.ir[exit_idx:],
            irHandler.ir[head_idx][0],
            head_idx, exit_idx,
        )
        print(f"\n  --- Overall ---")
        print(f"  {prop.overall_pass_msg if all_pass else prop.overall_fail_msg}")
        print("=============================\n")
        return "unsat" if all_pass else "sat"

    print(f"  [Tier dispatch] {len(all_loops)} loops — Tier 2b (multi-loop).")
    inv_groups = _collect_inv_groups(irHandler.ir, all_loops, progfl)
    return _check_relational_multi_loop(prop, irHandler, all_loops, params, low_outputs,
                                        inv_groups, prop.name)


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
    if is_turtle:
        _check_axis_aligned(irHandler.ir)

    print("\n=== Relational Verifier (Tier 2: loop) ===")
    print(f"  Low inputs  : {low_inputs}")
    print(f"  Low outputs : {low_outputs}")
    if is_turtle:
        print("  Turtle mode : position + path checks on body and post-loop")

    all_loops = find_all_loops(irHandler.ir)
    if not all_loops:
        print("  [!] No loop found — falling back to Tier 1.")
        return check_non_interference(irHandler, params, low_inputs, low_outputs)

    # --- Dispatch to multi-loop path when there is more than one loop ---
    if len(all_loops) > 1:
        # Build per-loop (inv_exprs, inv_source) pairs
        inv_groups_multi = []
        sidecar_groups = _parse_inv_file_multi(progfl)   # list of groups or None
        for k, lp in enumerate(all_loops):
            lp_head = lp[0]
            ann = _annotations_for_loop(irHandler.ir, lp_head)
            if ann:
                inv_groups_multi.append((ann, f"from @@ annotations (loop {k+1})"))
            elif sidecar_groups and k < len(sidecar_groups):
                inv_groups_multi.append((sidecar_groups[k], f"from .inv sidecar (group {k+1})"))
            else:
                inv_groups_multi.append((None, "auto-generated"))
        return check_multi_loop_non_interference(
            irHandler, all_loops, params, low_inputs, low_outputs,
            inv_groups_multi, progfl=progfl
        )

    # --- Single loop: use original Tier 2 path ---
    loop = all_loops[0]
    head_idx, body_start, body_end, exit_idx = loop
    pre_loop_ir   = irHandler.ir[:head_idx]
    body_ir       = irHandler.ir[body_start:body_end]
    post_loop_ir  = irHandler.ir[exit_idx:]
    loop_cond     = irHandler.ir[head_idx][0]

    print(f"\n  Loop head    : IR[{head_idx}]  condition: {loop_cond}")
    print(f"  Body         : IR[{body_start}:{body_end}]")
    print(f"  Loop exit    : IR[{exit_idx}]")
    print(f"  Post-loop    : IR[{exit_idx}:{len(irHandler.ir)}]  ({len(post_loop_ir)} statements)")

    # ------------------------------------------------------------------
    # Timing side-channel: secret-dependent loop bound
    # ------------------------------------------------------------------
    is_tainted, bound_str, tainted_vars = _check_secret_bound(
        irHandler.ir, head_idx, params, low_inputs
    )
    if is_tainted:
        body_ir = irHandler.ir[body_start:body_end]
        touches_low = _body_writes_low_output(body_ir, low_outputs)
        if touches_low:
            # Body writes a low output, so the secret bound causes a direct value
            # leak too (different iteration counts -> different output values).
            # Fall through to the standard 3-check machinery so the full
            # counterexample is reported — but warn about the bound first.
            print(f"\n  [!] WARNING: Loop bound '{bound_str}' is non low")
            print(f"  The body also writes a low output — this is a VALUE LEAK, not just a timing leak.")
            print(f"  Continuing with standard invariant checks to produce a full counterexample...\n")
        else:
            # Body never touches any low output, so the only observable difference
            # between two runs with different secrets is the number of iterations.
            print(f"\n  [!] TIMING SIDE-CHANNEL DETECTED")
            print(f"  The loop bound '{bound_str}' is non low")
            print(f"  The loop body does NOT write any low output, so there is no direct value leak.")
            print(f"  However, an observer can infer the secret by counting loop iterations")
            print(f"  (e.g. via execution time, energy consumption, or cache behaviour).")
            print(f"\n  NON-INTERFERENCE: FAILS (pure timing / termination side-channel)")
            print("===========================================\n")
            return "sat"

    # Check for relational invariant annotations:
    #   Priority: 1. @@ annotations in IR  2. .inv sidecar  3. auto-generated
    inv_exprs = None
    inv_source = None

    # 1. Scan IR for @@ InvariantAnnotation nodes
    annotated = [str(stmt.expr) for stmt, _ in irHandler.ir
                 if isinstance(stmt, ChironAST.InvariantAnnotation)]
    if annotated:
        inv_exprs = annotated
        inv_source = "from @@ annotations in .tl"

    # 2. Fall back to .inv sidecar file
    if inv_exprs is None:
        inv_exprs = _parse_inv_file(progfl)
        if inv_exprs is not None:
            inv_source = "from .inv sidecar"

    # Auto-collect loop counters — always equal across traces
    auto_counters = []
    for stmt, _ in irHandler.ir:
        if isinstance(stmt, ChironAST.AssignmentCommand):
            v = str(stmt.lvar).replace(":", "")
            if "__rep_counter_" in v and v not in auto_counters:
                auto_counters.append(v)

    # Build invariant variable list (used when no annotations/sidecar, or to seed _fresh_ctx)
    if inv_vars is None:
        if inv_exprs is not None:
            # Variables to create fresh Z3 vars for = all vars mentioned in expressions
            # Plus loop counters, low inputs, and low outputs (always equal across traces)
            inv_vars = _extract_inv_vars(inv_exprs)
            for v in auto_counters:
                if v not in inv_vars:
                    inv_vars.append(v)
            for v in [v.replace(":", "") for v in low_inputs]:
                if v not in inv_vars:
                    inv_vars.append(v)
            for v in [v.replace(":", "") for v in low_outputs]:
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
        print(f"  Invariant    : relational expressions {inv_exprs}  ({inv_source})")
    else:
        print(f"  Invariant    : equal across traces for {inv_vars}")

    def _build_inv(c1, c2):
        if inv_exprs is not None:
            rel = build_relational_invariant(c1, c2, inv_exprs)
            # Low inputs and loop counters are always equal across traces
            auto_eq = [getattr(c1, v.replace(":", "")) == getattr(c2, v.replace(":", ""))
                       for v in low_inputs]
            auto_eq += [getattr(c1, v) == getattr(c2, v) for v in auto_counters]
            # Low outputs not already covered by inv_exprs are always equal too
            inv_expr_vars = set(_extract_inv_vars(inv_exprs))
            for v in [v.replace(":", "") for v in low_outputs]:
                if v not in inv_expr_vars:
                    auto_eq.append(getattr(c1, v) == getattr(c2, v))
            return And(rel, *auto_eq) if auto_eq else rel
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
        body_step_diffs = []
        for i in range(n_body_steps):
            idx = pre_body_steps + i
            body_step_diffs.append(
                getattr(ctx1_post, f'turtle_step_{idx}_dx') != getattr(ctx2_post, f'turtle_step_{idx}_dx'))
            body_step_diffs.append(
                getattr(ctx1_post, f'turtle_step_{idx}_dy') != getattr(ctx2_post, f'turtle_step_{idx}_dy'))
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
        post_step_diffs = []
        for i in range(n_post_steps):
            idx = pre_post_steps + i
            post_step_diffs.append(
                getattr(ctx1_final, f'turtle_step_{idx}_dx') != getattr(ctx2_final, f'turtle_step_{idx}_dx'))
            post_step_diffs.append(
                getattr(ctx1_final, f'turtle_step_{idx}_dy') != getattr(ctx2_final, f'turtle_step_{idx}_dy'))
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
    """Report path-safety check result with per-step (dx, dy) counterexample."""
    if result == unsat:
        print(f"  [PASS] Path safety: all {n_steps} move-step displacement(s) equal across traces.")
    elif result == sat:
        m = solver.model()
        print(f"  [FAIL] Path leak — move-step displacements can differ across traces:")
        for i in range(n_steps):
            idx = step_offset + i
            dx1 = m.eval(_z3_wrap(getattr(ctx1, f'turtle_step_{idx}_dx')), model_completion=True)
            dy1 = m.eval(_z3_wrap(getattr(ctx1, f'turtle_step_{idx}_dy')), model_completion=True)
            dx2 = m.eval(_z3_wrap(getattr(ctx2, f'turtle_step_{idx}_dx')), model_completion=True)
            dy2 = m.eval(_z3_wrap(getattr(ctx2, f'turtle_step_{idx}_dy')), model_completion=True)
            tag = " <-- LEAK" if (str(dx1) != str(dx2) or str(dy1) != str(dy2)) else ""
            print(f"    step {i}: trace1=(dx={dx1}, dy={dy1})  trace2=(dx={dx2}, dy={dy2}){tag}")
    else:
        print("  [?] Path check returned UNKNOWN")
