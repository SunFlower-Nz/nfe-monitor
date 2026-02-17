"""Database models for NFe Monitor."""

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class NFeStatus(str, PyEnum):
    AUTHORIZED = "authorized"
    CANCELED = "canceled"
    DENIED = "denied"
    PENDING = "pending"


class User(Base):
    """User account model."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    companies = relationship("Company", back_populates="owner")


class Company(Base):
    """Company model — each company has a CNPJ to monitor."""
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    cnpj = Column(String(18), nullable=False, index=True)  # Format: XX.XXX.XXX/XXXX-XX
    state_code = Column(String(2), nullable=False)  # UF: SP, RJ, MG, etc.
    is_active = Column(Boolean, default=True)
    last_scraped_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("cnpj", name="uq_company_cnpj"),)

    owner = relationship("User", back_populates="companies")
    nfe_documents = relationship("NFeDocument", back_populates="company")


class NFeDocument(Base):
    """NFe document model — represents a single Nota Fiscal Eletrônica."""
    __tablename__ = "nfe_documents"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    access_key = Column(String(44), unique=True, nullable=False, index=True)  # Chave de acesso (44 digits)
    nfe_number = Column(String(20), nullable=False)
    series = Column(String(5))
    issuer_cnpj = Column(String(18), nullable=False)
    issuer_name = Column(String(200))
    issue_date = Column(DateTime, nullable=False)
    total_value = Column(Float, nullable=False)
    icms_value = Column(Float, default=0.0)
    ipi_value = Column(Float, default=0.0)
    status = Column(Enum(NFeStatus), default=NFeStatus.AUTHORIZED)
    xml_content = Column(Text, nullable=True)  # Full XML if available
    scraped_at = Column(DateTime, default=datetime.utcnow)
    notified = Column(Boolean, default=False)

    company = relationship("Company", back_populates="nfe_documents")


class ScrapeLog(Base):
    """Log of scraping runs for monitoring."""
    __tablename__ = "scrape_logs"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="running")  # running, success, failed
    documents_found = Column(Integer, default=0)
    new_documents = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
