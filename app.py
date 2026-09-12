"""
Calculador de Valor Intrinseco (VMI) - version app de escritorio/web
Replica el modelo de VMI_Investing_template.xlsx: solo se ingresa el
"stock symbol" y la app trae automaticamente los datos financieros y
calcula el valor intrinseco por accion a 20 anios.

Ejecutar con:
    streamlit run app.py
"""
import streamlit as st

from data_fetcher import fetch_stock_data, DEFAULT_ASSUMPTIONS
from valuation import ValuationInputs, compute_intrinsic_value, discount_rate_from_beta

st.set_page_config(page_title="Calculador de Valor Intrinseco", page_icon="📈", layout="wide")

# ---------------------------------------------------------------- estilos --
st.markdown("""
<style>
.big-metric-card {
    border-radius: 16px;
    padding: 28px 24px;
    color: white;
    text-align: center;
}
.big-metric-card h2 { margin: 0; font-size: 15px; font-weight: 600; opacity: 0.9; letter-spacing: .03em; text-transform: uppercase;}
.big-metric-card p { margin: 6px 0 0 0; font-size: 40px; font-weight: 800; }
.card-blue   { background: linear-gradient(135deg, #1e3a5f, #2c5f8a); }
.card-green  { background: linear-gradient(135deg, #0f5132, #1f8f5f); }
.card-red    { background: linear-gradient(135deg, #7a1f1f, #b23a3a); }
.section-title { font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; margin-top: 18px;}
</style>
""", unsafe_allow_html=True)

st.title("📈 Calculador de Valor Intrinseco")
st.caption("Basado en el modelo de descuento a 20 anios (Ingreso Neto / Flujo de Caja Operativo / Flujo de Caja Libre)")

# ------------------------------------------------------------- entrada -----
col_a, col_b = st.columns([2, 1])
with col_a:
    ticker = st.text_input("Stock Symbol", value="MU", placeholder="Ej: AAPL, MU, 0700.HK").strip().upper()
with col_b:
    method = st.selectbox(
        "Metodo de valoracion",
        ["Discounted Net Income", "Discounted Cash Flow", "Discounted Free Cash Flow"],
    )

buscar = st.button("🔍 Traer datos y calcular", type="primary")

if "fetched" not in st.session_state:
    st.session_state.fetched = None

if buscar and ticker:
    with st.spinner(f"Buscando datos de {ticker}..."):
        try:
            st.session_state.fetched = fetch_stock_data(ticker)
        except Exception as e:
            st.session_state.fetched = None
            st.error(f"No se pudieron obtener datos para '{ticker}': {e}")

data = st.session_state.fetched

if data:
    if data.warnings:
        with st.expander("⚠️ Avisos al obtener datos (algunos campos pueden requerir edicion manual)"):
            for w in data.warnings:
                st.write("- " + w)

    st.markdown('<p class="section-title">Datos obtenidos automaticamente (edita si algo no cuadra)</p>', unsafe_allow_html=True)

    metric_label = {
        "Discounted Net Income": ("Ingreso Neto (actual)", data.net_income),
        "Discounted Cash Flow": ("Flujo de Caja Operativo (actual)", data.operating_cash_flow),
        "Discounted Free Cash Flow": ("Flujo de Caja Libre (actual)", data.free_cash_flow),
    }[method]

    c1, c2, c3 = st.columns(3)
    with c1:
        company_name = st.text_input("Nombre de la compania", value=data.company_name or ticker)
        statement_ccy = st.text_input("Moneda de estados financieros", value=data.financial_statement_currency or "USD")
        listing_ccy = st.text_input("Moneda de cotizacion", value=data.stock_listing_currency or "USD")
        exchange_rate = st.number_input(
            f"1 {statement_ccy} equivale a (en {listing_ccy})", value=1.0, min_value=0.0, format="%.6f"
        )
    with c2:
        base_metric = st.number_input(
            metric_label[0], value=float(metric_label[1] or 0.0), format="%.2f"
        )
        total_debt = st.number_input("Deuda total (corto + largo plazo)", value=float(data.total_debt or 0.0), format="%.2f")
        cash = st.number_input("Caja e inversiones a corto plazo", value=float(data.cash_and_st_investments or 0.0), format="%.2f")
        shares = st.number_input("Acciones en circulacion", value=float(data.shares_outstanding or 0.0), format="%.0f")
    with c3:
        last_close = st.number_input(f"Ultimo cierre ({listing_ccy})", value=float(data.last_close_price or 0.0), format="%.2f")
        current_year = st.number_input("Anio actual (ultimo anio fiscal)", value=2026, step=1)
        beta = st.number_input("Beta", value=float(data.beta or 1.0), format="%.2f")
        risk_free = st.number_input("Tasa libre de riesgo", value=float(data.risk_free_rate or 0.03), format="%.5f")
        mrp = st.number_input(
            "Prima de riesgo de mercado", value=float(data.market_risk_premium or 0.03), format="%.5f",
            help="Se obtiene automaticamente (ERP y Rf 'Current Guidance' mas recientes de Kroll para EE.UU.). Editable."
        )

    calc_discount_rate = discount_rate_from_beta(beta, risk_free, mrp)

    st.markdown('<p class="section-title">Tasas de crecimiento y descuento</p>', unsafe_allow_html=True)
    g1, g2, g3, g4 = st.columns(4)
    with g1:
        growth_1_5 = st.number_input(
            "Crecimiento anios 1-5",
            value=float(data.historical_growth_estimate or 0.10), format="%.4f",
            help="Sugerencia inicial basada en el CAGR historico de utilidad neta. Ajustalo con tu propio criterio o estimados de analistas."
        )
    with g2:
        growth_6_10 = st.number_input("Crecimiento anios 6-10", value=float((growth_1_5 or 0.1) / 2), format="%.4f")
    with g3:
        growth_11_20 = st.number_input("Crecimiento anios 11-20", value=0.04, format="%.4f")
    with g4:
        discount_rate = st.number_input(
            "Tasa de descuento (Risk Free + Beta x Prima)",
            value=float(calc_discount_rate), format="%.4f",
            help="Calculada automaticamente como Tasa libre de riesgo + Beta x Prima de riesgo de mercado. Puedes sobreescribirla."
        )

    if st.button("💰 Calcular Valor Intrinseco", type="primary"):
        inp = ValuationInputs(
            ticker=ticker, company_name=company_name, valuation_method=method,
            financial_statement_currency=statement_ccy, stock_listing_currency=listing_ccy,
            exchange_rate=exchange_rate,
            base_metric_current=base_metric, total_debt=total_debt, cash_and_st_investments=cash,
            growth_1_5=growth_1_5, growth_6_10=growth_6_10, growth_11_20=growth_11_20,
            shares_outstanding=shares, discount_rate=discount_rate,
            current_year=int(current_year), last_close_price=last_close,
            beta=beta, risk_free_rate=risk_free, market_risk_premium=mrp,
        )
        result = compute_intrinsic_value(inp)

        st.markdown("---")
        st.subheader(f"Resultado — {company_name} ({ticker})")

        premium = result.discount_premium
        premium_color = "card-green" if premium < 0 else "card-red"
        premium_word = "DESCUENTO (infravalorada)" if premium < 0 else "PRIMA (sobrevalorada)"

        r1, r2 = st.columns(2)
        with r1:
            st.markdown(f"""
            <div class="big-metric-card card-blue">
                <h2>Valor Intrinseco Final por Accion ({listing_ccy})</h2>
                <p>{result.final_intrinsic_value_per_share_listing_ccy:,.2f}</p>
            </div>
            """, unsafe_allow_html=True)
        with r2:
            st.markdown(f"""
            <div class="big-metric-card {premium_color}">
                <h2>{premium_word}</h2>
                <p>{premium * 100:,.1f}%</p>
            </div>
            """, unsafe_allow_html=True)

        st.caption(f"Ultimo cierre: {last_close:,.2f} {listing_ccy}  ·  Tasa de descuento usada: {discount_rate*100:.2f}%")

        with st.expander("Ver detalle del calculo (igual a las columnas F:O de la hoja original)"):
            d1, d2 = st.columns(2)
            with d1:
                st.write("**Ingreso Neto antes de caja/deuda por accion**", f"{result.intrinsic_value_before_cash_debt:,.2f}")
                st.write("**(–) Deuda por accion**", f"{result.debt_per_share:,.2f}")
                st.write("**(+) Caja por accion**", f"{result.cash_per_share:,.2f}")
            with d2:
                st.write("**Valor Intrinseco por accion (moneda de estados financieros)**", f"{result.intrinsic_value_per_share_statement_ccy:,.2f}")
                st.write("**Valor presente 20 anios (total)**", f"{result.present_value_20y_statement_ccy:,.0f}")

            st.write("**Proyeccion anios 1-10**")
            st.table({
                "Anio": [y for y, *_ in result.years_1_10],
                "Valor proyectado": [f"{v:,.0f}" for _, v, *_ in result.years_1_10],
                "Valor descontado": [f"{v:,.0f}" for *_, v in result.years_1_10],
            })
            st.write("**Proyeccion anios 11-20**")
            st.table({
                "Anio": [y for y, *_ in result.years_11_20],
                "Valor proyectado": [f"{v:,.0f}" for _, v, *_ in result.years_11_20],
                "Valor descontado": [f"{v:,.0f}" for *_, v in result.years_11_20],
            })
else:
    st.info("Ingresa un stock symbol y presiona 'Traer datos y calcular' para comenzar.")
