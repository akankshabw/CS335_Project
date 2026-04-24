# Program Analysis with Chiron

A framework to teach program analysis, verification, and testing in a graduate-level course.

```
░█████╗░██╗░░██╗██╗██████╗░░█████╗░███╗░░██╗
██╔══██╗██║░░██║██║██╔══██╗██╔══██╗████╗░██║
██║░░╚═╝███████║██║██████╔╝██║░░██║██╔██╗██║
██║░░██╗██╔══██║██║██╔══██╗██║░░██║██║╚████║
╚█████╔╝██║░░██║██║██║░░██║╚█████╔╝██║░╚███║
░╚════╝░╚═╝░░╚═╝╚═╝╚═╝░░╚═╝░╚════╝░╚═╝░░╚══╝
```
[![Architecture Diagram](./assets/Architecture_Digram.png)](./assets/Architecture_Digram.png)

## Video Demo 

Fuzzer Demo in Chiron Framework. Click the image below

<a href="https://raw.githubusercontent.com/PRAISE-group/Chiron-Framework/master/assets/Fuzzer_Demo.mp4" title="Link Title"><img src="https://raw.githubusercontent.com/PRAISE-group/Chiron-Framework/master/assets/Screenshot%20from%202025-01-16%2012-34-51.png" alt="Alternate Text" /></a>

- [Some nice words in WSS' 2023, IIT Delhi about Chiron Framework](https://www.linkedin.com/posts/ashupdsce_wss-wss2023-iitd-activity-7150851909581463553-bJ6-?utm_source=share&utm_medium=member_desktop)
- [ASE 2023 Conference Page](https://conf.researchr.org/details/ase-2023/ase-2023-papers/117/An-Integrated-Program-Analysis-Framework-for-Graduate-Courses-in-Programming-Language)
- [Read our research paper here](https://ieeexplore.ieee.org/document/10298417)

## Citation 

If you want to cite this work, you may use this.

```
@INPROCEEDINGS{ase_2023_chiron,
  author={Chatterjee, Prantik and Kalita, Pankaj Kumar and Lahiri, Sumit and Muduli, Sujit Kumar and Singh, Vishal and Takhar, Gourav and Roy, Subhajit},
  booktitle={2023 38th IEEE/ACM International Conference on Automated Software Engineering (ASE)}, 
  title={An Integrated Program Analysis Framework for Graduate Courses in Programming Languages and Software Engineering}, 
  year={2023},
  volume={},
  number={},
  pages={598-610},
  keywords={Surveys;Computer languages;Program processors;Software algorithms;Software systems;Task analysis;Engines;program analysis verification and testing;programming languages;software engineering;graduate level course;education},
  doi={10.1109/ASE56229.2023.00101}}
```

---

## Installing Dependencies

You need to install `java` Runtime and dependency libs. You may also need to install java JDK (`javac`) on older Windows machine.
Python, pip and other packages are also required. Please follow the steps given below.

If you are using Windows, we highly recommend using `powershell` instead of `wsl` or `windows command prompt`.

- [https://learn.microsoft.com/en-us/powershell/scripting/install/install-powershell-on-windows?view=powershell-7.5](https://learn.microsoft.com/en-us/powershell/scripting/install/install-powershell-on-windows?view=powershell-7.5)

```pwsh
winget search --id Microsoft.PowerShell

Name               Id                           Version Source
---------------------------------------------------------------
PowerShell         Microsoft.PowerShell         7.5.4.0 winget
PowerShell Preview Microsoft.PowerShell.Preview 7.6.0.6 winget

winget install --id Microsoft.PowerShell --source winget
```
 
### Installing Java

Installing the lastest java package for your operating system. 

- [https://www.java.com/en/download/manual.jsp](https://www.java.com/en/download/manual.jsp)

```bash
$ java --version 
openjdk 21.0.9 2025-10-21 LTS
OpenJDK Runtime Environment Temurin-21.0.9+10 (build 21.0.9+10-LTS)
OpenJDK 64-Bit Server VM Temurin-21.0.9+10 (build 21.0.9+10-LTS, mixed mode, sharing)

$ javac --version
javac 21.0.9
```

### Installing Python

We recommend using the latest version of Python (`python3.14`) with python install manager.

- [https://www.python.org/](https://www.python.org/)

```bash
$ python --version 
Python 3.11.3

$ python3.14 --version
Python 3.14.2
```

### Installing UV (astral) package manager

We recommend using `uv` package manager to handle python dependencies for Chiron. 
Virtual environment with `uv` also works without issues.

If you intend to use `pip` and system-wide install `python`, install the following packages using pip instead of uv.

- [https://docs.astral.sh/uv/getting-started/installation](https://docs.astral.sh/uv/getting-started/installation/#__tabbed_1_1)
- [https://www.antlr.org/download.html](https://www.antlr.org/download.html)

These packages are required, you may need to try different versions of these packages, for python3.10 or python3.11. 

- [https://pypi.org/project/antlr4-python3-runtime/](https://pypi.org/project/antlr4-python3-runtime/)
- [https://pypi.org/project/numpy/](https://pypi.org/project/numpy/)
- [https://pypi.org/project/z3-solver/](https://pypi.org/project/z3-solver/)
- [https://pypi.org/project/networkx/](https://pypi.org/project/networkx/)

```bash
$ uv add antlr4-python3-runtime==4.13.2 networkx z3-solver numpy
Resolved 5 packages in 127ms
Audited 4 packages in 30ms

# If you do not want to use uv package manager.
$ pip install antlr4-python3-runtime==4.13.2 networkx z3-solver numpy 

# On UNIX/MacOSX platform, run this. On Windows (10/11) not required.
$ sudo apt-get install python3-tk
```

### Generating the ANTLR files

The `antlr` files need to be rebuilt if any changes are made to the `tlang.g4` file or when installing Chiron for the first time.
We use a visitor pattern to generate the AST from parsing. 

- [https://www.antlr.org/about.html](https://www.antlr.org/about.html)

You may download the latest antlr version complete jar binary to the `\ChironCore\extlib` folder and use it.

- [https://www.antlr.org/download/antlr-4.13.2-complete.jar](https://www.antlr.org/download/antlr-4.13.2-complete.jar)

From the directory shown in the command below, build the antlr related visitor code with java and latest antlr runtime jar files.

```bash
$ cd ChironCore/turtparse
$ java -cp ../extlib/antlr-4.13.2-complete.jar org.antlr.v4.Tool -Dlanguage=Python3 -visitor -no-listener tlang.g4
```

### Running an example

The main directory for source files is `ChironCore`. We have examples of the turtle programs in `examples` folder.
To pass parameters (input params) for running a turtle program, use the `-d` flag. Pass the parameters as a python dictionary. 

```bash
$ cd ChironCore
$ python3 chiron.py -r ./example/example1.tl -d '{":x": 20, "y": 30, ":z": 20, ":p": 40}'
```

If you are using `uv` package manager, which we highly recommend using, run `Chiron` using the following commands.
Always prefix with `uv run` instead of running with `python`.

```bash
$ cd ChironCore
$ uv run chiron.py -r ./example/example1.tl -d '{":x": 20, "y": 30, ":z": 20, ":p": 40}'
```

### See help for other command line options

```bash
$ python3 chiron.py --help
```

---

## Relational Verification of Hyperproperties (CS335 Project Extension)

This extension adds a **relational verification** pass to Chiron that checks security hyperproperties over pairs of program executions using the Z3 SMT solver. Three properties are supported:

| Property | Question | Flag |
|---|---|---|
| **Non-interference** | Can secret inputs influence public outputs? | `-rv` / `-rvl` |
| **2-Symmetry** | Does swapping two inputs change any output? | `--sym` |
| **Monotonicity** | Can increasing an input decrease any output? | `--mono` |

All three properties are checked across three program tiers:
- **Tier 1** — straight-line programs and conditionals (`if`/`else`)
- **Tier 2** — programs with a single `repeat`-loop
- **Tier 2b** — programs with multiple sequential `repeat`-loops

### Files Changed

| File | Change |
|---|---|
| `ChironCore/relationalVerifier.py` | **New.** Core verifier: dual-context Z3 encoding, 3-check inductive loop proof, turtle symbolic model, path/position safety, `_merge_contexts` for conditionals, `@@` annotation scanning, `.inv` sidecar parsing, timing side-channel detection, Tier 2b multi-loop engine, `PropSpec` generic 2-safety engine, symmetry-2 and monotonicity. |
| `ChironCore/chiron.py` | **Modified.** Added CLI flags: `-rv`, `-rvl`, `--low_in`, `--low_out`, `--sym`, `--mono`. |
| `ChironCore/turtparse/tlang.g4` | **Modified.** Added `annotation` grammar rule for `@@` invariant annotations; regenerated `tlangParser.py` and `tlangVisitor.py`. |
| `ChironCore/ChironAST/ChironAST.py` | **Modified.** Added `InvariantAnnotation` AST node. |
| `ChironCore/ChironAST/builder.py` | **Modified.** Added `visitAnnotation` visitor method. |
| `ChironCore/example/` | **New files.** 80+ test programs covering all tiers and properties. |
| `ChironCore/run_tests.sh` | **New.** Automated test runner |

---

### Running the Relational Verifier

All commands are run from the `ChironCore/` directory.

#### Non-Interference

**Tier 1 — straight-line programs:**
```bash
# Safe: secret never reaches :out
python3 chiron.py example/ni_safe.tl -rv \
  -d '{":pub":0, ":secret":0, ":out":0}' \
  --low_in '[":pub"]' --low_out '[":out"]'

# Leak: :out = :pub + :secret
python3 chiron.py example/ni_leak.tl -rv \
  -d '{":pub":0, ":secret":0, ":out":0}' \
  --low_in '[":pub"]' --low_out '[":out"]'
```

**Tier 2 — single loop:**
```bash
# Safe: loop accumulates :pub only
python3 chiron.py example/loop_safe.tl -rvl \
  -d '{":pub":0, ":secret":0, ":n":5, ":out":0}' \
  --low_in '[":pub",":n"]' --low_out '[":out"]'

# Leak: loop accumulates :secret
python3 chiron.py example/loop_leak.tl -rvl \
  -d '{":pub":0, ":secret":0, ":n":5, ":out":0}' \
  --low_in '[":pub",":n"]' --low_out '[":out"]'
```

**Tier 2b — multiple sequential loops:**
```bash
python3 chiron.py example/multi_loop_safe.tl -rvl \
  -d '{":pub":0, ":secret":0, ":n":5, ":m":3, ":out1":0, ":out2":0}' \
  --low_in '[":pub",":n",":m"]' --low_out '[":out1",":out2"]'
```

**With non-trivial relational invariant (inline `@@` annotation):**
```bash
# :temp is not low but affects :out; annotation supplies the cross-trace relation
python3 chiron.py -rvl example/safe_annotated.tl \
  -d '{":n":3, ":pub":10, ":secret":5, ":out":0, ":temp":0}' \
  --low_in '[":pub",":n"]' --low_out '[":out"]'
```

**With `.inv` sidecar file:**
```bash
# safe_nontrivial_inv.inv sits alongside the .tl file and lists invariant expressions
python3 chiron.py -rvl example/safe_nontrivial_inv.tl \
  -d '{":n":3, ":pub":10, ":secret":5, ":out":0, ":temp":0}' \
  --low_in '[":pub",":n"]' --low_out '[":out"]'
```

#### Turtle Path/Position Safety

Declare `":turtle_x"` and/or `":turtle_y"` as low outputs to trigger turtle geometry checks. Two levels of check run automatically:
- **Position safety** — can the final `(x, y)` position differ across traces?
- **Path safety** — can any individual move's displacement vector differ?

```bash
# Position and path both leak (move by secret amount)
python3 chiron.py example/turtle_pos_leak.tl -rv \
  -d '{":pub":0, ":secret":0}' \
  --low_in '[":pub"]' --low_out '[":turtle_x",":turtle_y"]'

# Path leaks but final position is safe (forward pub+secret; backward secret)
python3 chiron.py example/turtle_path_leak_pos_safe.tl -rv \
  -d '{":pub":5, ":secret":0}' \
  --low_in '[":pub"]' --low_out '[":turtle_x",":turtle_y"]'

# Visual witness: zigzag amplitude proportional to :secret
python3 chiron.py -rvl example/turtle_zigzag_leak.tl \
  -d '{":n":12, ":pub":20, ":secret":0, ":out":0}' \
  --low_in '[":pub",":n"]' --low_out '[":out",":turtle_x",":turtle_y"]'
bash witness.sh   # launches two turtle windows side-by-side
```

#### Timing Side-Channel Detection

A secret-dependent loop bound leaks even if the body never writes a low output.

```bash
# Pure timing leak: bound = :secret, body only writes :temp (not low)
python3 chiron.py example/timing_leak.tl -rvl \
  -d '{":pub":0, ":secret":0, ":out":0}' \
  --low_in '[":pub"]' --low_out '[":out"]'

# Value + timing leak: bound = :secret, body writes :out (low)
python3 chiron.py example/timing_value_leak.tl -rvl \
  -d '{":pub":0, ":secret":0, ":out":0}' \
  --low_in '[":pub"]' --low_out '[":out"]'
```

#### 2-Symmetry

Checks that swapping two named inputs does not change any low output. Tier is auto-detected.

```bash
# Tier 1 — straight-line (safe: addition is commutative)
python3 chiron.py example/sym_safe.tl \
  --sym '[":a", ":b"]' --low_out '[":out"]' \
  -d '{":a": 0, ":b": 0, ":out": 0}'

# Tier 1 — straight-line (not symmetric: extra :b)
python3 chiron.py example/sym_leak.tl \
  --sym '[":a", ":b"]' --low_out '[":out"]' \
  -d '{":a": 0, ":b": 0, ":out": 0}'

# Tier 1 — conditional max (symmetric)
python3 chiron.py example/sym_cond_max.tl \
  --sym '[":a", ":b"]' --low_out '[":out"]' \
  -d '{":a": 0, ":b": 0, ":out": 0}'

# Tier 2 — single loop (symmetric)
python3 chiron.py example/sym_loop_cond_sym.tl \
  --sym '[":a", ":b"]' --low_out '[":out"]' \
  -d '{":a": 0, ":b": 0, ":n": 0, ":out": 0}'

# Tier 2b — multiple loops (symmetric: both loops use :a+:b)
python3 chiron.py example/sym_loop_commute.tl \
  --sym '[":a", ":b"]' --low_out '[":out"]' \
  -d '{":a":0, ":b":0, ":n":0, ":m":0, ":out":0}'

# Tier 2b — multiple loops (not symmetric: second loop uses :b+:b)
python3 chiron.py example/sym_loop_asym.tl \
  --sym '[":a", ":b"]' --low_out '[":out"]' \
  -d '{":a":0, ":b":0, ":n":0, ":m":0, ":out":0}'
```

#### Monotonicity

Checks that increasing a named input never decreases any low output. Tier is auto-detected.

```bash
# Tier 1 — safe (net: out = pub + x, increasing in :x)
python3 chiron.py example/mono_safe.tl \
  --mono ':x' --low_out '[":out"]' \
  -d '{":x": 0, ":pub": 0, ":out": 0, ":temp": 0}'

# Tier 1 — not monotone (out = pub - x, decreasing in :x)
python3 chiron.py example/mono_unsafe.tl \
  --mono ':x' --low_out '[":out"]' \
  -d '{":x": 0, ":pub": 0, ":out": 0}'

# Tier 2 — single loop (safe: each iteration adds :x)
python3 chiron.py example/mono_loop_safe.tl \
  --mono ':x' --low_out '[":out"]' \
  -d '{":x":0, ":n":0, ":out":0}'

# Tier 2 — single loop (not monotone: each iteration subtracts :x)
python3 chiron.py example/mono_loop_unsafe.tl \
  --mono ':x' --low_out '[":out"]' \
  -d '{":x":0, ":n":0, ":out":0}'

# Tier 2b — multiple loops (safe: both loops add :x)
python3 chiron.py example/mono_multiloop_safe.tl \
  --mono ':x' --low_out '[":out"]' \
  -d '{":x":0, ":n":0, ":m":0, ":out":0}'
```

#### Running All Tests at Once

An automated test runner

```bash
cd ChironCore
bash run_tests.sh
```
---

### Relational Invariant Annotations

When an intermediate (non-low) variable indirectly affects a low output, the default invariant is too weak to prove safety. Two mechanisms supply stronger relational invariants.

**Inline `@@` annotation** — written directly in the `.tl` file:
```
:out = 0
:temp = :secret + :pub
@@ :out
@@ :temp - :secret
repeat :n [ :out = :out + :temp - :secret ]
```
Each `@@ expr` line tells the verifier to assert `expr(trace1) = expr(trace2)` as part of the loop invariant.

**`.inv` sidecar file** — a separate `prog.inv` file alongside `prog.tl`:
```
:out
:__rep_counter_1
:temp - :secret
```
Same semantics; useful when you don't want to modify the source program.

Priority: `@@` annotations > `.inv` sidecar > auto-generated simple equality.

---

### CLI Flag Reference (Relational Verifier)

| Flag | Description |
|---|---|
| `-rv` / `--relationalVerify` | Non-interference check, Tier 1 (straight-line + conditionals). Requires `-d` with all variables and `--low_in`, `--low_out`. |
| `-rvl` / `--relationalVerifyLoop` | Non-interference check, Tier 2 and Tier 2b (single or multiple loops). Same requirements as `-rv`. |
| `--low_in '[":v1", ...]'` | List of low (public) input variables. |
| `--low_out '[":v1", ...]'` | List of low (public) output variables. Declare `":turtle_x"` / `":turtle_y"` here to enable turtle checks. |
| `--sym '[":a", ":b"]'` | 2-Symmetry check: swap `:a` and `:b` between traces. Requires exactly two variables. Auto-dispatches across all tiers. |
| `--mono ':x'` | Monotonicity check: trace 1 has smaller `:x`, trace 2 has larger. Auto-dispatches across all tiers. |
| `-d '{":v": val, ...}'` | Initial variable values (all program variables must be listed). |
