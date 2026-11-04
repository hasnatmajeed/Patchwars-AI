"""Run Bandit against one generated temporary file without executing its contents."""
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

TEMP_ROOT = Path(__file__).resolve().parents[2] / '.scanner-tmp'
OUTPUT_LIMIT = 2 * 1024 * 1024
TIMEOUT_SECONDS = 30


class ScanError(Exception):
    pass


class ScanTimeout(ScanError):
    pass


def scan_python(data: bytes, timeout: float = TIMEOUT_SECONDS) -> list[dict]:
    try:
        TEMP_ROOT.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='scan-', dir=TEMP_ROOT) as directory:
            source = Path(directory) / 'source.py'
            source.write_bytes(data)
            process = subprocess.Popen(
                [sys.executable, '-m', 'bandit', '-f', 'json', str(source)],
                cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            output = bytearray()

            def read_output() -> None:
                while True:
                    chunk = process.stdout.read(65536)
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > OUTPUT_LIMIT:
                        process.kill()
                        break

            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                reader.join()
                raise ScanTimeout('Scanner timed out.') from None
            reader.join()
            process.stdout.close()
            if len(output) > OUTPUT_LIMIT or process.returncode not in (0, 1):
                raise ScanError('Scanner failed.')
            result = json.loads(output)
            if result.get('errors') or not isinstance(result.get('results'), list):
                raise ScanError('Scanner could not analyze the file.')
            findings = []
            for item in result['results']:
                findings.append({
                    'test_id': item['test_id'], 'severity': item['issue_severity'],
                    'confidence': item['issue_confidence'], 'line_number': item['line_number'],
                    'description': item['issue_text'],
                })
            return findings
    except ScanError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ScanError('Scanner failed.') from exc
