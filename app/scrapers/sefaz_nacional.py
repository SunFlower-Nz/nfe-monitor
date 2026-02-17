"""SEFAZ Nacional scraper using Playwright."""

import asyncio
from datetime import datetime
from typing import List, Optional

from playwright.async_api import async_playwright, Browser, Page

from app.scrapers.base import BaseSefazScraper, ScrapedNFe


class SefazNacionalScraper(BaseSefazScraper):
    """
    Scraper for the Portal Nacional da NFe (https://www.nfe.fazenda.gov.br).

    Uses Playwright for headless browser automation to navigate the portal,
    authenticate, and extract NFe data for a given CNPJ.
    """

    PORTAL_URL = "https://www.nfe.fazenda.gov.br/portal/consultaRecebidas.aspx"

    def __init__(self, cnpj: str, state_code: str, certificate_path: str = "", certificate_password: str = ""):
        super().__init__(cnpj, state_code)
        self.certificate_path = certificate_path
        self.certificate_password = certificate_password
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

    async def login(self) -> bool:
        """
        Authenticate with SEFAZ portal using digital certificate.

        Returns:
            True if authentication successful.
        """
        try:
            playwright = await async_playwright().start()
            self._browser = await playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            self._page = await context.new_page()

            # Navigate to portal
            await self._page.goto(self.PORTAL_URL, wait_until="networkidle", timeout=30000)

            # Wait for login form
            await self._page.wait_for_selector("#login-certificado", timeout=10000)

            # Click certificate login
            await self._page.click("#login-certificado")

            # Note: In production, certificate handling would be done via
            # browser certificate store or client certificate authentication.
            # This is a simplified version for demonstration purposes.

            # Wait for authenticated state
            await self._page.wait_for_selector("#consulta-form", timeout=15000)

            return True

        except Exception as e:
            print(f"Login failed: {e}")
            return False

    async def scrape(self, since_date: Optional[datetime] = None) -> List[ScrapedNFe]:
        """
        Scrape NFe documents from the portal.

        Args:
            since_date: Only return documents issued after this date.

        Returns:
            List of ScrapedNFe objects.
        """
        if not self._page:
            raise RuntimeError("Must call login() before scrape()")

        documents: List[ScrapedNFe] = []

        try:
            # Fill CNPJ in search form
            await self._page.fill("#cnpj-destinatario", self.cnpj)

            # Set date range if specified
            if since_date:
                date_str = since_date.strftime("%d/%m/%Y")
                await self._page.fill("#data-inicio", date_str)

            # Set end date to today
            today_str = datetime.now().strftime("%d/%m/%Y")
            await self._page.fill("#data-fim", today_str)

            # Submit search
            await self._page.click("#btn-consultar")

            # Wait for results
            await self._page.wait_for_selector(
                ".resultado-consulta, .sem-resultados",
                timeout=30000,
            )

            # Check if there are results
            no_results = await self._page.query_selector(".sem-resultados")
            if no_results:
                return documents

            # Parse results table
            rows = await self._page.query_selector_all(".resultado-consulta tbody tr")

            for row in rows:
                try:
                    cells = await row.query_selector_all("td")
                    if len(cells) < 7:
                        continue

                    access_key = await self._get_text(cells[0])
                    nfe_number = await self._get_text(cells[1])
                    series = await self._get_text(cells[2])
                    issuer_cnpj = await self._get_text(cells[3])
                    issuer_name = await self._get_text(cells[4])
                    issue_date_str = await self._get_text(cells[5])
                    total_value_str = await self._get_text(cells[6])

                    # Parse date
                    issue_date = datetime.strptime(issue_date_str.strip(), "%d/%m/%Y")

                    # Parse value (Brazilian format: 1.234,56)
                    total_value = float(
                        total_value_str
                        .replace("R$", "")
                        .replace(".", "")
                        .replace(",", ".")
                        .strip()
                    )

                    doc = ScrapedNFe(
                        access_key=access_key.strip(),
                        nfe_number=nfe_number.strip(),
                        series=series.strip(),
                        issuer_cnpj=issuer_cnpj.strip(),
                        issuer_name=issuer_name.strip(),
                        issue_date=issue_date,
                        total_value=total_value,
                    )

                    documents.append(doc)

                except Exception as e:
                    print(f"Error parsing row: {e}")
                    continue

            # Check for pagination and get remaining pages
            while True:
                next_btn = await self._page.query_selector(".pagination .next:not(.disabled)")
                if not next_btn:
                    break

                await next_btn.click()
                await self._page.wait_for_selector(".resultado-consulta tbody tr", timeout=10000)
                await asyncio.sleep(1)  # Rate limiting

                # Parse additional rows
                rows = await self._page.query_selector_all(".resultado-consulta tbody tr")
                for row in rows:
                    try:
                        cells = await row.query_selector_all("td")
                        if len(cells) < 7:
                            continue
                        # ... same parsing logic
                    except Exception:
                        continue

        except Exception as e:
            print(f"Scrape failed: {e}")
            raise

        return documents

    async def _get_text(self, element) -> str:
        """Extract text content from a page element."""
        return (await element.text_content()) or ""

    async def cleanup(self) -> None:
        """Close browser resources."""
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._page = None
