import pytest

from backend.app.ai_agents import MAX_SOURCE_BYTES
from backend.app.verification import verify_patch


def finding(test_id, line):
    return {'test_id': test_id, 'line_number': line, 'description': test_id,
            'severity': 'MEDIUM', 'confidence': 'HIGH'}


def test_valid_reduction_and_change_statistics():
    result = verify_patch('eval(input())\n', 'value = input()\n', [finding('B307', 1)], [])
    assert result['syntax_valid'] is True and result['code_changed'] is True
    assert result['verification_status'] == 'static_improvement'
    assert result['original_finding_count'] == 1 and result['proposed_finding_count'] == 0
    assert result['remaining_findings'] == [] and result['introduced_findings'] == []
    assert result['change_summary'] == {'original_lines': 1, 'proposed_lines': 1,
                                        'lines_added': 1, 'lines_removed': 1}
    assert result['manual_review_required'] is True


@pytest.mark.parametrize('patch', ['', '   ', 'if:', 'x' * (MAX_SOURCE_BYTES + 1), '\x00'])
def test_invalid_patches(patch):
    result = verify_patch('x = 1', patch, [], None)
    assert result['verification_status'] == 'invalid_patch'
    assert result['syntax_valid'] is not True
    assert result['proposed_finding_count'] is None


def test_unchanged_and_finding_multiplicity():
    item = finding('B307', 1)
    result = verify_patch('eval(input())', 'eval(input())', [item], [item, item])
    assert result['code_changed'] is False
    assert result['remaining_findings'] == [item] and result['introduced_findings'] == [item]
    assert result['verification_status'] == 'no_static_improvement'


def test_introduced_finding_precludes_improvement_even_when_count_drops():
    old = [finding('B307', 1), finding('B308', 2)]
    new = [finding('B999', 3)]
    result = verify_patch('a = 1', 'a = 2', old, new)
    assert result['introduced_findings'] == new
    assert result['verification_status'] == 'no_static_improvement'


def test_insertions_do_not_report_displaced_findings_as_new():
    target, existing, displaced = finding('B307', 1), finding('B101', 2), finding('B101', 3)
    report = verify_patch('value = eval(text)\nassert value\n',
                          'import ast\nvalue = ast.literal_eval(text)\nassert value\n',
                          [target, existing], [displaced], target)
    assert report['remaining_findings'] == [displaced]
    assert report['introduced_findings'] == []
    assert report['verification_status'] == 'static_improvement'


@pytest.mark.parametrize('before,after', [(None, []), ([], None), (None, None)])
def test_unavailable_scan_is_incomplete(before, after):
    result = verify_patch('x = 1', 'x = 2', before, after)
    assert result['syntax_valid'] is True
    assert result['verification_status'] == 'verification_incomplete'
    assert result['remaining_findings'] is None and result['introduced_findings'] is None


def test_source_is_never_executed(tmp_path):
    marker = tmp_path / 'marker'
    code = f"open({str(marker)!r}, 'w').write('executed')\n"
    result = verify_patch('pass\n', code, [], [])
    assert result['syntax_valid'] is True
    assert not marker.exists()


def test_target_rule_and_unrelated_changes_are_reported_conservatively():
    original = 'x = 1\nvalue = eval(text)\ny = 1\n'
    target = finding('B307', 2)
    patch = 'x = 1\nvalue = eval(text)\ny = 2\n'
    result = verify_patch(original, patch, [target], [target], target=target)
    assert result['target_rule_still_reported'] is True
    assert result['unrelated_change_possible'] is True
    assert result['verification_status'] != 'static_improvement'
    fixed = verify_patch(original, 'x = 1\nvalue = int(text)\ny = 1\n', [target], [], target=target)
    assert fixed['target_rule_still_reported'] is False
    assert fixed['unrelated_change_possible'] is False
