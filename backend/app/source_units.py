"""Bounded, non-executing notebook parsing and finding-focused Python scopes."""
import ast
import json
import textwrap
import io
import ijson
from typing import Any

MAX_CELLS = 200
MAX_CONTEXT_BYTES = 6000
MAX_PREVIEW_BYTES = 256 * 1024


class SourceError(ValueError):
    pass


def reconstruct_source(full: str, original: str, replacement: str, start: int, end: int) -> str:
    """Validate a line mapping and both Python units without executing either."""
    lines = full.splitlines(keepends=True)
    if not 1 <= start <= end <= len(lines):
        raise SourceError('The original source mapping is unavailable.')
    region = ''.join(lines[start - 1:end])
    if textwrap.dedent(region) != original:
        raise SourceError('The original source does not match the reviewed region.')
    try:
        ast.parse(replacement)
        indentation = region[:len(region) - len(region.lstrip(' \t'))]
        replacement = textwrap.indent(replacement, indentation)
        if region.endswith(('\n', '\r')) and not replacement.endswith(('\n', '\r')):
            replacement += '\r\n' if region.endswith('\r\n') else '\n'
        result = ''.join(lines[:start - 1]) + replacement + ''.join(lines[end:])
        ast.parse(result)
        compile(result, '<review>', 'exec', dont_inherit=True)
        return result
    except (SyntaxError, ValueError, TypeError, RecursionError, MemoryError):
        raise SourceError('The replacement or reconstructed source is invalid Python.') from None


def notebook_cells(data, max_source_bytes: int = 8 * 1024 * 1024) -> list[dict[str, Any]]:
    """Parse one notebook incrementally; retain only bounded code-cell sources.

    ijson validates the complete document. Individual JSON scalar values can still
    occupy memory up to the notebook upload limit; never build output/metadata trees.
    """
    stream = io.BytesIO(data) if isinstance(data, bytes) else data
    stream.seek(0)
    cells: list[dict[str, Any]] = []
    current = None
    root_seen = cells_seen = False
    language = kernel_language = None
    retained = 0
    depth = events = 0
    try:
        for prefix, event, value in ijson.parse(stream, buf_size=1024 * 1024):
            events += 1
            if events > 1000000:
                raise SourceError('Notebook exceeds the JSON event budget.')
            if event in ('start_map', 'start_array'):
                depth += 1
                if depth > 128:
                    raise SourceError('Notebook JSON nesting is too deep.')
            elif event in ('end_map', 'end_array'):
                depth -= 1
            if prefix == '' and event == 'start_map':
                root_seen = True
            if prefix == 'cells' and event == 'start_array':
                if cells_seen:
                    raise SourceError('Duplicate notebook cells field.')
                cells_seen = True
            elif prefix == 'cells' and event not in ('end_array', 'start_array'):
                raise SourceError('Notebook cells must be an array.')
            if prefix == 'metadata.language_info.name' and event == 'string':
                language = value
            elif prefix == 'metadata.kernelspec.language' and event == 'string':
                kernel_language = value
            if prefix == 'cells.item' and event == 'start_map':
                if len(cells) >= MAX_CELLS:
                    raise SourceError('Notebook exceeds the 200-cell limit.')
                current = {'cell_index': len(cells), 'cell_type': None, 'parts': [],
                           'source_seen': False, 'source_array': False, 'oversized': False, 'bytes': 0}
                cells.append(current)
            elif prefix == 'cells.item' and event not in ('end_map', 'start_map', 'map_key'):
                raise SourceError('Notebook cells must be objects.')
            elif current is not None and prefix == 'cells.item.cell_type':
                if event != 'string' or current['cell_type'] is not None:
                    raise SourceError('Invalid notebook cell type.')
                current['cell_type'] = value
            elif current is not None and prefix == 'cells.item.source':
                if event == 'end_array':
                    continue
                if current['source_seen']:
                    raise SourceError('Invalid notebook cell source.')
                current['source_seen'] = True
                if event == 'start_array':
                    current['source_array'] = True
                elif event == 'string':
                    encoded_size = len(value.encode('utf-8'))
                    if encoded_size + retained > max_source_bytes:
                        current['oversized'] = True
                    else:
                        current['parts'].append(value)
                        current['bytes'] += encoded_size
                        retained += encoded_size
                else:
                    raise SourceError('Invalid notebook cell source.')
            elif current is not None and prefix == 'cells.item.source.item':
                if event != 'string' or not current['source_array']:
                    raise SourceError('Invalid notebook cell source.')
                encoded_size = len(value.encode('utf-8'))
                if current['oversized'] or len(current['parts']) >= 100000 or encoded_size + retained > max_source_bytes:
                    if not current['oversized']:
                        retained -= current['bytes']
                        current['parts'].clear()
                        current['oversized'] = True
                else:
                    current['parts'].append(value)
                    current['bytes'] += encoded_size
                    retained += encoded_size
        if not root_seen or not cells_seen:
            raise SourceError('Notebook is not valid bounded UTF-8 notebook JSON.')
        output = []
        for cell in cells:
            if cell['cell_type'] is None:
                raise SourceError('Invalid notebook cell type.')
            if cell['cell_type'] != 'code':
                continue
            source = ''.join(cell['parts'])
            reason = None
            if cell['oversized']:
                reason = 'Cell source exceeds the notebook analysis byte budget.'
            elif (language or kernel_language or 'python').lower() not in ('python', 'python3'):
                reason = 'Notebook kernel is not Python.'
            elif any(line.lstrip().startswith(('%', '!', '?')) for line in source.splitlines()):
                reason = 'Notebook magic or shell syntax is not analyzed.'
            elif not source.strip():
                reason = 'Empty code cell.'
            else:
                try:
                    ast.parse(source)
                except (SyntaxError, ValueError, RecursionError, MemoryError):
                    reason = 'Cell is not valid standalone Python.'
            output.append({'cell_index': cell['cell_index'], 'source': source, 'reason': reason})
        return output
    except SourceError:
        raise
    except (ijson.JSONError, UnicodeError, ValueError, TypeError, OverflowError, RecursionError, MemoryError):
        raise SourceError('Notebook is not valid bounded UTF-8 notebook JSON.') from None


def finding_scope(source: str, line: int, include_import_usage: bool = False) -> tuple[str, int, int]:
    """Return a complete enclosing definition or top-level statement, never a cut fragment."""
    lines = source.splitlines(keepends=True)
    if line < 1 or line > len(lines):
        raise SourceError('Selected finding line is outside the source.')
    try:
        tree = ast.parse(source)
        nodes = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                 and node.lineno <= line <= (node.end_lineno or node.lineno)]
        if nodes:
            # Preserve the enclosing class/function context when possible. Do not
            # silently discard an oversized enclosing definition.
            node = max(nodes, key=lambda item: (item.end_lineno or item.lineno) - item.lineno)
        else:
            node = next((item for item in tree.body if item.lineno <= line <= (item.end_lineno or item.lineno)), None)
        if node is None:
            raise SourceError('No complete Python region contains the selected finding.')
        if include_import_usage:
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                raise SourceError('More code context is needed for this import finding.')
            names = {alias.asname or (alias.name.split('.')[0] if isinstance(node, ast.Import) else alias.name)
                     for alias in node.names if alias.name != '*'}
            usage = next((top for top in tree.body if top is not node and any(
                isinstance(call, ast.Call) and any(isinstance(part, ast.Name) and part.id in names
                                                  for part in ast.walk(call.func))
                for call in ast.walk(top))), None)
            if usage is None:
                raise SourceError('More code context is needed: no related import call was found.')
            start = min(node.lineno, usage.lineno)
            end = max(node.end_lineno or node.lineno, usage.end_lineno or usage.lineno)
            context = ''.join(lines[start - 1:end])
            if len(context.encode('utf-8')) > MAX_CONTEXT_BYTES:
                raise SourceError('More code context is needed: the import and its use exceed the 6000-byte AI context limit.')
            ast.parse(context)
            return context, start, end
        decorators = getattr(node, 'decorator_list', [])
        start = min([node.lineno] + [item.lineno for item in decorators])
        end = node.end_lineno or node.lineno
        context = textwrap.dedent(''.join(lines[start - 1:end]))
        if len(context.encode('utf-8')) > MAX_CONTEXT_BYTES:
            raise SourceError('The enclosing code region exceeds the 6000-byte AI context limit; choose a finding in a smaller definition.')
        ast.parse(context)
        return context, start, end
    except SourceError:
        raise
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        raise SourceError('Could not safely derive a complete Python region for this finding.') from None
