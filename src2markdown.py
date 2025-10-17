from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence

from pathspec import PathSpec


DEFAULT_SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".csx",
    ".cxx",
    ".go",
    ".h",
    ".hh",
    ".hpp",
    ".hs",
    ".java",
    ".jl",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".m",
    ".mm",
    ".php",
    ".pl",
    ".ps1",
    ".py",
    ".r",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".vue",
    ".yaml",
    ".yml",
    ".zig",
}

DEFAULT_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".venv",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "target",
    "venv",
}

DEFAULT_IGNORED_FILES = {
    ".DS_Store",
}

LANGUAGE_HINTS = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".csx": "csharp",
    ".cxx": "cpp",
    ".go": "go",
    ".h": "c",
    ".hh": "cpp",
    ".hpp": "cpp",
    ".hs": "haskell",
    ".java": "java",
    ".jl": "julia",
    ".js": "javascript",
    ".json": "json",
    ".jsx": "jsx",
    ".kt": "kotlin",
    ".m": "objectivec",
    ".mm": "objectivec",
    ".php": "php",
    ".pl": "perl",
    ".ps1": "powershell",
    ".py": "python",
    ".r": "r",
    ".rb": "ruby",
    ".rs": "rust",
    ".scala": "scala",
    ".sh": "bash",
    ".sql": "sql",
    ".swift": "swift",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".vue": "vue",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".zig": "zig",
}

TOP_ANCHOR = "document-top"
TOC_ANCHOR = "table-of-contents"
BACK_LINK = f"[Back to Top](#{TOP_ANCHOR}) • [Back to TOC](#{TOC_ANCHOR})"


@dataclass
class TreeNode:
    """Representation of a directory or file in the aggregation tree."""

    path: Path
    is_dir: bool
    depth: int
    children: List["TreeNode"] = field(default_factory=list)
    anchor: str | None = None
    heading_text: str | None = None
    is_markdown: bool = False


class AnchorRegistry:
    """Generates unique anchor slugs in a GitHub-compatible manner."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def register(self, heading_text: str) -> str:
        slug = _slugify(heading_text)
        count = self._counts.get(slug, 0)
        final_slug = slug if count == 0 else f"{slug}-{count}"
        self._counts[slug] = count + 1
        return final_slug


def aggregate_directory(
    input_dir: Path,
    output_file: Path,
    *,
    title: str | None = None,
    include_extensions: Iterable[str] | None = None,
    ignored_dirs: Iterable[str] | None = None,
    ignored_files: Iterable[str] | None = None,
    ignore_patterns: Sequence[str] | None = None,
    follow_symlinks: bool = False,
) -> None:
    """Aggregate source code and Markdown files into a single Markdown document."""
    input_dir = input_dir.resolve()
    output_file = output_file.resolve()

    if not input_dir.is_dir():
        raise ValueError(f"Input path is not a directory: {input_dir}")

    extensions = {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in (
        include_extensions or DEFAULT_SOURCE_EXTENSIONS
    )}

    ignored_dir_names = set(DEFAULT_IGNORED_DIRS)
    if ignored_dirs:
        ignored_dir_names.update(ignored_dirs)
    ignored_file_names = set(DEFAULT_IGNORED_FILES)
    if ignored_files:
        ignored_file_names.update(ignored_files)

    ignore_spec = (
        PathSpec.from_lines("gitwildmatch", ignore_patterns)
        if ignore_patterns
        else None
    )

    root_node = _build_tree(
        input_dir,
        root_path=input_dir,
        depth=0,
        extensions=extensions,
        ignored_dirs=ignored_dir_names,
        ignored_files=ignored_file_names,
        follow_symlinks=follow_symlinks,
        output_path=output_file,
        ignore_spec=ignore_spec,
    )

    if root_node is None or not root_node.children:
        raise ValueError(f"No matching files found under {input_dir}")

    title_text = title or f"{input_dir.name} Source Archive"
    registry = AnchorRegistry()

    _assign_headings(root_node, registry, root_path=input_dir)

    content_lines = _render_document(
        root_node,
        root_path=input_dir,
        title=title_text,
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n".join(content_lines) + "\n", encoding="utf-8")


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate all source code and Markdown files under a directory into a single Markdown file."
        )
    )
    parser.add_argument("input_dir", type=Path, help="Directory to scan for source and Markdown files.")
    parser.add_argument(
        "output_file",
        nargs="?",
        type=Path,
        default=None,
        help="Destination Markdown file. Defaults to '<input_dir>.md'.",
    )
    parser.add_argument(
        "--title",
        help="Optional title for the aggregated document. Defaults to '<input_dir.name> Source Archive'.",
    )
    parser.add_argument(
        "--extensions",
        nargs="*",
        help="Overrides the default list of source file extensions (space separated list).",
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="Follow directory symlinks while walking the tree.",
    )
    parser.add_argument(
        "--ignore-dir",
        dest="ignore_dirs",
        action="append",
        default=[],
        help="Additional directory name to ignore (can be provided multiple times).",
    )
    parser.add_argument(
        "--ignore-file",
        dest="ignore_files",
        action="append",
        default=[],
        help="Additional file name to ignore (can be provided multiple times).",
    )
    parser.add_argument(
        "--ignore",
        dest="ignore_patterns",
        action="append",
        nargs="+",
        default=[],
        help="Gitignore-style pattern(s) to exclude; provide one or more per flag.",
    )
    return parser


def _build_tree(
    root: Path,
    *,
    root_path: Path,
    depth: int,
    extensions: set[str],
    ignored_dirs: set[str],
    ignored_files: set[str],
    follow_symlinks: bool,
    output_path: Path,
    ignore_spec: PathSpec | None,
) -> TreeNode | None:
    resolved = root.resolve()

    if resolved == output_path:
        return None

    if root.is_symlink() and not follow_symlinks:
        return None

    if not root.exists():
        return None

    is_dir = root.is_dir()

    if ignore_spec and root != root_path:
        relative = root.relative_to(root_path).as_posix()
        if ignore_spec.match_file(relative) or (is_dir and ignore_spec.match_file(f"{relative}/")):
            return None

    if root.is_file():
        suffix = root.suffix.lower()
        if suffix == ".md" or suffix in extensions:
            return TreeNode(
                path=root,
                is_dir=False,
                depth=depth,
                is_markdown=(suffix == ".md"),
            )
        return None

    children: List[TreeNode] = []

    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except PermissionError:
        return None

    for entry in entries:
        if entry.is_dir():
            if entry.name in ignored_dirs or entry.name.startswith("."):
                continue
            child = _build_tree(
                entry,
                root_path=root_path,
                depth=depth + 1,
                extensions=extensions,
                ignored_dirs=ignored_dirs,
                ignored_files=ignored_files,
                follow_symlinks=follow_symlinks,
                output_path=output_path,
                ignore_spec=ignore_spec,
            )
            if child is not None:
                children.append(child)
        elif entry.is_file():
            if entry.name in ignored_files or entry.name.startswith("."):
                continue
            child = _build_tree(
                entry,
                root_path=root_path,
                depth=depth + 1,
                extensions=extensions,
                ignored_dirs=ignored_dirs,
                ignored_files=ignored_files,
                follow_symlinks=follow_symlinks,
                output_path=output_path,
                ignore_spec=ignore_spec,
            )
            if child is not None:
                children.append(child)

    if not children:
        return None

    return TreeNode(path=root, is_dir=True, depth=depth, children=children)


def _assign_headings(node: TreeNode, registry: AnchorRegistry, *, root_path: Path) -> None:
    if node.depth > 0:
        relative = node.path.relative_to(root_path).as_posix()
        heading_text = f"{relative}/" if node.is_dir else relative
        node.heading_text = heading_text
        node.anchor = registry.register(heading_text)

    for child in node.children:
        _assign_headings(child, registry, root_path=root_path)


def _build_toc(node: TreeNode) -> List[str]:
    lines: List[str] = []
    for child in node.children:
        if child.anchor and child.heading_text:
            indent = "  " * max(child.depth - 1, 0)
            lines.append(f"{indent}- [{child.heading_text}](#{child.anchor})")
        if child.is_dir:
            lines.extend(_build_toc(child))
    return lines


def _render_document(
    root_node: TreeNode,
    *,
    root_path: Path,
    title: str,
) -> List[str]:
    lines: List[str] = []
    lines.append(f"# {title}")
    lines.append(f"<a id=\"{TOP_ANCHOR}\"></a>")
    lines.append("")

    toc_lines = _build_toc(root_node)
    if toc_lines:
        lines.append("## Table of Contents")
        lines.append(f"<a id=\"{TOC_ANCHOR}\"></a>")
        lines.append("")
        lines.extend(toc_lines)
        lines.append("")

    for child in root_node.children:
        lines.extend(_render_node(child, root_path=root_path))

    return lines


def _render_node(node: TreeNode, *, root_path: Path) -> List[str]:
    lines: List[str] = []
    level = min(node.depth + 1, 6)
    if node.heading_text and node.anchor:
        lines.append(f"{'#' * level} {node.heading_text}")
        lines.append(f"<a id=\"{node.anchor}\"></a>")
    elif node.heading_text:
        lines.append(f"{'#' * level} {node.heading_text}")
    lines.append("")

    if node.is_dir:
        for child in node.children:
            lines.extend(_render_node(child, root_path=root_path))
        return lines

    relative = node.path.relative_to(root_path).as_posix()
    if node.is_markdown:
        lines.append(f"<!-- Begin {relative} -->")
        content = node.path.read_text(encoding="utf-8", errors="replace")
        stripped = content.rstrip("\n")
        if stripped:
            lines.append(stripped)
        lines.append(f"<!-- End {relative} -->")
        lines.append(BACK_LINK)
        lines.append("")
        return lines

    language = LANGUAGE_HINTS.get(node.path.suffix.lower(), "")
    lines.append(f"```{language}".rstrip())
    content = node.path.read_text(encoding="utf-8", errors="replace")
    lines.append(content.rstrip("\n"))
    lines.append("```")
    lines.append(BACK_LINK)
    lines.append("")
    return lines


def _slugify(text: str) -> str:
    slug = text.strip().lower()
    slug = slug.replace("/", " ")
    slug = re.sub(r"[^\w\- ]+", "", slug)
    slug = slug.replace("_", " ")
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_cli_parser()
    args = parser.parse_args(argv)

    extensions = args.extensions if args.extensions else None
    ignore_dirs = set(DEFAULT_IGNORED_DIRS).union(args.ignore_dirs or [])
    ignore_files = set(DEFAULT_IGNORED_FILES).union(args.ignore_files or [])
    ignore_patterns = (
        [pattern for group in args.ignore_patterns for pattern in group]
        if args.ignore_patterns
        else None
    )

    input_dir: Path = args.input_dir
    if args.output_file is not None:
        output_file: Path = args.output_file
    else:
        resolved_input = input_dir.resolve()
        output_file = resolved_input.with_name(f"{resolved_input.name}.md")

    aggregate_directory(
        input_dir,
        output_file,
        title=args.title,
        include_extensions=extensions,
        ignored_dirs=ignore_dirs,
        ignored_files=ignore_files,
        ignore_patterns=ignore_patterns,
        follow_symlinks=args.follow_symlinks,
    )
    return 0


__all__ = [
    "aggregate_directory",
    "build_cli_parser",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
