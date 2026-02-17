"""Streamlit dashboard for NFe Monitor."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import httpx
from datetime import datetime, timedelta

# Configuration
API_URL = "http://api:8000"

st.set_page_config(
    page_title="NFe Monitor",
    page_icon="📄",
    layout="wide",
)

# --- Authentication State ---
if "token" not in st.session_state:
    st.session_state.token = None
    st.session_state.user_id = None


def api_get(endpoint: str, params: dict = None) -> dict:
    """Make authenticated GET request to API."""
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    response = httpx.get(f"{API_URL}{endpoint}", params=params, headers=headers)
    response.raise_for_status()
    return response.json()


# --- Login Page ---
if not st.session_state.token:
    st.title("🔐 NFe Monitor — Login")

    tab1, tab2 = st.tabs(["Login", "Cadastro"])

    with tab1:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Senha", type="password", key="login_password")

        if st.button("Entrar"):
            try:
                response = httpx.post(
                    f"{API_URL}/api/v1/auth/login",
                    params={"email": email, "password": password},
                )
                if response.status_code == 200:
                    data = response.json()
                    st.session_state.token = data["access_token"]
                    st.session_state.user_id = data["user_id"]
                    st.rerun()
                else:
                    st.error("Email ou senha incorretos")
            except Exception as e:
                st.error(f"Erro de conexão: {e}")

    with tab2:
        name = st.text_input("Nome completo")
        email = st.text_input("Email", key="reg_email")
        password = st.text_input("Senha", type="password", key="reg_password")

        if st.button("Cadastrar"):
            try:
                response = httpx.post(
                    f"{API_URL}/api/v1/auth/register",
                    params={"email": email, "password": password, "full_name": name},
                )
                if response.status_code == 200:
                    data = response.json()
                    st.session_state.token = data["access_token"]
                    st.session_state.user_id = data["user_id"]
                    st.rerun()
                else:
                    st.error("Erro no cadastro")
            except Exception as e:
                st.error(f"Erro: {e}")

    st.stop()


# --- Main Dashboard ---
st.title("📄 NFe Monitor — Dashboard")

# Sidebar
with st.sidebar:
    st.header("🏢 Empresas")

    companies = api_get("/api/v1/companies", {"user_id": st.session_state.user_id})

    if not companies:
        st.warning("Nenhuma empresa cadastrada")
        st.stop()

    company_names = {c["id"]: c["name"] for c in companies}
    selected_company_id = st.selectbox(
        "Selecionar empresa",
        options=list(company_names.keys()),
        format_func=lambda x: company_names[x],
    )

    st.divider()

    if st.button("🚪 Sair"):
        st.session_state.token = None
        st.session_state.user_id = None
        st.rerun()


# --- KPI metrics ---
summary = api_get("/api/v1/nfe/summary", {"company_id": selected_company_id})

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total NFe", summary["total_documents"])
with col2:
    st.metric("Valor Total", f"R$ {summary['total_value']:,.2f}")
with col3:
    st.metric("Crédito ICMS", f"R$ {summary['total_icms_credit']:,.2f}")
with col4:
    selected_company = next(c for c in companies if c["id"] == selected_company_id)
    last_scraped = selected_company.get("last_scraped_at", "Nunca")
    st.metric("Última verificação", last_scraped or "Nunca")

st.divider()

# --- Charts ---
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("📈 NFe por Mês")
    if summary["monthly_breakdown"]:
        monthly_df = pd.DataFrame([
            {"Mês": k, "Quantidade": v["count"], "Valor": v["total_value"]}
            for k, v in sorted(summary["monthly_breakdown"].items())
        ])
        fig = px.bar(monthly_df, x="Mês", y="Valor", text="Quantidade",
                     color_discrete_sequence=["#1F4E79"])
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem dados para exibir")

with col_chart2:
    st.subheader("🏭 Top Fornecedores")
    nfe_data = api_get("/api/v1/nfe", {
        "company_id": selected_company_id, "page_size": 100
    })
    if nfe_data["items"]:
        nfe_df = pd.DataFrame(nfe_data["items"])
        supplier_totals = nfe_df.groupby("issuer_name")["total_value"].sum().nlargest(10)
        fig2 = px.pie(values=supplier_totals.values, names=supplier_totals.index,
                      color_discrete_sequence=px.colors.sequential.Blues_r)
        fig2.update_layout(height=350)
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Sem dados para exibir")

st.divider()

# --- Documents Table ---
st.subheader("📋 Documentos Recentes")

if nfe_data["items"]:
    display_df = pd.DataFrame(nfe_data["items"])[
        ["nfe_number", "issuer_name", "issuer_cnpj", "issue_date", "total_value", "status"]
    ]
    display_df.columns = ["Número", "Emitente", "CNPJ Emitente", "Data", "Valor (R$)", "Status"]
    display_df["Valor (R$)"] = display_df["Valor (R$)"].apply(lambda x: f"R$ {x:,.2f}")

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Export button
    csv = display_df.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Exportar CSV", csv, "nfe_documents.csv", "text/csv")
else:
    st.info("Nenhum documento encontrado")
