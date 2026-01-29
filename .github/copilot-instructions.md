# Copilot instructions

## Project overview
- Single-file Python CLI that converts tool diagnostics into CI/CD annotation formats. Core types and adapters live in [../ci_annotation_converter.py](../ci_annotation_converter.py).
- Data flow: input JSON/text → `InputAdapter.from_file()` → `AnnotationItem` list → `OutputAdapter.to_file()` → formatted output.

## Key architecture/patterns
- Adapter registry pattern: `InputAdapter`/`OutputAdapter` subclasses register via `id` in `registry` using `__init_subclass__`. Add new formats by defining a subclass with `id`, `schema` (input only), and `severity_map`.
- `AnnotationItem` is immutable (`@dataclass(frozen=True)`) and computes a `fingerprint` in `__post_init__`. Some adapters (e.g., `TyAdapter`) override the fingerprint after creation.
- Severity filtering is centralized in output adapters: only `Severity.WARN` and above are emitted (see `GitHubJsonAdapter.to_file()` and `GitHubTextAdapter.to_file()`).

## Conventions & gotchas
- Inputs are validated with the `schema` library (`import schema as s`). Keep schema validation aligned with upstream tool output keys.
- Line/column indexing varies by tool: some inputs are 0-based and are adjusted to 1-based (see `PyrightAdapter` and `MypyAdapter`). Preserve these offsets when adding new adapters.
- GitHub text output uses command-escaped formatting and explicitly escapes Windows backslashes in file paths (see `GitHubTextAdapter.to_file()`).

## Developer workflows
- CLI entrypoint: `main()` parses args (`INPUT_FORMAT`, `OUTPUT_FORMAT`, `-i/-o`, `-e`). Formats are discovered dynamically from adapter registries.
- The script reads from stdin/stdout when files are omitted; avoid adding behavior that assumes file paths.

## Extending the project
- To add a new input format, implement `InputAdapter.from_file()` and map severities to `Severity`.
- To add a new output format, implement `OutputAdapter.to_file()` and ensure required CI format fields are set.
- Keep changes localized to [../ci_annotation_converter.py](../ci_annotation_converter.py); there are no package modules or tests yet.
