"""Bounded, static comparison of a proposed Python file; never executes it."""
import ast
from collections import Counter
from difflib import SequenceMatcher
from typing import Any

from .ai_agents import MAX_SOURCE_BYTES


def code_structure(source: str) -> str:
    """Compare Python structure without whitespace, comments or source positions."""
    try:
        return ast.dump(ast.parse(source, type_comments=True), include_attributes=False)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return source


def verify_patch(original: str, proposed: str, original_findings: list[dict[str, Any]] | None,
                 proposed_findings: list[dict[str, Any]] | None,
                 target: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compare existing scanner results; None means that scan was unavailable."""
    changed = original != proposed
    report: dict[str, Any] = {
        'syntax_valid': None, 'code_changed': changed,
        'original_finding_count': len(original_findings) if original_findings is not None else None,
        'proposed_finding_count': len(proposed_findings) if proposed_findings is not None else None,
        'remaining_findings': None, 'introduced_findings': None,
        'change_summary': None, 'verification_status': 'invalid_patch',
        'target_rule_still_reported': None, 'unrelated_change_possible': None,
        'manual_review_required': True,
    }
    try:
        proposed_bytes = proposed.encode('utf-8')
        original_bytes = original.encode('utf-8')
    except UnicodeError:
        return report
    if len(original_bytes) > MAX_SOURCE_BYTES:
        report['verification_status'] = 'verification_incomplete'
        return report
    if not proposed.strip() or len(proposed_bytes) > MAX_SOURCE_BYTES or '\x00' in proposed:
        return report
    old_lines = Counter(original.splitlines())
    new_lines = Counter(proposed.splitlines())
    report['change_summary'] = {
        'original_lines': sum(old_lines.values()), 'proposed_lines': sum(new_lines.values()),
        'lines_added': sum((new_lines - old_lines).values()),
        'lines_removed': sum((old_lines - new_lines).values()),
    }
    try:
        proposed_tree = ast.parse(proposed)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        report['syntax_valid'] = False
        return report
    report['syntax_valid'] = True
    changed = changed and code_structure(original) != code_structure(proposed)
    report['code_changed'] = changed
    if target is not None:
        try:
            old_tree = ast.parse(original)
            line = target.get('line_number')
            index = next(i for i, node in enumerate(old_tree.body) if node.lineno <= line <= (node.end_lineno or node.lineno))
            old_nodes = [ast.dump(node, include_attributes=False) for node in old_tree.body]
            new_nodes = [ast.dump(node, include_attributes=False) for node in proposed_tree.body]
            if len(old_nodes) + len(new_nodes) > 400:
                raise ValueError('Structural comparison limit')
            changes = SequenceMatcher(None, old_nodes, new_nodes, autojunk=False).get_opcodes()
            report['unrelated_change_possible'] = any(tag != 'equal' and
                (not (i1 <= index < i2 and i2 - i1 == 1) if tag != 'insert' else i1 not in (index, index + 1))
                for tag, i1, i2, _, _ in changes)
        except (SyntaxError, StopIteration, TypeError, ValueError, RecursionError, MemoryError):
            report['unrelated_change_possible'] = None
    if original_findings is None or proposed_findings is None:
        report['verification_status'] = 'verification_incomplete'
        return report

    def identity(finding: dict[str, Any]) -> tuple[Any, ...]:
        return (finding['test_id'], finding['line_number'], finding['description'])

    line_matches = SequenceMatcher(None, original.splitlines(), proposed.splitlines()).get_matching_blocks()
    old_lines_by_new = {new + offset + 1: old + offset + 1
                        for old, new, size in line_matches for offset in range(size)}
    available = Counter(identity(f) for f in original_findings)
    remaining, introduced = [], []
    for finding in proposed_findings:
        rule, line, description = identity(finding)
        key = rule, old_lines_by_new.get(line, line), description
        if available[key]:
            remaining.append(finding)
            available[key] -= 1
        else:
            introduced.append(finding)
    report['remaining_findings'], report['introduced_findings'] = remaining, introduced
    if target is not None and target.get('test_id'):
        # Rule IDs may occur at multiple locations; this conservative check does not prove a fix.
        report['target_rule_still_reported'] = any(f.get('test_id') == target['test_id'] for f in proposed_findings)
    report['verification_status'] = (
        'static_improvement' if changed and len(proposed_findings) < len(original_findings)
        and not introduced and report['target_rule_still_reported'] is not True
        and report['unrelated_change_possible'] is not True else 'no_static_improvement'
    )
    return report
