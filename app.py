"""
Calculador de Valor Intrínseco (VMI) - version app de escritorio/web
Replica el modelo de VMI_Investing_template.xlsx: solo se ingresa el
"stock symbol" y la app trae automáticamente los datos financieros y
calcula el valor intrinseco por acción a 10 anios (3 tramos de crecimiento).

Ejecutar con:
    streamlit run app.py
"""
import streamlit as st
import pandas as pd

from data_fetcher import fetch_stock_data, fetch_quarterly_fundamentals, fetch_price_history
from valuation import (
    ValuationInputs, compute_intrinsic_value, discount_rate_from_beta,
    discount_rate_from_beta_table_us, total_debt_to_ebitda, interpret_debt_ratio,
    interpret_recommendation, compute_roic, compute_peg_ratio, compute_fcf_margin,
)

st.set_page_config(page_title="Calculador de Valor Intrínseco", page_icon="📈", layout="wide")

MILLION = 1_000_000


def fmt_money(value: float, decimals: int = 2) -> str:
    """Formatea valores grandes en millones (sin decimales) para facilitar
    la lectura. Ej: 12,493,000,000 -> '12,493 M'   |   338.42 -> '338.42'"""
    if value is None:
        return "-"
    if abs(value) >= MILLION:
        return f"{value / MILLION:,.0f} M"
    return f"{value:,.{decimals}f}"


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
.card-purple { background: linear-gradient(135deg, #4a1e6b, #7a3ea3); }
.big-metric-card small { display: block; margin-top: 8px; font-size: 13px; font-weight: 500; opacity: 0.85; }
.section-title { font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; margin-top: 18px;}
.debt-badge {
    display: inline-block; padding: 10px 18px; border-radius: 10px;
    color: white; font-weight: 700; font-size: 15px;
}
/* Resaltado leve para las celdas clave (Último cierre y Tasa de descuento) */
[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: #fff8e1;
    border-radius: 10px;
    padding: 6px 10px 2px 10px;
}
</style>
""", unsafe_allow_html=True)

st.title("📈 Calculador de Valor Intrínseco")
st.caption("Horizonte de 10 años en 3 tramos de crecimiento (Ingreso Neto / Flujo de Caja Operativo / Flujo de Caja Libre)")

tab_calc, tab_charts = st.tabs(["📊 Calculadora", "📈 Gráficos"])

with tab_calc:
    # ------------------------------------------------------------- entrada -----
    col_a, col_b = st.columns([2, 1])
    with col_a:
        ticker = st.text_input("Stock Symbol", value="MU", placeholder="Ej: AAPL, MU, 0700.HK").strip().upper()
    with col_b:
        method = st.selectbox(
            "Método de valoración",
            ["Ingreso Neto Descontado", "Flujo de Efectivo Descontado", "Flujo de Caja Libre Descontado"],
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

        st.markdown('<p class="section-title">Datos obtenidos automáticamente (edita si es necesario)</p>', unsafe_allow_html=True)

        metric_label = {
            "Ingreso Neto Descontado": ("Ingreso Neto (actual)", data.net_income),
            "Flujo de Efectivo Descontado": ("Flujo de Caja Operativo (actual)", data.operating_cash_flow),
            "Flujo de Caja Libre Descontado": ("Flujo de Caja Libre (actual)", data.free_cash_flow),
        }[method]

        # Los montos grandes (>1 millon) se muestran y editan en millones para
        # facilitar la lectura; se re-escalan a unidades absolutas antes de calcular.
        def scaled_input(label, raw_value, help_text=None):
            raw_value = float(raw_value or 0.0)
            in_millions = abs(raw_value) >= MILLION
            display_value = raw_value / MILLION if in_millions else raw_value
            shown_label = f"{label} (en millones)" if in_millions else label
            entered = st.number_input(shown_label, value=display_value, format="%.0f" if in_millions else "%.2f", help=help_text)
            return entered * MILLION if in_millions else entered

        c1, c2, c3 = st.columns(3)
        with c1:
            company_name = st.text_input("Nombre de la compañía", value=data.company_name or ticker)
            statement_ccy = st.text_input("Moneda de estados financieros", value=data.financial_statement_currency or "USD")
            listing_ccy = st.text_input("Moneda de cotización", value=data.stock_listing_currency or "USD")
            exchange_rate = st.number_input(
                f"1 {statement_ccy} equivale a (en {listing_ccy})", value=1.0, min_value=0.0, format="%.6f"
            )
        with c2:
            base_metric = scaled_input(metric_label[0], metric_label[1])
            total_debt = scaled_input("Deuda total (corto + largo plazo)", data.total_debt)
            cash = scaled_input("Caja e inversiones a corto plazo", data.cash_and_st_investments)
            shares = scaled_input("Acciones en circulación", data.shares_outstanding)
        with c3:
            with st.container(border=True):
                last_close = st.number_input(f"Último cierre ({listing_ccy})", value=float(data.last_close_price or 0.0), format="%.2f")
            current_year = st.number_input("Año actual (último año fiscal)", value=2026, step=1)
            beta = st.number_input("Beta", value=float(data.beta or 1.0), format="%.2f")
            risk_free = st.number_input("Tasa libre de riesgo", value=float(data.risk_free_rate or 0.03), format="%.5f")
            mrp = st.number_input(
                "Prima de riesgo de mercado", value=float(data.market_risk_premium or 0.03), format="%.5f",
                help="Se obtiene automáticamente (ERP y Rf 'Current Guidance' mas recientes de Kroll para EE.UU.). Editable."
            )

        calc_discount_rate = (
            discount_rate_from_beta_table_us(beta) if data.region != "CN_HK"
            else discount_rate_from_beta(beta, risk_free, mrp)
        )
        discount_rate_source = (
            "tabla de referencia por Beta (EE.UU.)" if data.region != "CN_HK"
            else "formula Risk Free + Beta x Prima"
        )

        st.markdown('<p class="section-title">Tasas de crecimiento y descuento</p>', unsafe_allow_html=True)
        g1, g2, g3, g4, g5 = st.columns(5)
        with g1:
            growth_0_3 = st.number_input(
                "Crecimiento años 1-3",
                value=float(data.historical_growth_estimate or 0.10), format="%.4f",
                help="Sugerencia inicial basada en el CAGR historico de utilidad neta. Ajustalo con tu propio criterio o estimados de analistas."
            )
        with g2:
            growth_4_7 = st.number_input("Crecimiento años 4-7", value=float((growth_0_3 or 0.1) / 2), format="%.4f")
        with g3:
            growth_8_10 = st.number_input("Crecimiento años 8-10", value=0.04, format="%.4f")
        with g4:
            with st.container(border=True):
                discount_rate = st.number_input(
                    "Tasa de descuento (Risk Free + Beta x Prima)",
                    value=float(calc_discount_rate), format="%.4f",
                    help=f"Calculada automáticamente usando: {discount_rate_source}. Puedes sobreescribirla."
                )
        with g5:
            terminal_growth_rate = st.number_input(
                "Crecimiento perpetuo (g, año 11+)",
                value=0.025, format="%.4f",
                help="Tasa a la que se asume que el flujo crece PARA SIEMPRE despues del año 10 (valor terminal). "
                     "Se recomienda un valor conservador, cercano al crecimiento de largo plazo de la economia (2%-3%), "
                     "nunca igual a la tasa de crecimiento de los años 8-10."
            )
        if terminal_growth_rate >= discount_rate:
            st.warning(
                "El crecimiento perpetuo (g) debe ser MENOR que la tasa de descuento; de lo contrario el valor "
                "terminal no es matematicamente valido (la perpetuidad no converge). Se usara $0 de valor terminal "
                "hasta que ajustes g o la tasa de descuento."
            )

        # --- Indicadores fundamentales: Deuda Total/EBITDA, P/E, ROIC, PEG, FCF Margin ---
        debt_ratio = total_debt_to_ebitda(total_debt, data.ebitda)
        debt_label, debt_color = interpret_debt_ratio(debt_ratio)
        roic = compute_roic(data.ebit, data.effective_tax_rate, total_debt, data.total_equity, cash)
        peg = compute_peg_ratio(data.pe_ratio_ttm, growth_0_3)
        fcf_margin = compute_fcf_margin(data.free_cash_flow, data.total_revenue)

        st.markdown('<p class="section-title">Indicadores</p>', unsafe_allow_html=True)
        ratio_txt = f"{debt_ratio:.2f}x" if debt_ratio is not None else "N/D"
        pe_txt = f"{data.pe_ratio_ttm:.1f}x" if data.pe_ratio_ttm else "N/D"
        roic_txt = f"{roic*100:.1f}%" if roic is not None else "N/D"
        peg_txt = f"{peg:.2f}" if peg is not None else "N/D"
        fcf_margin_txt = f"{fcf_margin*100:.1f}%" if fcf_margin is not None else "N/D"
        st.markdown(
            f'<span class="debt-badge" style="background:{debt_color};">Deuda Total / EBITDA: {ratio_txt} — {debt_label}</span>'
            f'&nbsp;&nbsp;<span class="debt-badge" style="background:#374151;">Ratio P/E (TTM): {pe_txt}</span>'
            f'&nbsp;&nbsp;<span class="debt-badge" style="background:#0f5f7a;">ROIC: {roic_txt}</span>'
            f'&nbsp;&nbsp;<span class="debt-badge" style="background:#5a4a9e;">PEG Ratio: {peg_txt}</span>'
            f'&nbsp;&nbsp;<span class="debt-badge" style="background:#1f7a5f;">FCF Margin: {fcf_margin_txt}</span>',
            unsafe_allow_html=True,
        )
        st.caption(
            "Deuda/EBITDA — Excelente < 2x · Saludable 2x–4x · Alerta 4x–5x · Riesgosa > 5x   ·   "
            "PEG — por debajo de 1 suele considerarse atractivo, por encima de 2 costoso (usa el crecimiento de años 1-3 como estimado)   ·   "
            "ROIC y FCF Margin: mientras mas altos, mejor (compara contra el costo de capital y contra la industria)."
        )

        if st.button("💰 Calcular Valor Intrínseco", type="primary"):
            inp = ValuationInputs(
                ticker=ticker, company_name=company_name, valuation_method=method,
                financial_statement_currency=statement_ccy, stock_listing_currency=listing_ccy,
                exchange_rate=exchange_rate,
                base_metric_current=base_metric, total_debt=total_debt, cash_and_st_investments=cash,
                growth_0_3=growth_0_3, growth_4_7=growth_4_7, growth_8_10=growth_8_10,
                terminal_growth_rate=terminal_growth_rate,
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

            r1, r2, r3 = st.columns(3)
            with r1:
                st.markdown(f"""
                <div class="big-metric-card card-blue">
                    <h2>Valor Intrínseco Final por Acción ({listing_ccy})</h2>
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
            with r3:
                if data.analyst_target_mean:
                    st.markdown(f"""
                    <div class="big-metric-card card-purple">
                        <h2>Precio Objetivo de Analistas ({listing_ccy})</h2>
                        <p>{data.analyst_target_mean:,.2f}</p>
                        <small>Rango: {data.analyst_target_low:,.2f} – {data.analyst_target_high:,.2f}
                        {f" · {int(data.analyst_count)} analistas" if data.analyst_count else ""}</small>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div class="big-metric-card card-purple">
                        <h2>Precio Objetivo de Analistas</h2>
                        <p style="font-size:20px;">No disponible</p>
                    </div>
                    """, unsafe_allow_html=True)

            rec_label, rec_color = interpret_recommendation(data.analyst_recommendation_key)
            if data.analyst_target_mean:
                upside_vs_target = (data.analyst_target_mean / last_close - 1) if last_close else 0.0
                st.markdown(
                    f'<span class="debt-badge" style="background:{rec_color};">'
                    f'Consenso de analistas: {rec_label}</span>'
                    f'&nbsp;&nbsp;<span style="color:#374151;">'
                    f'Upside/Downside vs. precio objetivo: {upside_vs_target*100:+.1f}%</span>',
                    unsafe_allow_html=True,
                )

            st.caption(f"Último cierre: {last_close:,.2f} {listing_ccy}  ·  Tasa de descuento usada: {discount_rate*100:.2f}%")

            comparison_parts = [
                f"Último cierre: {last_close:,.2f}",
                f"Tu Valor Intrínseco: {result.final_intrinsic_value_per_share_listing_ccy:,.2f}",
            ]
            if data.analyst_target_mean:
                comparison_parts.append(f"Precio Objetivo de Analistas: {data.analyst_target_mean:,.2f}")
            st.info(" vs. ".join(comparison_parts) + f" ({listing_ccy})")

            with st.expander("Ver detalle del calculo"):
                d1, d2 = st.columns(2)
                with d1:
                    st.write("**Ingreso Neto antes de caja/deuda por acción**", fmt_money(result.intrinsic_value_before_cash_debt))
                    st.write("**(–) Deuda por acción**", fmt_money(result.debt_per_share))
                    st.write("**(+) Caja por acción**", fmt_money(result.cash_per_share))
                with d2:
                    st.write("**Valor Intrínseco por acción (moneda de estados financieros)**", fmt_money(result.intrinsic_value_per_share_statement_ccy))
                    st.write("**Valor presente flujos explicitos (años 1-10)**", fmt_money(result.present_value_explicit_10y))
                    st.write("**Valor terminal (perpetuidad desde año 11, sin descontar)**", fmt_money(result.terminal_value_undiscounted))
                    st.write("**Valor terminal descontado a valor presente**", fmt_money(result.terminal_value_discounted))
                    st.write("**Valor presente TOTAL (explicito + terminal)**", fmt_money(result.present_value_10y_statement_ccy))
                    if result.present_value_explicit_10y:
                        pct_terminal = result.terminal_value_discounted / result.present_value_10y_statement_ccy * 100 if result.present_value_10y_statement_ccy else 0
                        st.caption(f"El valor terminal representa ~{pct_terminal:.0f}% del valor presente total (es normal que sea la mayor parte).")

                st.write("**Proyección a 10 años (3 tramos de crecimiento)**")
                st.table({
                    "Año": [y.calendar_year for y in result.years],
                    "Tramo": [y.tranche for y in result.years],
                    "Valor proyectado": [fmt_money(y.projected_value) for y in result.years],
                    "Valor descontado": [fmt_money(y.discounted_value) for y in result.years],
                })
    else:
        st.info("Ingresa un stock symbol y presiona 'Traer datos y calcular' para comenzar.")

with tab_charts:
    st.caption(
        "Historial trimestral (hasta 10 años, sujeto a lo que Yahoo Finance tenga disponible) de "
        "Ingreso Total, Ingreso Neto, Flujo de Caja Operativo, Flujo de Caja Libre, Margen Bruto y "
        "Margen Operativo, más el precio histórico de la acción (mensual)."
    )

    default_ticker = ticker if ticker else (data.ticker if data else "MU")
    chart_ticker = st.text_input(
        "Stock Symbol", value=default_ticker, key="chart_ticker",
        placeholder="Ej: AAPL, MU, 0700.HK",
    ).strip().upper()

    cargar_graficos = st.button("📈 Cargar gráficos", type="primary", key="cargar_graficos_btn")

    if "chart_data" not in st.session_state:
        st.session_state.chart_data = None
    if "price_data" not in st.session_state:
        st.session_state.price_data = None

    if cargar_graficos and chart_ticker:
        with st.spinner(f"Descargando historial de {chart_ticker}..."):
            try:
                st.session_state.chart_data = fetch_quarterly_fundamentals(chart_ticker)
                st.session_state.price_data = fetch_price_history(chart_ticker)
            except Exception as e:
                st.session_state.chart_data = None
                st.session_state.price_data = None
                st.error(f"No se pudo descargar el historial de '{chart_ticker}': {e}")

    qdata = st.session_state.chart_data
    pdata = st.session_state.price_data

    if qdata or pdata:
        all_warnings = (qdata.get("warnings") if qdata else []) + (pdata.get("warnings") if pdata else [])
        if all_warnings:
            with st.expander("⚠️ Avisos sobre el historial disponible"):
                for w in all_warnings:
                    st.write("- " + w)

        if pdata and pdata["dates"]:
            st.markdown('<p class="section-title">Precio de la acción (cierre mensual)</p>', unsafe_allow_html=True)
            price_df = pd.DataFrame({"Precio de cierre": pdata["close"]}, index=pd.to_datetime(pdata["dates"]))
            st.line_chart(price_df)

        if qdata and qdata["quarters"]:
            idx = pd.to_datetime(qdata["quarters"])

            def _to_millions(values):
                return [v / MILLION if v is not None else None for v in values]

            st.markdown('<p class="section-title">Ingreso Total e Ingreso Neto (por trimestre, en millones)</p>', unsafe_allow_html=True)
            df_income = pd.DataFrame({
                "Ingreso Total (M)": _to_millions(qdata["total_revenue"]),
                "Ingreso Neto (M)": _to_millions(qdata["net_income"]),
            }, index=idx)
            st.line_chart(df_income)

            st.markdown('<p class="section-title">Flujo de Caja Operativo y Flujo de Caja Libre (por trimestre, en millones)</p>', unsafe_allow_html=True)
            df_cf = pd.DataFrame({
                "Flujo de Caja Operativo (M)": _to_millions(qdata["operating_cash_flow"]),
                "Flujo de Caja Libre (M)": _to_millions(qdata["free_cash_flow"]),
            }, index=idx)
            st.line_chart(df_cf)

            st.markdown('<p class="section-title">Margen Bruto y Margen Operativo (por trimestre)</p>', unsafe_allow_html=True)
            df_margins = pd.DataFrame({
                "Margen Bruto": [v * 100 if v is not None else None for v in qdata["gross_margin"]],
                "Margen Operativo": [v * 100 if v is not None else None for v in qdata["operating_margin"]],
            }, index=idx)
            st.line_chart(df_margins)
            st.caption("Márgenes expresados en porcentaje (%).")
        elif qdata is not None:
            st.warning("No se encontraron datos trimestrales para graficar este ticker.")
    else:
        st.info("Escribe un stock symbol y presiona 'Cargar gráficos' para comenzar.")

