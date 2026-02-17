"""Abstract base class for SEFAZ scrapers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class ScrapedNFe:
    """Data class for a scraped NFe document."""
    access_key: str
    nfe_number: str
    series: str
    issuer_cnpj: str
    issuer_name: str
    issue_date: datetime
    total_value: float
    icms_value: float = 0.0
    ipi_value: float = 0.0
    status: str = "authorized"
    xml_content: Optional[str] = None


class BaseSefazScraper(ABC):
    """
    Abstract base class for SEFAZ portal scrapers.

    Each state may have a slightly different portal layout,
    so we create specific scrapers inheriting from this base.
    """

    def __init__(self, cnpj: str, state_code: str):
        """
        Initialize scraper.

        Args:
            cnpj: Company CNPJ to check NFe for.
            state_code: State code (UF), e.g., 'SP', 'RJ'.
        """
        self.cnpj = cnpj
        self.state_code = state_code

    @abstractmethod
    async def scrape(self, since_date: Optional[datetime] = None) -> List[ScrapedNFe]:
        """
        Scrape SEFAZ portal for NFe documents.

        Args:
            since_date: Only return NFe issued after this date.

        Returns:
            List of scraped NFe documents.
        """
        pass

    @abstractmethod
    async def login(self) -> bool:
        """
        Authenticate with the SEFAZ portal.

        Returns:
            True if login successful.
        """
        pass

    async def cleanup(self) -> None:
        """Clean up resources (close browser, etc.)."""
        pass
