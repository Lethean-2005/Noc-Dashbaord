"""Converts a .docx (as bytes) to PDF via Microsoft Word itself (COM
automation) — not a reportlab/pure-Python reconstruction. Shared by every
report type that needs Word's own rendering engine for high-fidelity PDF
export (Incident Report, Smart Network Report, ...); each report type
only needs its own build_docx(report), and calls
convert_docx_to_pdf(build_docx(report)) here for the PDF.

Requires Microsoft Word to be installed on whatever machine runs this —
there is no reportlab/pure-Python fallback. If Word (or pywin32) isn't
available, convert_docx_to_pdf() raises RuntimeError rather than silently
producing a lower-fidelity document; the route layer decides how to
surface that to the user.

Originally lived inside incident_report_pdf.py as that report type's own
code — extracted here once a second report type (Smart Network Report)
needed the exact same Word-automation machinery, so it's shared instead
of duplicated.
"""

import os
import tempfile
import threading
import time

from app.utils.logger import get_logger

logger = get_logger(__name__)

_WD_EXPORT_FORMAT_PDF = 17
_WD_EXPORT_OPTIMIZE_FOR_PRINT = 0
_WD_EXPORT_DOCUMENT_CONTENT = 0

# One Word instance PER WORKER THREAD, kept alive and reused across
# calls instead of spinning a fresh one up (DispatchEx) and tearing it
# down (Quit) on every single export — measured at 4-9s combined out of
# a typical 7-16s total, none of it scaling with document complexity (a
# report with 0 events and one with 5 events took the same time) — it's
# pure Word process startup/shutdown overhead, not our own code or the
# document's own size. Thread-local rather than one shared instance:
# this app runs multi-threaded (waitress with WAITRESS_THREADS, or
# Werkzeug's threaded=True dev server — see run.py), and Word's COM
# automation objects are single-threaded-apartment — calling the SAME
# instance from a different thread than created it risks
# RPC_E_WRONG_THREAD errors or silent corruption, so each thread gets
# and keeps its own instead of ever sharing one.
_thread_local = threading.local()


def _discard_word():
    """Drops this thread's cached Word instance (if any) — called when
    it's found dead (the liveness probe in _get_word() below) or after
    an export failed on it, so the NEXT call on this thread starts a
    fresh instance rather than reusing a possibly-broken process."""
    word = getattr(_thread_local, "word", None)
    _thread_local.word = None
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass


def _get_word(win32, pythoncom):
    word = getattr(_thread_local, "word", None)
    if word is not None:
        try:
            _ = word.Visible  # liveness probe — raises if the process died
            return word
        except Exception:
            _discard_word()

    # CoInitialize is intentionally never paired with a CoUninitialize
    # here — this apartment is meant to live as long as this worker
    # thread does, for as long as _thread_local.word stays cached, not
    # just for one call.
    pythoncom.CoInitialize()
    word = win32.DispatchEx("Word.Application")
    # Visible=True, not False — confirmed live on the VM that a manual,
    # visible Word export of a blank doc succeeds while this app's own
    # invisible, automated export of a real filled-in doc fails every
    # time with a bare "Command failed" from BOTH ExportAsFixedFormat
    # AND the legacy SaveAs fallback (same document, same account, same
    # already-connected RDP session — only the Visible flag differs).
    # That matches a known Windows Server limitation: some of Word's own
    # export/rendering code paths need a real paintable window surface,
    # which an invisible automation instance never gets allocated. The
    # window briefly appearing on the SERVER's own screen (never seen by
    # an actual dashboard user) is an acceptable tradeoff for the export
    # actually working.
    word.Visible = True
    word.DisplayAlerts = 0
    try:
        # msoAutomationSecurityForceDisable (3) — on an unattended server
        # this instance never has a UI to click through, so any macro/
        # ActiveX security prompt that Word would normally pop up has
        # nowhere to go; instead of blocking (and DisplayAlerts=0
        # suppressing the dialog while the call underneath still waits
        # on it) it can surface as exactly the generic "export failed
        # due to an unexpected error" seen on the VM. Forcing this off
        # removes that whole class of silent failure.
        word.AutomationSecurity = 3
    except Exception:
        pass
    _thread_local.word = word
    return word


def convert_docx_to_pdf(docx_bytes, doc_label="document"):
    """docx_bytes: a real .docx file's bytes (from any report type's own
    build_docx()). Returns PDF bytes. The first export on a given worker
    thread still pays Word's own startup cost; every export after that
    on the SAME thread reuses the already-running instance (see
    _get_word() above) instead of paying it again.

    `doc_label` is purely for the retry/timing log lines, so a VM-side
    "export failed" report can be pinned to which report type it was
    without needing a separate log line format per type.

    A production export once failed with a generic Word COM error
    (ExportAsFixedFormat's own "The export failed due to an unexpected
    error", HRESULT -2147467259/E_FAIL — no further detail from Word
    itself) on a report with a real uploaded photo — Word's COM
    automation is flaky enough on its own (a leftover process from a
    prior crash, a transient lock) that a single attempt isn't reliable;
    this retries up to 2 more times (3 total), discarding this thread's
    cached Word instance first and pausing 2s before each retry so the
    retry gets a completely fresh instance AND whatever transient
    condition caused the failure has time to actually clear, before
    giving up — same idea as BaseCacheRepository.replace_all()'s own
    retry for "database is locked"."""
    try:
        import pythoncom
        import win32com.client as win32
        import pywintypes
    except ImportError as e:
        raise RuntimeError(
            "PDF export requires Microsoft Word + pywin32 on this machine "
            "(pip install pywin32) — no fallback renderer is used, since "
            "the whole point is matching Word's own output exactly."
        ) from e

    t_start = time.monotonic()

    _MAX_ATTEMPTS = 3
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return _export_via_word(docx_bytes, win32, pythoncom, pywintypes, t_start, doc_label)
        except pywintypes.com_error as e:
            _discard_word()
            if attempt == _MAX_ATTEMPTS:
                raise RuntimeError(
                    f"PDF export failed in Microsoft Word after {_MAX_ATTEMPTS} attempts "
                    f"({e.args[2][2] if len(e.args) > 2 and e.args[2] else e}). "
                    "This can happen with an unusual attached photo, or a "
                    "leftover Word process on the server — try DOCX export "
                    "instead, or removing/re-uploading any photos and "
                    "trying again."
                ) from e
            # A brief pause before retrying, not an immediate retry — the
            # docstring's own "transient lock"/"leftover process" theory
            # for why a single attempt isn't reliable only has time to
            # clear if something actually waits for it; retrying in the
            # same instant just hits the identical transient state again.
            logger.warning(
                "%s PDF export attempt %d/%d failed (%s) — retrying in 2s",
                doc_label, attempt, _MAX_ATTEMPTS, e,
            )
            time.sleep(2)


def _export_via_word(docx_bytes, win32, pythoncom, pywintypes, t_start, doc_label):
    with tempfile.TemporaryDirectory() as tmp_dir:
        docx_path = os.path.join(tmp_dir, "export.docx")
        pdf_path = os.path.join(tmp_dir, "export.pdf")
        with open(docx_path, "wb") as f:
            f.write(docx_bytes)

        word = _get_word(win32, pythoncom)
        t_word_started = time.monotonic()
        doc = None
        t_doc_opened = t_exported = None
        try:
            doc = word.Documents.Open(docx_path, ReadOnly=True)
            t_doc_opened = time.monotonic()
            try:
                # If a PREVIOUS run ever left a Word process hanging
                # around (a crash before the old per-call word.Quit(),
                # or the user manually opening the .docx themselves —
                # both happened once during development), some global
                # Word UI state — like "Show Markup" being on, which
                # underlines/colors a template's own leftover
                # grammar-check marks — can otherwise leak into what
                # gets baked into a fresh export. Forcing Final/no-markup
                # view here makes the exported PDF's markup state
                # deterministic regardless of any such ambient state —
                # now doubly relevant since the Word instance itself is
                # reused across calls, not just across accidental leftover
                # processes.
                doc.ActiveWindow.View.ShowRevisionsAndComments = False
                doc.ActiveWindow.View.RevisionsView = 0  # wdRevisionsViewFinal
            except Exception:
                pass
            # ExportAsFixedFormat (what Word's own "Save As PDF" dialog
            # uses) instead of the older SaveAs(FileFormat=17) — the
            # legacy call renders thin table borders visibly bolder than
            # the original. OptimizeFor=Print is the high-fidelity vector
            # path; OnScreen (the other option) is what produced the
            # bolder lines. Item=Content (not WithMarkup) is a second,
            # redundant guard against the same markup-leaking-into-export
            # risk the Final-view lines above already cover.
            try:
                doc.ExportAsFixedFormat(
                    OutputFileName=pdf_path,
                    ExportFormat=_WD_EXPORT_FORMAT_PDF,
                    OptimizeFor=_WD_EXPORT_OPTIMIZE_FOR_PRINT,
                    Item=_WD_EXPORT_DOCUMENT_CONTENT,
                )
            except pywintypes.com_error as export_error:
                # ExportAsFixedFormat is the high-fidelity path (see
                # above), but it's also the one seen failing on the VM
                # with a bare "unexpected error" and no further detail —
                # same open, already-working document, just a different
                # Word export API, so this is cheap to try before giving
                # up and tearing down the whole Word instance (the
                # caller's own 3-attempt retry, which DOES tear it down,
                # is still the backstop if this also fails). Slightly
                # bolder table borders is a far better outcome than no
                # PDF at all.
                logger.warning(
                    "%s: ExportAsFixedFormat failed (%s) — retrying this export via "
                    "legacy SaveAs(wdFormatPDF) before giving up",
                    doc_label, export_error,
                )
                doc.SaveAs(pdf_path, FileFormat=_WD_EXPORT_FORMAT_PDF)
            t_exported = time.monotonic()
        finally:
            # Only the DOCUMENT closes per call — the Word APPLICATION
            # itself stays open, cached on _thread_local for the next
            # call on this same thread to reuse (see _get_word()).
            if doc is not None:
                doc.Close(False)
        t_cleanup_done = time.monotonic()

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

    t_done = time.monotonic()
    # Logged so a slow export (reported on the VM) can be pinned to a
    # specific phase — Word's own startup (only paid on this thread's
    # FIRST export — see _get_word()), the Documents.Open() call,
    # ExportAsFixedFormat() itself, or the document's own Close() —
    # instead of guessing; each has a different likely cause (a cold
    # Word first-launch, antivirus scanning the temp file, genuine page
    # count) and a different fix.
    logger.info(
        "%s PDF export timing: word_startup=%s doc_open=%s export=%s "
        "doc_close=%s total=%.2fs",
        doc_label,
        f"{t_word_started - t_start:.2f}s",
        f"{t_doc_opened - t_word_started:.2f}s" if t_doc_opened else "n/a",
        f"{t_exported - t_doc_opened:.2f}s" if t_exported and t_doc_opened else "n/a",
        f"{t_cleanup_done - (t_exported or t_doc_opened or t_word_started):.2f}s",
        t_done - t_start,
    )
    return pdf_bytes
