# My stuff
from core   import __version__, Analyser, S0TokenScan, S1ASTScan, PrintResults, PrintJSON, PrintProgress, SetColorEnabled
from config import Config

# Python stuff
from typing import Callable, List, Optional
import argparse
import sys

# vvv Helper Functions vvv
def _BuildParser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog        = "python main.py",
        description = "PyMetricor - Python code quality analyser",
        formatter_class = argparse.RawDescriptionHelpFormatter,
        epilog = '''
examples:
  python main.py src/                         analyse all .py files under src/
  python main.py dummy.py utils.py            analyse two specific files
  python main.py src/ --depth 5               show 5 worst files
  python main.py src/ --quiet                 print score only
  python main.py src/ --json                  machine-readable JSON output
  python main.py src/ --explain               output explanation for penalties applied
  python main.py src/ --no-color              disable ANSI colors (for pipes)
  python main.py src/ --ignore tests/ docs/   skip tests/ and docs/ directories
  python main.py src/ --config my.yml         use a project-specific configuration
        ''',
    )

    p.add_argument(
        "paths",
        nargs   = "+",
        metavar = "PATH",
        help    = "files or directories to analyse (.py files only, __init__.py excluded)",
    )
    p.add_argument(
        "-d", "--depth",
        type    = int,
        default = 3,
        metavar = "N",
        help    = "show the N worst-scoring files in the report (default: 3)",
    )
    p.add_argument(
        "-gm", "--global-metrics",
        type    = int,
        default = 5,
        metavar = "N",
        help    = "show the N worst-scoring metrics globally (default: 5)",
    )
    p.add_argument(
        "-fm", "--file-metrics",
        type    = int,
        default = 3,
        metavar = "N",
        help    = "show the N worst-scoring metrics per file (default: 3)",
    )
    p.add_argument(
        "-q", "--quiet",
        action  = "store_true",
        help    = "print only the final score (no breakdown)",
    )
    p.add_argument(
        "-e", "--explain",
        action  = "store_true",
        help    = "show why each metric scored poorly (offenders + fix)",
    )
    p.add_argument(
        "--json",
        action  = "store_true",
        help    = "output full results as JSON (suppresses all other output)",
    )
    p.add_argument(
        "--no-color",
        action  = "store_true",
        help    = "disable ANSI color codes (auto-disabled when not a TTY)",
    )
    p.add_argument(
        "--max-errors",
        type    = int,
        default = 10,
        metavar = "N",
        help    = "abort analysis after N file errors (default: 10)",
    )
    p.add_argument(
        "--version",
        action  = "version",
        version = f"PyMetricor {__version__}",
    )
    p.add_argument(
        "-c", "--config",
        default = None,
        metavar = "FILE",
        help    = "config file to use (default: $PYMETRICOR_CONFIG, else pymetricor.yml next to main.py)",
    )
    p.add_argument(
        "--ignore",
        nargs   = "+",
        default = [],
        metavar = "PATH",
        help    = "files or directories to exclude from analysis (supports partial path matching)",
    )

    return p

# vvv Main Function vvv
def Main(argv: List[str] = sys.argv[1:]) -> int:
    parser: argparse.ArgumentParser = _BuildParser()
    args: argparse.Namespace = parser.parse_args(argv)

    # Auto-disable color when stdout is not a TTY or --no-color is set
    use_color: bool = not args.no_color and sys.stdout.isatty()
    SetColorEnabled(use_color)

    global_config: Config = Config(args.config)

    # Build section info from config (order must match Section enum)
    section_weights: List[float] = [
        global_config.metrics.weights.sections.readability,
        global_config.metrics.weights.sections.efficiency,
        global_config.metrics.weights.sections.maintainability,
        global_config.metrics.weights.sections.security,
    ]
    section_names: List[str] = [
        "Readability",
        "Efficiency",
        "Maintainability",
        "Security",
    ]

    # Progress callback - suppressed in quiet/json modes or non-TTY stderr
    progress_cb: Optional[Callable[[int, int, str], None]] = None
    if not args.quiet and not args.json and sys.stderr.isatty():
        progress_cb = PrintProgress

    analyser: Analyser = Analyser([S0TokenScan(), S1ASTScan()], max_file_errors=args.max_errors)
    ctx, has_errors = analyser.Run(args.paths, ignore_paths=args.ignore, progress_callback=progress_cb)

    if ctx.aborted_analysis and not args.json:
        print("[PyMetricor]: Analysis aborted", file=sys.stderr)
        if has_errors:
            ctx.PrettyPrintErrors()

        return 1

    final_score: float = ctx.ComputeFinalScore(section_weights)

    # Output modes
    if args.json:
        PrintJSON(ctx, final_score, section_weights, section_names)

    elif args.quiet:
        print(f"{final_score:.2f}")

    else:
        PrintResults(
            ctx,
            final_score,
            section_weights,
            section_names,
            depth         = max(1, args.depth),
            top_metrics   = max(1, args.global_metrics),
            worst_metrics = max(1, args.file_metrics),
            explain       = args.explain,
        )
        if has_errors:
            ctx.PrettyPrintErrors()

    return 1 if has_errors else 0

# Driver
if __name__ == "__main__":
    sys.exit(Main())