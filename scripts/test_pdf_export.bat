@echo off
setlocal
set "NOC_PDF_TEST_ROOT=%~dp0"
if not exist "%NOC_PDF_TEST_ROOT%run.py" set "NOC_PDF_TEST_ROOT=%~dp0..\"
if not exist "%NOC_PDF_TEST_ROOT%run.py" (
    echo Copy this file into the dashboard project folder next to run.py.
    pause
    exit /b 1
)
if not exist "%NOC_PDF_TEST_ROOT%.venv\Scripts\python.exe" (
    echo Project Python was not found. Create the project .venv first.
    pause
    exit /b 1
)
set "NOC_PDF_TEST_LAUNCHER=%~f0"
echo PDF export test - application settings and saved reports stay unchanged.
echo Hidden Word is tested first. Word may appear during the visible comparison.
echo Five report samples are tested in both modes. Each export has a 45-second limit. This may take a few minutes.
echo.
powershell -NoProfile -Command "$testTempPath = Join-Path ([IO.Path]::GetTempPath()) ('noc-pdf-test-' + [guid]::NewGuid().ToString('N') + '.py'); $testExitCode = 1; try { $launcherText = [IO.File]::ReadAllText($env:NOC_PDF_TEST_LAUNCHER); $testPayload = ($launcherText -split '(?m)^::PYTHON_PAYLOAD\r?$', 2)[1]; [IO.File]::WriteAllText($testTempPath, $testPayload, (New-Object Text.UTF8Encoding($false))); & (Join-Path $env:NOC_PDF_TEST_ROOT '.venv\Scripts\python.exe') $testTempPath --timeout 45; $testExitCode = $LASTEXITCODE } finally { if (Test-Path -LiteralPath $testTempPath) { Remove-Item -LiteralPath $testTempPath } }; exit $testExitCode"
set "NOC_PDF_TEST_EXIT=%ERRORLEVEL%"
echo.
echo Read hidden_all_passed in the summary above. This test does not enable hidden mode.
if /I not "%~1"=="--no-pause" pause
exit /b %NOC_PDF_TEST_EXIT%
::PYTHON_PAYLOAD
"""Compare hidden and visible Word PDF exports without changing application settings."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(os.environ['NOC_PDF_TEST_ROOT']).resolve()
sys.path.insert(0, str(ROOT))


def tagged_processes(tag):
    import win32gui
    import win32process

    found = set()

    def inspect(window, _):
        if tag in win32gui.GetWindowText(window):
            found.add(win32process.GetWindowThreadProcessId(window)[1])

    win32gui.EnumWindows(inspect, None)
    return found


def stop_tagged_word(tag):
    import win32api
    import win32process

    for pid in tagged_processes(tag):
        handle = win32api.OpenProcess(0x1000 | 0x0001, False, pid)
        try:
            if Path(win32process.GetProcessImageFileName(handle)).name.lower() == 'winword.exe':
                win32api.TerminateProcess(handle, 1)
        finally:
            handle.Close()


def child(mode, folder, tag):
    import pythoncom
    from app.services import word_export

    def isolated_word(win32, com):
        cached = getattr(word_export._thread_local, 'word', None)
        if cached is not None:
            return cached
        com.CoInitialize()
        word = win32.DispatchEx('Word.Application')
        word.Caption = tag
        word.Visible = mode == 'visible'
        word.DisplayAlerts = 0
        word.AutomationSecurity = 3
        word_export._thread_local.word = word
        print('Word created; visible=' + str(word.Visible), flush=True)
        return word

    word_export._get_word = isolated_word
    try:
        pdf = word_export.convert_docx_to_pdf((folder / 'sample.docx').read_bytes(), doc_label='PDF visibility test')
        (folder / (mode + '.pdf')).write_bytes(pdf)
        print('PDF created', flush=True)
    finally:
        word_export._discard_word()
        pythoncom.CoUninitialize()


def sample_documents():
    """Representative report variants; never read or change saved reports."""
    import base64
    from io import BytesIO
    from PIL import Image, ImageDraw
    from app.services.incident_report.incident_report_docx import build_docx as incident_docx
    from app.services.incident_report.smart_network_docx import build_docx as smart_docx

    pictures = []
    for name, format_name, color in [('sample.png', 'PNG', 'lightblue'), ('sample.jpg', 'JPEG', 'lightgreen')]:
        image = Image.new('RGB', (960, 540), color)
        ImageDraw.Draw(image).text((40, 40), 'PDF export validation image', fill='black')
        stream = BytesIO()
        image.save(stream, format=format_name)
        pictures.append({'id': name, 'filename': name,
                         'content_type': 'image/png' if format_name == 'PNG' else 'image/jpeg',
                         'data_base64': base64.b64encode(stream.getvalue()).decode('ascii')})
    report = {
        'document_title': 'Official Incident Report', 'incident_number': 'TEST-REPORT',
        'incident_raised_by': 'Test operator', 'incident_received_by': 'Test engineer',
        'reported_date': '13-Nov-2026', 'incident_date': '13-Nov-2026', 'report_time': '08:00',
        'service_disruption': 'Sample service interruption', 'incident_category': 'Transmission',
        'customers_impacted': 'Sample customer', 'duration_of_interruption': '00hrs 30mins',
        'raise_time': '13-Nov-2026 08:00', 'restored_time': '13-Nov-2026 08:30',
        'details_date_and_time': '13-Nov-2026 08:00', 'time_of_complaint': '13-Nov-2026 08:05',
        'issue_reported': 'Sample connection unavailable', 'actions_taken_summary': 'Checked and restored the sample connection.',
        'cause_of_outage': 'Sample interface failure', 'fault_gps_location': 'Test location',
        'issued_time': '13-Nov-2026 08:00', 'resolution': 'Restored the sample connection.', 'permanent_fixed': 'Yes',
        'chronology_events': [{'date': '13-Nov-2026', 'time': '08:00', 'description': 'Issue reported.'},
                              {'date': '13-Nov-2026', 'time': '08:30', 'description': 'Service verified.'}],
    }
    second = dict(report, has_second_fault='1', cause_of_outage_2='Sample backup path failure',
                  fault_gps_location_2='Second test location', issued_time_2='13-Nov-2026 08:10',
                  resolution_2='Restored the backup path.', permanent_fixed_2='Yes',
                  improvement_plan=['Monitor both paths.', 'Review the maintenance procedure.'],
                  picture_references=pictures)
    long_report = dict(report, chronology_events=[
        {'date': '13-Nov-2026' if index < 18 else '14-Nov-2026',
         'time': f'{index % 24:02d}:00',
         'description': 'Checked service status and recorded the investigation result. ' * 2}
        for index in range(36)
    ])
    months = ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec')
    monthly = [{'circuit': circuit, 'months': {month: '99.9%' for month in months}}
               for circuit in ('TEST-CIRCUIT-A', 'TEST-CIRCUIT-B')]
    smart = {
        'document_title': 'Monthly report', 'smart_customer_name': 'Sample customer',
        'smart_report_month': 'Nov 2026',
        'smart_active_circuits': [{'customer_description': 'Sample circuit', 'service': 'IPLC',
                                   'bandwidth': '100G', 'circuit_id': 'TEST-CIRCUIT-A'}],
        'smart_monthly_outage': monthly, 'smart_fault_services': monthly, 'smart_credit_note': monthly,
        'smart_credit_amounts': {'jan': '100', 'dec': '200'},
        'smart_failure_to_react': [{'ticket_no': 'TEST-REPORT', 'circuit_id': 'TEST-CIRCUIT-A',
                                     'smart_complain': '13-Nov-2026 08:05', 'tct_respond': '13-Nov-2026 08:10',
                                     'failure_to_react': '00hrs 05mins', 'sla': 'Pass', 'service_credit': '0%'}],
        'smart_services_outage': [{'ticket_no': 'TEST-REPORT', 'circuit_id': 'TEST-CIRCUIT-A',
                                   'date_started': '13-Nov-2026 08:00', 'date_finished': '13-Nov-2026 08:30',
                                   'service': 'IPLC', 'issue_owner': 'Test provider',
                                   'interruption': '00hrs 30mins', 'notes': 'Sample recovery details. ' * 12}],
    }
    return {
        'incident_standard': incident_docx(report),
        'incident_photos_png_jpeg': incident_docx(dict(report, picture_references=pictures)),
        'incident_second_fault_photos_plan': incident_docx(second),
        'incident_long_multi_day_chronology': incident_docx(long_report),
        'smart_network_complete': smart_docx(smart),
    }


def test_report(name, docx, folder, timeout, pdf_engine):
    folder.mkdir()
    (folder / 'sample.docx').write_bytes(docx)
    result = {}
    for mode in ('hidden', 'visible'):
        tag = 'NOC-PDF-TEST-' + uuid.uuid4().hex
        command = [sys.executable, str(Path(__file__).resolve()), '--child', mode, '--folder', str(folder), '--tag', tag]
        started = time.monotonic()
        print('Testing ' + name + ' / ' + mode + ' Word export...', flush=True)
        try:
            process = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=timeout,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            pdf_path = folder / (mode + '.pdf')
            if process.returncode == 0 and pdf_path.exists():
                data = pdf_path.read_bytes()
                valid = data.startswith(b'%PDF-') and b'%%EOF' in data[-4096:]
                result[mode] = {'success': valid, 'bytes': len(data)}
                if pdf_engine is not None and valid:
                    with pdf_engine.open(pdf_path) as pdf:
                        result[mode]['pages'] = len(pdf)
            else:
                result[mode] = {'success': False, 'reason': 'Word export failed', 'exit_code': process.returncode}
        except subprocess.TimeoutExpired:
            result[mode] = {'success': False, 'reason': 'Timed out after ' + str(timeout) + ' seconds'}
        finally:
            stop_tagged_word(tag)
        result[mode]['elapsed_seconds'] = round(time.monotonic() - started, 1)
        print(name + ' / ' + mode + ': ' + json.dumps(result[mode]), flush=True)
    if all(result[mode]['success'] for mode in ('hidden', 'visible')):
        if pdf_engine is not None:
            with pdf_engine.open(folder / 'hidden.pdf') as a, pdf_engine.open(folder / 'visible.pdf') as b:
                result['same_rendering'] = len(a) == len(b) and all(
                    left.get_pixmap().samples == right.get_pixmap().samples for left, right in zip(a, b)
                )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child', choices=('hidden', 'visible'))
    parser.add_argument('--folder', type=Path)
    parser.add_argument('--tag')
    parser.add_argument('--timeout', type=int, default=45)
    args = parser.parse_args()
    if args.child:
        child(args.child, args.folder, args.tag)
        return 0
    if not 10 <= args.timeout <= 60:
        parser.error('--timeout must be between 10 and 60 seconds')
    try:
        import pymupdf
    except ImportError:
        pymupdf = None
    results = {}
    with tempfile.TemporaryDirectory(prefix='noc-pdf-test-') as directory:
        for name, docx in sample_documents().items():
            results[name] = test_report(name, docx, Path(directory) / name, args.timeout, pymupdf)
    summary = {mode + '_all_passed': all(report[mode]['success'] for report in results.values())
               for mode in ('hidden', 'visible')}
    if pymupdf is not None:
        summary['all_layouts_match'] = all(report.get('same_rendering', False) for report in results.values())
    else:
        summary['layout_comparison'] = 'Not available; PDF creation was tested.'
    print(json.dumps({'reports': results, 'summary': summary}, indent=2), flush=True)
    return 0 if summary['hidden_all_passed'] and summary['visible_all_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
