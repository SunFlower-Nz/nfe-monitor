"""FastAPI application entry point for NFe Monitor."""

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models import Company, NFeDocument, User


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Automated fiscal document monitoring for Brazilian businesses.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health ---

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy", "version": settings.APP_VERSION, "timestamp": datetime.utcnow()}


# --- Auth ---

@app.post("/api/v1/auth/register", tags=["Auth"])
async def register(email: str, password: str, full_name: str, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=email,
        hashed_password=get_password_hash(password),
        full_name=full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer", "user_id": user.id}


@app.post("/api/v1/auth/login", tags=["Auth"])
async def login(email: str, password: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer", "user_id": user.id}


# --- Companies ---

@app.get("/api/v1/companies", tags=["Companies"])
async def list_companies(user_id: int, db: Session = Depends(get_db)):
    companies = db.query(Company).filter(Company.owner_id == user_id).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "cnpj": c.cnpj,
            "state_code": c.state_code,
            "is_active": c.is_active,
            "last_scraped_at": c.last_scraped_at,
        }
        for c in companies
    ]


@app.post("/api/v1/companies", status_code=201, tags=["Companies"])
async def create_company(
    user_id: int, name: str, cnpj: str, state_code: str,
    db: Session = Depends(get_db),
):
    company = Company(
        owner_id=user_id, name=name, cnpj=cnpj, state_code=state_code,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return {"id": company.id, "name": company.name, "cnpj": company.cnpj}


# --- NFe Documents ---

@app.get("/api/v1/nfe", tags=["NFe"])
async def list_nfe(
    company_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    since: str = Query(None, description="Filter by date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    query = db.query(NFeDocument).filter(NFeDocument.company_id == company_id)

    if since:
        since_date = datetime.strptime(since, "%Y-%m-%d")
        query = query.filter(NFeDocument.issue_date >= since_date)

    total = query.count()
    documents = (
        query.order_by(NFeDocument.issue_date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": [
            {
                "id": d.id,
                "access_key": d.access_key,
                "nfe_number": d.nfe_number,
                "issuer_cnpj": d.issuer_cnpj,
                "issuer_name": d.issuer_name,
                "issue_date": d.issue_date.isoformat(),
                "total_value": d.total_value,
                "status": d.status.value if hasattr(d.status, 'value') else d.status,
            }
            for d in documents
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.get("/api/v1/nfe/summary", tags=["NFe"])
async def nfe_summary(company_id: int, db: Session = Depends(get_db)):
    """Get summary statistics for a company's NFe documents."""
    docs = db.query(NFeDocument).filter(NFeDocument.company_id == company_id).all()

    total_value = sum(d.total_value for d in docs)
    total_icms = sum(d.icms_value for d in docs)

    # Group by month
    monthly = {}
    for d in docs:
        month_key = d.issue_date.strftime("%Y-%m")
        if month_key not in monthly:
            monthly[month_key] = {"count": 0, "total_value": 0.0}
        monthly[month_key]["count"] += 1
        monthly[month_key]["total_value"] += d.total_value

    return {
        "total_documents": len(docs),
        "total_value": total_value,
        "total_icms_credit": total_icms,
        "monthly_breakdown": monthly,
    }
