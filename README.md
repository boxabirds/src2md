# src2md

Utility script that renders a source tree into Markdown so the contents can be inspected or shared more easily.

## Prerequisites

- Python 3.11+ (or whatever version your `uv` is configured to manage)
- [uv](https://github.com/astral-sh/uv) for running the script in an isolated environment

## Basic usage

```bash
uv run python src2markdown.py <path-to-project> [options]
```

The script walks the target directory, converts supported source files to Markdown, and writes them to standard output. Pass `--help` for the full list of arguments.

## Example

```bash
uv run python src2markdown.py ../rusty-waves-project/rusty-waves-dsp \
  --ignore "*.d.ts" "docs/delivery" "docs/pocs" "docs/reviews" \
  "tests" "benches" "pkg-web" "pkg-node" ".github" ".cargo" "examples"
```

The example above renders the Rusty Waves DSP project while ignoring TypeScript declaration files and several documentation, test, and packaging directories.

## Tips

- Combine multiple `--ignore` patterns to skip noisy directories or generated assets.
- Redirect the output to a file if you want to archive the Markdown snapshot.
