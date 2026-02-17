"""Scraping Celery tasks."""

from datetime import datetime, timedelta

from app.core.database import SessionLocal
from app.models import Company, NFeDocument, ScrapeLog
from app.scrapers.sefaz_nacional import SefazNacionalScraper
from app.tasks.celery_app import celery_app
from app.tasks.notification_tasks import send_new_nfe_notification


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def scrape_all_companies(self) -> dict:
    """
    Scrape all active companies.

    Returns:
        Summary of scraping results.
    """
    db = SessionLocal()
    results = {"total_companies": 0, "total_new_documents": 0, "errors": []}

    try:
        # Get all active companies
        companies = (
            db.query(Company)
            .filter(Company.is_active == True)
            .all()
        )

        results["total_companies"] = len(companies)

        for company in companies:
            try:
                scrape_single_company.delay(company.id)
            except Exception as e:
                results["errors"].append(
                    {"company_id": company.id, "error": str(e)}
                )

    finally:
        db.close()

    return results


@celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
def scrape_single_company(self, company_id: int) -> dict:
    """
    Scrape NFe documents for a single company.

    Args:
        company_id: ID of the company to scrape.

    Returns:
        Scraping results summary.
    """
    db = SessionLocal()
    log = ScrapeLog(company_id=company_id, started_at=datetime.utcnow())

    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise ValueError(f"Company {company_id} not found")

        db.add(log)
        db.commit()

        # Determine date range
        since_date = company.last_scraped_at or (datetime.utcnow() - timedelta(days=30))

        # Create scraper
        scraper = SefazNacionalScraper(
            cnpj=company.cnpj,
            state_code=company.state_code,
        )

        # Run scraper (this is sync wrapper around async code)
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            login_ok = loop.run_until_complete(scraper.login())
            if not login_ok:
                raise RuntimeError("Failed to login to SEFAZ portal")

            documents = loop.run_until_complete(scraper.scrape(since_date))
        finally:
            loop.run_until_complete(scraper.cleanup())
            loop.close()

        # Process scraped documents
        new_count = 0
        for doc in documents:
            # Check if document already exists
            existing = (
                db.query(NFeDocument)
                .filter(NFeDocument.access_key == doc.access_key)
                .first()
            )
            if existing:
                continue

            # Create new document
            nfe = NFeDocument(
                company_id=company.id,
                access_key=doc.access_key,
                nfe_number=doc.nfe_number,
                series=doc.series,
                issuer_cnpj=doc.issuer_cnpj,
                issuer_name=doc.issuer_name,
                issue_date=doc.issue_date,
                total_value=doc.total_value,
                icms_value=doc.icms_value,
                ipi_value=doc.ipi_value,
                status=doc.status,
                xml_content=doc.xml_content,
            )
            db.add(nfe)
            new_count += 1

        # Update company last scraped time
        company.last_scraped_at = datetime.utcnow()

        # Update log
        log.finished_at = datetime.utcnow()
        log.status = "success"
        log.documents_found = len(documents)
        log.new_documents = new_count

        db.commit()

        # Send notifications for new documents
        if new_count > 0:
            send_new_nfe_notification.delay(company.id, new_count)

        return {
            "company_id": company.id,
            "documents_found": len(documents),
            "new_documents": new_count,
            "status": "success",
        }

    except Exception as e:
        log.finished_at = datetime.utcnow()
        log.status = "failed"
        log.error_message = str(e)
        db.commit()

        # Retry on transient errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)

        return {
            "company_id": company_id,
            "status": "failed",
            "error": str(e),
        }

    finally:
        db.close()
