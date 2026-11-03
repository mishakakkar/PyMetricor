# Changelog

## 1.7.0 (2026-11-03)

Taint is tracked through object attributes, and SQL injection, server-side request forgery and template injection are detected.

### Added
- Field-sensitive values: attribute assignments (`self.x = ...`, `obj.x = ...`, two levels deep) are tracked on the variable's abstract value. Constructors return the object with the attributes `__init__` assigned; method summaries take the receiver's attributes and return them (setters). Guards, validators and blacklist checks apply to attributes (`if not is_safe(self.path): abort()`).
- `EXECUTE_QUERY` (CWE-89): `execute`/`executemany`/`executescript`/`raw`/`extra` on any receiver that is not a project class, `sqlalchemy.text`, `RawSQL`, `pandas.read_sql(_query)`. Queries `sql_external_query` (high) and `sql_dynamic_query` (low). SQL quoting helpers (`quote_name`, `escape_string` ...) are validators; `psycopg(2).sql.Identifier`/`Literal` are sanitisers.
- `SEND_REQUEST` (CWE-918): `requests`, `httpx`, `urllib`, `aiohttp`, `urllib3`, `http.client`, `socket.create_connection`, and `get`/`post`/... on client sessions (`http_client` carrier). Queries `ssrf_external_url` (high) and `ssrf_dynamic_url` (low). Response data is external. URL allowlist checks (`url_has_allowed_host_and_scheme` and similar) are guards.
- `RENDER_TEMPLATE` (CWE-1336): templates compiled from source text (Jinja, Flask `render_template_string`, Django, Mako, Tornado; `from_string` except on a sandboxed environment). Queries `template_external_source` (critical) and `template_dynamic_source` (low).
- `sink_args` in function and method specs: only the named arguments are recorded for the capability.
- New security metric `injection_and_request_forgery` (SQL injection and SSRF findings), sensitivity 0.5 like the other security metrics. Security weights are now code execution 0.40, cryptography 0.20, file access 0.20, injection and request forgery 0.20. Template injection counts as code execution.

### Fixed
- `request.args.get(...)` (and other source attributes) on a `request` imported from a framework lost its taint, because the attribute was typed as a module namespace.

## 1.6.0 (not released separately)

Faster security analysis on large, call-heavy projects; every score and finding is unchanged.

### Changed
- Control-flow joins keep bindings that both branches share instead of rebuilding them, and reuse one value for unbound names.
- Call resolution for function summaries is memoised per call node within a file, and the receiver is evaluated only when the resolution binds it.
- Validator name matching is memoised.

## 1.5.0 (not released separately)

Security analysis recognises validation code and covers more sinks.

### Added
- Validators (`validators` in `schema.yml`): a project helper named as a check (`validate_*`, `sanitize_*`, `raise_if_*` and similar) validates its Name arguments when called as a statement, and its result when used as a value.
- `assert` statements refine like the `if` that guards the code after them.
- Blacklist checks (`";" not in cmd`, `if ".." in p: raise`) for shell and path metacharacters; `os.path.commonpath([base, p]) == base` on a normalised path; `re.fullmatch`, anchored `re.match`/`re.search` and `str.isalnum()`-style checks as guards. `not` and `or` in tests are handled (`if a in p or b in p: raise`).
- Sinks: `subprocess.check_output`, `check_call`, `getoutput`, `getstatusoutput`, `os.exec*`, `os.spawn*`, `os.posix_spawn*`, `asyncio.create_subprocess_*`, `pty.spawn`; `shutil.copy2`/`copytree`, `os.rename`/`replace`/`symlink`, `io.open`, `codecs.open`, `FileResponse` (aiohttp, Starlette, FastAPI, Django).
- `methods` in `schema.yml`: sinks on objects of a carrier type, used for pathlib paths (`p.read_text()`, `p.write_bytes()`, `p.unlink()` ...) and tar archives (`extractall`, `extract`).
- `DESERIALIZE` capability (pickle, marshal, shelve, dill, jsonpickle, `pandas.read_pickle`, `yaml.load` without a safe loader, `yaml.unsafe_load`) and `EXTRACT_ARCHIVE` (tar extraction without a member filter, `shutil.unpack_archive`), with their queries. They feed `arbitrary_code_execution` and `unsafe_file_access`.
- `safe_args` on function specs: an argument value that makes the call safe (`Loader=SafeLoader`, `filter="data"`).

### Changed (affects scores)
- A variable holding a sanitised value no longer makes `+` dynamic.
- `/` propagates like `+` (pathlib paths); before, its result was unknown.

## 1.4.0 (not released separately)

Security analysis follows calls across functions and files, and maintainability gains a module coupling metric.

### Added
- Function summaries (`core/reasoning/summaries.py`, `core/reasoning/project.py`): calls to project functions, in the same file or another file of the run, are analysed per abstract calling context; flows from arguments to sinks are reported at the call site and return values carry the callee's effect. Summaries are shared across the files of a run.
- `module_coupling` maintainability metric (weight 0.15; the other six maintainability weights are scaled by 0.85 and rounded): fan-out above 4, fan-in above 12 and load-time import cycles (`core/modules.py`). Thresholds are the 75th (fan-out) and 95th (fan-in) percentiles on the calibration half of the PyPI corpus; sensitivities make the 99th percentile score 50.

### Changed (affects scores)
- The result of a call that propagates its arguments is no longer CONSTANT once any argument is DYNAMIC, as for `+`: `open(os.path.join(BASE, name))` is a dynamic path. Before, the constant `BASE` masked it.
- Projects are analysed with an index of their modules, including `__init__.py` files (which are still not scored).

## 1.3.0 (not released separately)

Readability recalibrated with four new metrics, tuned on the CodeQual development split.

### Added
- `COGNITIVE_COMPLEXITY` and `LINE_DENSITY` (weight .30 each), `IDENTIFIER_QUALITY` and `FORMATTING_CONSISTENCY` (.05 each); the nine earlier readability metrics share the remaining .30.

## 1.2.0

Path-traversal modelling, and size and complexity thresholds calibrated on code. Thresholds were chosen on a 100-package sample of one half of the top-950 PyPI corpus (seed 2026) and checked on the other half: metrics that give more than 90% of held-out files a perfect score fell from 12 to 8. On PySASTBench, file-level F1 rose from .69 to .79.

### Changed (affects scores)
- `max_function_length` 200 -> 50, `max_parameter_bloat` 8 -> 4, `max_inheritance_depth` 5 -> 2, `max_exception_violations` 2 -> 0, `max_class_methods` 18 -> 6, `max_class_attributes` 15 -> 5, `avg_complexity_base` 10 -> 3.
- Nesting depth counts each source line once, at its deepest node; its sensitivity is 1.2 -> 0.4.

### Added
- Schema `guards`: `startswith` on a NORMALIZED path (`normalized_prefix`) and calls named like containment helpers such as `is_safe_path` or `is_relative_to` (`path_containment`) sanitise the tested value.
- Schema `control`: terminator calls (`abort`, `sys.exit`, ...). A branch that always exits no longer flows into the code after it.
- Schema `sources.route_decorators`: parameters of `@app.route`, `@router.get` and similar handlers are external input. New request attributes: `files`, `values`, `cookies`, `headers`, `COOKIES`, `META`, `query_params`, `path_params`.
- File sinks: `flask.send_file`, `os.remove`, `os.unlink`, `os.rmdir`, `shutil.rmtree`, `shutil.copy`, `shutil.copyfile`, `shutil.move`. `os.path.abspath`, `realpath` and `normpath` add NORMALIZED; `werkzeug.utils.secure_filename` is a sanitiser.
- `CITATION.cff` and `.zenodo.json` for citation and archiving.

## 1.1.0

Readability scoring recalibrated against human ratings (CodeQual, 637 human-rated Python samples). Rules were chosen on a dev half and checked once on a held-out half split by problem: within-source Spearman with mean human readability rose from -0.00 to 0.13 for the readability section and from 0.14 to 0.21 for the composite.

### Changed (affects scores)
- `comment_density`: docstring lines now count as documentation, and files no longer than `min_function_size` non-blank lines are not penalised for having no comments. Before, any file without `#` comments scored 0 on this metric.
- Module docstrings are not required for modules shorter than `min_function_size` lines.
- `preferred_line_length` 140 -> 100, `line_length` sensitivity 0.4 -> 0.05.
- `max_feasible_nesting` 7 -> 4, so nesting depth separates ordinary code.

### Fixed
- `if {}:` / `while {...}:` raised `AttributeError` in the dead-code rule and aborted the whole run (2 of 950 top PyPI packages, found by the RQ5 robustness run).
- An unexpected exception inside any stage is now recorded as an error on that file and the run continues, instead of aborting the project.
- Files whose analysis stopped part-way (for example, tokenizable but unparseable code) are left out of the project composite. Before, their missing metrics scored 0 and pulled the project score down.

### Added
- `identifier_length` readability metric (weight 0.12): share of distinct names shorter than `min_identifier_length` (2). Weights of `annotation_consistency` (0.15 -> 0.09) and `string_formatting_consistency` (0.16 -> 0.10) reduced to make room.

## 1.0.1

### Fixed
- Capabilities inside a chained call's receiver were missed: `hashlib.md5(x).hexdigest()`, `os.popen(c).read()`. Found by the security micro-benchmark.
- An empty or whitespace-only docstring on a function long enough to need one raised `IndexError` in the readability visitor and aborted the whole run. Found while scoring the readability-survey snippets.

## 1.0.0

First tagged release, intended as the version cited in the paper.

### Changed (affects scores)
- Security section now has three metrics: `broken_cryptography` 0.25, `arbitrary_code_execution` 0.50, new `unsafe_file_access` 0.25. Filesystem findings were computed before but never scored.
- New `weak_hash_used` query: any MD5/SHA-1 call is a medium finding. Before, only externally tainted input to a weak hash was reported, so `broken_cryptography` almost never fired.
- `filesystem_dynamic_path` severity medium -> low.
- Loops are iterated to a fixed point, so loop-carried taint is found.
- Module receivers (`os.path.join`) no longer make a call's result CONSTANT.
- Import aliases are resolved; sanitiser specs added (`shlex.quote`, `shlex.join`, `os.path.basename`, `int`, `float`).

### Changed (no score impact with shipped config)
- Config is loaded from `--config`, `$PYMETRICOR_CONFIG`, or the tool's own `pymetricor.yml`, never the working directory, and is never written implicitly.
- Built-in defaults now equal the shipped `pymetricor.yml` (the old ones referenced removed metrics and had efficiency weights summing to 0.9).
- External sources (`argv`, `environ`, `request`, ...) moved from code to the `sources` section of `schema.yml`.

### Fixed
- A file with mixed tabs/spaces (TabError) crashed the whole run; it is now a per-file error.

### Added
- `tests/` with 88 tests covering every metric, the reasoning engine, config, scoring and pipeline robustness; CI on Python 3.12 and 3.13.
- Pinned `requirements.txt`, `requirements-dev.txt`, `--version`.
