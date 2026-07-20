"""Entry point for scheduled/background jobs (run via cron or a task runner)."""
from app import create_app
from app.services.report_service import ReportService
from app.utils.logger import get_logger

logger = get_logger(__name__)


def run():
    app = create_app()
    with app.app_context():
        service = ReportService()
        reports = service.list_reports()
        logger.info("Scheduled run processed %d reports", len(reports))

if __name__ == "__main__":
    run()
