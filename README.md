# PyMetricor
 
A static analysis tool that scores Python codebases across four dimensions: **Readability**, **Efficiency**, **Maintainability**, and **Security**.
 
Each dimension is made up of multiple metrics. Each metric collects signals across two analysis stages:
  - Token scan
  - AST scan
and produces a weighted score.

All per-file scores are aggregated into a single project-level score using composite mass weighting,
so larger and more complex files contribute proportionally more than trivial ones.

## Installation

Requires Python 3.12+ (the code uses `typing.override`)

```bash
git clone https://github.com/Altered-commits/PyMetricor
cd PyMetricor
pip install -r requirements.txt
```

Dependencies (pinned in `requirements.txt` so scores are reproducible):
- `xxhash` - Duplicate code detection
- `astroid` - AST parsing and inference
- `PyYAML` - PyMetricor configuration and Schema for Reasoning Engine

## Configuration

### `pymetricor.yml` - Project Configuration

The config file is looked up in this order, and is never created implicitly:

1. `--config FILE` on the command line
2. the `PYMETRICOR_CONFIG` environment variable
3. `pymetricor.yml` next to `main.py` (the shipped defaults)

Results therefore do not depend on the directory PyMetricor is run from. A user file only needs the keys it changes; everything else falls back to the shipped values. Every weight group must sum to 1.0, and unknown keys are reported as warnings.

Controls all scoring weights and per-metric tuning parameters.

**Section weights** - how much each dimension contributes to the final score:
```yaml
weights:
  sections:
    readability: 0.30
    efficiency: 0.25
    maintainability: 0.25
    security: 0.20
```

**Composite mass** - how file size is computed for aggregation weighting. Larger/more complex files contribute more to the project score:
```yaml
weights:
  file_composite:
    loc: 0.2        # Lines of code
    tokens: 0.4     # Token count
    ast_nodes: 0.4  # AST node count
```

**Per-metric weights** - how much each individual metric contributes to its section. Must sum to 1.0 per section.

**Project-level metric** - `module_coupling` (maintainability) is computed from the import graph of everything analysed in one run: a module's fan-out (project modules it imports), fan-in (project modules that import it) and membership of a load-time import cycle. Imports inside functions and under `if TYPE_CHECKING:` count for fan-in and fan-out but not for cycles, and `from pkg import Name` counts as a dependency on the module that defines `Name` when `pkg/__init__.py` only re-exports it. A file analysed on its own scores 100.

**Tuning** - each metric exposes sensitivity constants and thresholds that control how harshly violations are penalised. For example:

```yaml
tuning:
  readability:
    thresholds:
      preferred_line_length: 100
      ideal_comment_ratio: 0.10
      min_identifier_length: 2
    sensitivity:
      line_length: 0.05
      comment_density: 4.5
      identifier_length: 2.0

  security:
    sensitivity:
      broken_cryptography: 0.5
      arbitrary_code_execution: 0.5
      unsafe_file_access: 0.5
      injection_and_request_forgery: 0.5
```

Docstring lines count toward `ideal_comment_ratio`, and files shorter than `min_function_size` need no comments. `identifier_length` penalises the share of distinct names shorter than `min_identifier_length`; loop targets, comprehension variables, `_`, `self` and `cls` are exempt.

Higher sensitivity values produce steeper score decay for the same number of violations.
Security sensitivity constants are the `k` values fed into the exponential decay formula `100 * exp(-weight * k)`.

**Identifier style** - the naming convention enforced per symbol category:
```yaml
tuning:
  readability:
    identifier_style:
      function_def: PASCAL_CASE
      class_def: PASCAL_CASE
      instance_attr: SNAKE_CASE
      variable: SNAKE_CASE
```

Supported styles: `SNAKE_CASE`, `PASCAL_CASE`, `CAMEL_CASE`, `SCREAMING_SNAKE_CASE`, `KEBAB_CASE`, `UPPER_FLAT_CASE`, `FLATCASE`, `TRAIN_CASE`, `COBOL_CASE`.

### `schema.yml` - Reasoning Engine Knowledge Base

This file is the entire domain knowledge of the security's reasoning engine.
No security logic is hardcoded in Python - adding or changing an entry here immediately changes engine behaviour with no code changes required.

**Properties** - the abstract traits a value can carry through the program:

| Property | Meaning |
|---|---|
| `CONSTANT` | Value is a known literal, not influenced by runtime input |
| `DYNAMIC` | Value is constructed at runtime and cannot be statically verified |
| `EXTERNAL_ORIGIN` | Value originates from user input, environment, or network |
| `TEXTUAL` | Value is string-like |
| `BYTES_LIKE` | Value is bytes or bytearray |
| `CODE_LIKE` | Value could be interpreted as executable code |
| `REFLECTIVE` | Value is used for attribute/module lookup |
| `FINITE_DOMAIN` | Refinement of DYNAMIC - value comes from a known finite set |

**Capabilities** - what a function *can do*, not whether it is dangerous. The engine records capability use; queries decide whether it is a problem:

| Capability | Triggered by |
|---|---|
| `INVOKE_DYNAMIC` | `exec`, `eval`, `compile` |
| `MODIFY_FILESYSTEM` | `open`, `os.remove`, `shutil.*`, `flask.send_file`, `FileResponse`, pathlib methods (`p.read_text()`, `p.unlink()` ...) |
| `SPAWN_PROCESS` | `os.system`, `subprocess.run`/`Popen`/`call`/`check_output`/`getoutput`, `os.exec*`, `os.spawn*`, `asyncio.create_subprocess_*` |
| `DESERIALIZE` | `pickle.load(s)`, `yaml.load` without a safe loader, `marshal`, `shelve`, `dill`, `jsonpickle` |
| `EXTRACT_ARCHIVE` | `tar.extractall()` / `tar.extract()` and `shutil.unpack_archive` without a member filter |
| `PERFORM_CRYPTO` | `hashlib.md5`, `hashlib.sha1` |
| `PERFORM_REFLECTION` | `getattr`, `__import__` (no schema entries yet) |
| `EXECUTE_QUERY` | `cursor.execute`/`executemany`/`executescript`, `Model.objects.raw`, `qs.extra`, `sqlalchemy.text`, `RawSQL`, `pandas.read_sql` (statement argument only) |
| `SEND_REQUEST` | `requests.*`, `httpx.*`, `urllib.request.urlopen`/`Request`, `aiohttp.request`, `http.client.HTTP(S)Connection`, client-session methods (URL argument only) |
| `RENDER_TEMPLATE` | `jinja2.Template`, `env.from_string` (not on a sandboxed environment), `flask.render_template_string`, Django, Mako and Tornado `Template` (template source only) |

Capabilities feed four security metrics: `arbitrary_code_execution` (INVOKE_DYNAMIC, SPAWN_PROCESS, PERFORM_REFLECTION, DESERIALIZE, RENDER_TEMPLATE), `broken_cryptography` (PERFORM_CRYPTO), `unsafe_file_access` (MODIFY_FILESYSTEM, EXTRACT_ARCHIVE) and `injection_and_request_forgery` (EXECUTE_QUERY, SEND_REQUEST). A spec's `sink_args` names the arguments a capability is about, so `cursor.execute(sql, params)` with tainted `params` is a parameterised query, not a finding.

**Attributes** - an assignment to an attribute of a variable (`self.cmd = x`, `obj.path = p`, `self.repo.url = u`) is tracked on that variable's value, up to two attributes deep. A constructor call returns the object with the attributes its `__init__` assigned, a method call passes the receiver's tracked attributes into the method's summary, and a setter's assignments are kept on the receiver after the call.

**Methods** - `methods` in `schema.yml` lists sinks called on an object (`p.read_text()`), which apply only when the object has one of the spec's `receiver_types`. Pathlib paths and tar archives are carrier types: `Path(...)` and `tarfile.open(...)` set them, and only `/`, the methods listed in `preserved_by` (`p.resolve()`, `p.joinpath(x)`) and `p.parent` keep them, so `str(p).replace(...)` is not a path operation. A spec's `safe_args` lists arguments that make the call safe, such as `yaml.load(f, Loader=SafeLoader)` or `tar.extractall(d, filter="data")`.

**Sources** - where untrusted data enters without a call: attribute names such as `argv`, `environ` and `form`, and globals such as `request`, are listed under `sources` in `schema.yml`.

**Sanitisers** - `shlex.quote`, `shlex.join`, `os.path.basename`, `int` and `float` are function specs that remove `EXTERNAL_ORIGIN` (and `DYNAMIC` where the result is safe to splice) and add `SANITIZED`. A variable holding a sanitised value does not make a concatenation dynamic (`"ls " + shlex.quote(x)` stays safe).

**Validators and checks** - a value is also treated as validated after:
- a call to a project validation helper used as a statement, such as `validate_path_is_safe(p)` or `_raise_if_restricted_key(k)`, or the result of one, such as `p = sanitize_path(p)` (`validators` in `schema.yml`: names starting with `validate`, `sanitize`, `raise_if_` and similar);
- a guard in an `if` that leaves the function when it fails, or in an `assert`: the guards in `schema.yml` (`is_safe_path(p)`, `p.startswith(base)` on a normalised path, `re.fullmatch(...)`, `re.match` with a pattern anchored by `$`, `name.isalnum()`), `os.path.commonpath([base, p]) == base` on a normalised `p`, and a check that the value does not contain a shell or path metacharacter or `..` (`assert ";" not in cmd`, `if ".." in p: raise`). `os.path.commonprefix` is a string prefix and does not count.

**Import aliases** - `import subprocess as sp` and `from os import system` are resolved to their qualified names before schema lookup.

**Function summaries** - a call that the schema does not model, but that resolves to a function of the analysed project, is followed into that function. The engine analyses the callee once per abstract calling context (the properties of each argument) and records which arguments reach which sinks and what the function returns. A tainted argument that reaches `subprocess.run(..., shell=True)` two calls down is reported at the call site, as `run_command→subprocess.Popen`, with the severity a direct call would get; a callee that sanitises or replaces its argument passes that on. Calls are resolved without type inference: functions, classes and imports visible from the call (including relative imports and package re-exports), methods through `self`, `cls` and `super()`, methods of objects built from a project class in the same scope or assigned to `self.x` in the class. Calls on other values stay unresolved. Recursion, chains deeper than 4 calls and more than 400 new summaries per file fall back to the unknown-call rule.

**Functions** - how each function transforms abstract values.
Each entry defines what properties the return value carries and whether calling it produces a capability:
```yaml
functions:
  input:
    returns:
      type: str
      adds: [EXTERNAL_ORIGIN, DYNAMIC, TEXTUAL]   # return value is tainted

  os.system:
    produces_capability: SPAWN_PROCESS             # calling this is recorded
```

**Queries** - what counts as a finding. Each query specifies a capability and the property conditions that must hold on the arguments for a finding to fire:
```yaml
queries:
  spawn_external_command:
    when:
      capability: SPAWN_PROCESS
      argument_has: [EXTERNAL_ORIGIN]   # tainted input reached the command
    severity: critical

  dynamic_execution_constant:
    when:
      capability: INVOKE_DYNAMIC
      argument_has: [CONSTANT]
      argument_lacks: [DYNAMIC, EXTERNAL_ORIGIN]  # literal string, probably safe
    severity: low
```

Severity levels: `info` → `low` → `medium` → `high` → `critical`.

## Usage

```bash
python main.py [PATH...] [OPTIONS]
```

### Examples

```bash
# Analyse all .py files under src/
python main.py src/

# Analyse specific files
python main.py main.py utils.py

# Show 5 worst files and 10 worst metrics
python main.py src/ --depth 5 --metrics 10

# Print score only
python main.py src/ --quiet

# Machine-readable JSON output
python main.py src/ --json

# Disable ANSI colours (for pipes or CI)
python main.py src/ --no-color
```

### Options
 
| Flag | Default | Description |
|---|---|---|
| `-d / --depth N` | 3 | Show N worst-scoring files in the report |
| `-m / --metrics N` | 5 | Show N worst-scoring metrics globally |
| `-q / --quiet` | off | Print final score only |
| `--json` | off | Output full results as JSON |
| `--no-color` | off | Disable ANSI color codes |
| `--max-errors N` | 10 | Abort after N file errors |
| `--ignore PATH...` | none | Skip files or directories |
| `-e / --explain` | off | Show offenders and fix advice per metric |
| `-c / --config FILE` | tool's `pymetricor.yml` | Use a different config file |
| `--version` | | Print the version |

`__init__.py` files are always excluded.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/
```

Every metric has a clean-vs-violation test (`tests/test_metrics.py` fails if a new metric has none), and the reasoning engine, config resolution, score aggregation and pipeline robustness each have their own test module.

## Evaluation

The scripts and results behind the paper (security benchmarks, readability against human ratings, defect prediction, and speed on the top PyPI packages) are in [`evaluation/`](evaluation/README.md). Results for the version the paper evaluates (1.7.0) are in `evaluation/results-v1.7.0/`.
