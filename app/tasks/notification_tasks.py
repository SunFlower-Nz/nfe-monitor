"""Notification Celery tasks — email and alert sending."""

from datetime import datetime, timedelta

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Company, NFeDocument, User
from app.tasks.celery_app import celery_app


@celery_app.task
def send_new_nfe_notification(company_id: int, new_count: int) -> dict:
    """
    Send notification when new NFe documents are found.

    Args:
        company_id: ID of the company.
        new_count: Number of new documents found.

    Returns:
        Notification result.
    """
    db = SessionLocal()

    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            return {"status": "error", "message": "Company not found"}

        user = db.query(User).filter(User.id == company.owner_id).first()
        if not user:
            return {"status": "error", "message": "User not found"}

        # Get new documents for the email
        new_docs = (
            db.query(NFeDocument)
            .filter(
                NFeDocument.company_id == company_id,
                NFeDocument.notified == False,
            )
            .order_by(NFeDocument.issue_date.desc())
            .all()
        )

        if not new_docs:
            return {"status": "skipped", "message": "No unnotified documents"}

        # Calculate totals
        total_value = sum(doc.total_value for doc in new_docs)

        # Build email content
        subject = f"📄 {new_count} nova(s) NFe detectada(s) — {company.name}"

        documents_html = ""
        for doc in new_docs:
            documents_html += f"""
            <tr>
                <td>{doc.nfe_number}</td>
                <td>{doc.issuer_name}</td>
                <td>{doc.issue_date.strftime('%d/%m/%Y')}</td>
                <td>R$ {doc.total_value:,.2f}</td>
            </tr>
            """

        body = f"""
        <html>
        <body>
            <h2>🔔 Novas NFe detectadas para {company.name}</h2>
            <p>Encontramos <strong>{new_count}</strong> nova(s) Nota(s) Fiscal(is) Eletrônica(s)
               emitidas contra o CNPJ {company.cnpj}.</p>

            <h3>Resumo</h3>
            <ul>
                <li><strong>Total de documentos:</strong> {new_count}</li>
                <li><strong>Valor total:</strong> R$ {total_value:,.2f}</li>
            </ul>

            <h3>Documentos</h3>
            <table border="1" cellpadding="8" cellspacing="0"
                   style="border-collapse: collapse; width: 100%;">
                <thead style="background: #1F4E79; color: white;">
                    <tr>
                        <th>Número NFe</th>
                        <th>Emitente</th>
                        <th>Data Emissão</th>
                        <th>Valor</th>
                    </tr>
                </thead>
                <tbody>
                    {documents_html}
                </tbody>
            </table>

            <p style="margin-top: 20px;">
                <a href="http://localhost:8501"
                   style="background: #1F4E79; color: white; padding: 10px 20px;
                          text-decoration: none; border-radius: 5px;">
                    Ver no Dashboard
                </a>
            </p>

            <p style="color: #666; font-size: 12px; margin-top: 30px;">
                Este é um email automático do NFe Monitor.
                Para alterar suas preferências de notificação, acesse o dashboard.
            </p>
        </body>
        </html>
        """

        # Send email (simplified — in production use proper email lib)
        _send_email(to=user.email, subject=subject, html_body=body)

        # Mark documents as notified
        for doc in new_docs:
            doc.notified = True
        db.commit()

        return {
            "status": "sent",
            "to": user.email,
            "documents": new_count,
            "total_value": total_value,
        }

    finally:
        db.close()


@celery_app.task
def send_daily_digest() -> dict:
    """Send daily digest email to all active users with yesterday's activity."""
    db = SessionLocal()
    sent_count = 0

    try:
        yesterday = datetime.utcnow() - timedelta(days=1)

        users = db.query(User).filter(User.is_active == True).all()

        for user in users:
            companies = (
                db.query(Company)
                .filter(Company.owner_id == user.id, Company.is_active == True)
                .all()
            )

            if not companies:
                continue

            company_ids = [c.id for c in companies]

            # Get yesterday's documents
            new_docs = (
                db.query(NFeDocument)
                .filter(
                    NFeDocument.company_id.in_(company_ids),
                    NFeDocument.scraped_at >= yesterday,
                )
                .all()
            )

            if not new_docs:
                continue

            total_value = sum(d.total_value for d in new_docs)

            subject = f"📊 Resumo diário NFe Monitor — {len(new_docs)} documento(s)"
            body = f"""
            <html><body>
            <h2>Resumo Diário — {datetime.now().strftime('%d/%m/%Y')}</h2>
            <p>Novos documentos nas últimas 24h: <strong>{len(new_docs)}</strong></p>
            <p>Valor total: <strong>R$ {total_value:,.2f}</strong></p>
            <p><a href="http://localhost:8501">Ver detalhes</a></p>
            </body></html>
            """

            _send_email(to=user.email, subject=subject, html_body=body)
            sent_count += 1

    finally:
        db.close()

    return {"digests_sent": sent_count}


def _send_email(to: str, subject: str, html_body: str) -> None:
    """
    Send an email using SMTP.

    In production, consider using a service like SendGrid, SES, or Mailgun.
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    if not settings.SMTP_USER:
        print(f"[EMAIL MOCK] To: {to}, Subject: {subject}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.EMAILS_FROM_NAME} <{settings.SMTP_USER}>"
    msg["To"] = to

    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
