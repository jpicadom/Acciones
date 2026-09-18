"""
Obtiene automáticamente, a partir del "stock symbol", los datos que en la
hoja de Excel original iban en las celdas de fondo blanco (las que el
usuario llenaba a mano). Usa la libreria `yfinance` (datos de Yahoo Finance).

Todo lo que no se pueda obtener automáticamente se deja en None para que la
app se lo pida al usuario (igual que una celda blanca vacia en Excel).
"""
from dataclasses import dataclass
from typing import Optional, Tuple
import datetime
import functools
import io
import re

import requests
from pypdf import PdfReader
import pandas as pd
import yfinance as yf


# --------------------------------------------------------------------------
# Prima de riesgo de mercado (ERP) y tasa libre de riesgo (Rf) de EE.UU.
# --------------------------------------------------------------------------
# Fuente: Kroll (antes Duff & Phelps) publica su "Recommended U.S. Equity
# Risk Premium and Corresponding Risk-free Rate", el estandar mas usado en
# valoración profesional en EE.UU. Los valores actuales solo aparecen en un
# grafico/SVG en la pagina web, pero Kroll tambien publica una tabla
# historica en PDF (texto real, no imagen) que sí se puede leer por codigo:
#   https://www.kroll.com/en/reports/cost-of-capital/recommended-us-equity-risk-premium-and-corresponding-risk-free-rates
KROLL_PAGE_URL = (
    "https://www.kroll.com/en/reports/cost-of-capital/"
    "recommended-us-equity-risk-premium-and-corresponding-risk-free-rates"
)
KROLL_PDF_TABLE_URL = (
    "https://edge.sitecorecloud.io/krollllc17bf0-kroll6fee-proda464-0e9b/"
    "media/cost-of-capital/kroll-us-erp-rf-table.pdf"
)

# Valores de respaldo (los que traia originalmente la hoja de calculo) por si
# la fuente en linea no esta disponible en el momento de usar la app.
FALLBACK_ASSUMPTIONS = {
    "US": {"risk_free_rate": 0.02958, "market_risk_premium": 0.0301,
           "source": f"{KROLL_PAGE_URL} (valor de respaldo, sin conexion)"},
    "CN_HK": {"risk_free_rate": 0.02604, "market_risk_premium": 0.07412,
              "source": "market-risk-premia.com/hk.html (valor de respaldo, sin conexion)"},
}

# Se mantiene el nombre anterior por compatibilidad con el resto del codigo.
DEFAULT_ASSUMPTIONS = FALLBACK_ASSUMPTIONS


@functools.lru_cache(maxsize=1)
def fetch_us_implied_erp_and_rf() -> Tuple[Optional[float], Optional[float], Optional[str], str]:
    """Trae el ERP y el Rf recomendados MAS RECIENTES de EE.UU. desde la
    tabla en PDF que publica Kroll ("Current Guidance", primera fila de la
    tabla = la vigencia mas reciente).

    Devuelve (risk_free_rate, market_risk_premium, vigente_desde, fuente).
    Si algo falla, devuelve (None, None, None, mensaje_de_error) para que el
    llamador decida usar el valor de respaldo.
    """
    try:
        resp = requests.get(KROLL_PDF_TABLE_URL, timeout=20,
                             headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        reader = PdfReader(io.BytesIO(resp.content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        return None, None, None, f"No se pudo descargar/leer {KROLL_PDF_TABLE_URL}: {e}"

    # La tabla esta ordenada de la vigencia mas reciente a la mas antigua.
    # La fila vigente actual siempre incluye "UNTIL FURTHER NOTICE".
    match = re.search(
        r"([A-Z][a-z]+ \d{1,2},\s*\d{4})\s*[−-]\s*UNTIL FURTHER NOTICE.*?"
        r"(\d+\.\d+)\*?\s+(\d+\.\d+)\s+\w",
        text, re.DOTALL,
    )
    if not match:
        return None, None, None, "No se encontro la fila 'UNTIL FURTHER NOTICE' en el PDF de Kroll"

    effective_date, rf_str, erp_str = match.group(1), match.group(2), match.group(3)
    try:
        rf = float(rf_str) / 100
        erp = float(erp_str) / 100
    except ValueError:
        return None, None, None, f"No se pudieron convertir los valores extraidos del PDF ({rf_str}, {erp_str})"

    return rf, erp, effective_date, KROLL_PDF_TABLE_URL


def get_us_market_assumptions() -> dict:
    """Punto de entrada usado por la app: intenta traer los valores mas
    recientes de ERP/Rf de EE.UU. (Kroll); si falla, usa el valor de
    respaldo."""
    rf, erp, effective_date, source = fetch_us_implied_erp_and_rf()
    if rf is not None and erp is not None:
        return {
            "risk_free_rate": rf,
            "market_risk_premium": erp,
            "source": f"{source} (vigente desde {effective_date})",
            "live": True,
        }
    fallback = dict(FALLBACK_ASSUMPTIONS["US"])
    fallback["live"] = False
    fallback["fetch_error"] = source  # aqui 'source' trae el mensaje de error
    return fallback


@dataclass
class FetchedData:
    ticker: str
    company_name: Optional[str] = None
    financial_statement_currency: Optional[str] = None
    stock_listing_currency: Optional[str] = None
    last_close_price: Optional[float] = None
    shares_outstanding: Optional[float] = None  # en unidades absolutas (no millones)
    total_debt: Optional[float] = None
    cash_and_st_investments: Optional[float] = None
    net_income: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    free_cash_flow: Optional[float] = None
    ebitda: Optional[float] = None
    region: str = "US"  # "US" o "CN_HK" -- determina que tabla/formula de tasa de descuento usar
    beta: Optional[float] = None
    risk_free_rate: Optional[float] = None
    market_risk_premium: Optional[float] = None
    historical_growth_estimate: Optional[float] = None  # CAGR de utilidad neta, ultimos anios disponibles
    scale: str = "unidades"  # aviso de unidades ("unidades" o "millones") para mostrar en la UI
    # --- Opinion de analistas ---
    analyst_target_mean: Optional[float] = None
    analyst_target_median: Optional[float] = None
    analyst_target_high: Optional[float] = None
    analyst_target_low: Optional[float] = None
    analyst_count: Optional[int] = None
    analyst_recommendation_key: Optional[str] = None    # "strong_buy" | "buy" | "hold" | "sell" | "strong_sell"
    analyst_recommendation_mean: Optional[float] = None  # escala 1 (compra fuerte) a 5 (venta fuerte)
    pe_ratio_ttm: Optional[float] = None  # Precio / Beneficio (Trailing Twelve Months)
    total_revenue: Optional[float] = None
    ebit: Optional[float] = None
    effective_tax_rate: Optional[float] = None
    total_equity: Optional[float] = None
    warnings: list = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


def _safe_get(d: dict, *keys):
    for k in keys:
        if d and k in d and d[k] is not None:
            return d[k]
    return None


def _cagr(values):
    """values: lista de valores anuales, del mas reciente al mas antiguo."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2 or vals[-1] <= 0 or vals[0] <= 0:
        return None
    n = len(vals) - 1
    try:
        return (vals[0] / vals[-1]) ** (1 / n) - 1
    except Exception:
        return None


def fetch_stock_data(ticker_symbol: str) -> FetchedData:
    data = FetchedData(ticker=ticker_symbol.upper())
    tk = yf.Ticker(data.ticker)

    # --- Info general ---
    try:
        info = tk.info or {}
    except Exception as e:
        info = {}
        data.warnings.append(f"No se pudo leer 'info' de Yahoo Finance: {e}")

    data.company_name = _safe_get(info, "longName", "shortName")
    data.financial_statement_currency = _safe_get(info, "financialCurrency")
    data.stock_listing_currency = _safe_get(info, "currency")
    data.last_close_price = _safe_get(info, "currentPrice", "previousClose", "regularMarketPreviousClose")
    data.shares_outstanding = _safe_get(info, "sharesOutstanding")
    data.beta = _safe_get(info, "beta")
    data.ebitda = _safe_get(info, "ebitda")

    # --- Opinion de analistas ---
    data.analyst_target_mean = _safe_get(info, "targetMeanPrice")
    data.analyst_target_median = _safe_get(info, "targetMedianPrice")
    data.analyst_target_high = _safe_get(info, "targetHighPrice")
    data.analyst_target_low = _safe_get(info, "targetLowPrice")
    data.analyst_count = _safe_get(info, "numberOfAnalystOpinions")
    data.analyst_recommendation_key = _safe_get(info, "recommendationKey")
    data.analyst_recommendation_mean = _safe_get(info, "recommendationMean")
    if data.analyst_target_mean is None:
        data.warnings.append("No hay precio objetivo de analistas disponible para este ticker.")

    # --- Ratio P/E (Precio / Beneficio TTM) ---
    data.pe_ratio_ttm = _safe_get(info, "trailingPE")

    total_debt = _safe_get(info, "totalDebt")
    cash = _safe_get(info, "totalCash")
    if total_debt is not None:
        data.total_debt = total_debt
    if cash is not None:
        data.cash_and_st_investments = cash

    # --- Estados financieros (respaldo / mayor precision que 'info') ---
    try:
        bs = tk.balance_sheet
        if bs is not None and not bs.empty:
            latest_col = bs.columns[0]
            if data.total_debt is None:
                for label in ["Total Debt", "TotalDebt"]:
                    if label in bs.index:
                        data.total_debt = float(bs.loc[label, latest_col])
                        break
            if data.cash_and_st_investments is None:
                for label in ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"]:
                    if label in bs.index:
                        data.cash_and_st_investments = float(bs.loc[label, latest_col])
                        break
            for label in ["Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity"]:
                if label in bs.index:
                    data.total_equity = float(bs.loc[label, latest_col])
                    break
    except Exception as e:
        data.warnings.append(f"No se pudo leer el balance general: {e}")

    net_income_history = []
    try:
        fin = tk.financials
        if fin is not None and not fin.empty and "Net Income" in fin.index:
            row = fin.loc["Net Income"]
            net_income_history = [float(v) for v in row.values]
            data.net_income = net_income_history[0]
        if data.ebitda is None and fin is not None and not fin.empty:
            if "EBITDA" in fin.index:
                data.ebitda = float(fin.loc["EBITDA"].iloc[0])
            elif "EBIT" in fin.index and "Reconciled Depreciation" in fin.index:
                data.ebitda = float(fin.loc["EBIT"].iloc[0]) + float(fin.loc["Reconciled Depreciation"].iloc[0])
            elif "Operating Income" in fin.index and "Reconciled Depreciation" in fin.index:
                data.ebitda = float(fin.loc["Operating Income"].iloc[0]) + float(fin.loc["Reconciled Depreciation"].iloc[0])
        if fin is not None and not fin.empty:
            for label in ["EBIT", "Operating Income"]:
                if label in fin.index:
                    data.ebit = float(fin.loc[label].iloc[0])
                    break
            for label in ["Total Revenue", "Operating Revenue"]:
                if label in fin.index:
                    data.total_revenue = float(fin.loc[label].iloc[0])
                    break
            if "Pretax Income" in fin.index and "Tax Provision" in fin.index:
                pretax = float(fin.loc["Pretax Income"].iloc[0])
                tax = float(fin.loc["Tax Provision"].iloc[0])
                if pretax:
                    data.effective_tax_rate = tax / pretax
    except Exception as e:
        data.warnings.append(f"No se pudo leer el estado de resultados: {e}")

    if data.total_revenue is None:
        data.total_revenue = _safe_get(info, "totalRevenue")

    if data.effective_tax_rate is None:
        data.effective_tax_rate = 0.21  # tasa corporativa estatutaria de EE.UU. (respaldo)
        data.warnings.append(
            "No se pudo calcular la tasa de impuesto efectiva de la empresa; se uso 21% (tasa "
            "corporativa estatutaria de EE.UU.) como respaldo para calcular el ROIC."
        )

    if data.ebitda is None:
        data.warnings.append("No se pudo obtener el EBITDA; el indicador Deuda Total/EBITDA no estara disponible.")

    try:
        cf = tk.cashflow
        if cf is not None and not cf.empty:
            if "Operating Cash Flow" in cf.index:
                data.operating_cash_flow = float(cf.loc["Operating Cash Flow"].iloc[0])
            if "Free Cash Flow" in cf.index:
                data.free_cash_flow = float(cf.loc["Free Cash Flow"].iloc[0])
            elif data.operating_cash_flow is not None and "Capital Expenditure" in cf.index:
                capex = float(cf.loc["Capital Expenditure"].iloc[0])
                data.free_cash_flow = data.operating_cash_flow + capex  # capex ya viene negativo
    except Exception as e:
        data.warnings.append(f"No se pudo leer el flujo de caja: {e}")

    # --- Estimacion de tasa de crecimiento historica (referencia, no un dato del modelo) ---
    data.historical_growth_estimate = _cagr(net_income_history[:6])

    # --- Tasa libre de riesgo / prima de riesgo de mercado ---
    exch = _safe_get(info, "exchange", "fullExchangeName") or ""
    is_cn_hk = any(x in str(exch).upper() for x in ["HKG", "HONG KONG", "SHANGHAI", "SHENZHEN"])
    data.region = "CN_HK" if is_cn_hk else "US"

    if is_cn_hk:
        # Damodaran solo cubre EE.UU.; para China/HK se mantiene el valor de
        # referencia original de la hoja de calculo.
        assumptions = FALLBACK_ASSUMPTIONS["CN_HK"]
        data.risk_free_rate = assumptions["risk_free_rate"]
        data.market_risk_premium = assumptions["market_risk_premium"]
    else:
        assumptions = get_us_market_assumptions()
        data.risk_free_rate = assumptions["risk_free_rate"]
        data.market_risk_premium = assumptions["market_risk_premium"]
        if not assumptions.get("live", True):
            data.warnings.append(
                "No se pudo traer el IMRP/Rf mas reciente en linea; se uso el valor de "
                f"respaldo. Detalle: {assumptions.get('fetch_error')}"
            )

    if data.shares_outstanding:
        # Escalamos utilidad/deuda/caja a la misma unidad que las acciones (unidades absolutas)
        data.scale = "unidades"

    return data


# --------------------------------------------------------------------------
# Historicos para graficos: fundamentales trimestrales y precio
# --------------------------------------------------------------------------
def fetch_quarterly_fundamentals(ticker_symbol: str, max_years: int = 10) -> dict:
    """Trae, por trimestre, Ingreso Total, Ingreso Neto, Flujo de Caja
    Operativo, Flujo de Caja Libre, Margen Bruto y Margen Operativo.

    Yahoo Finance solo conserva ~4-5 años de historial trimestral de forma
    gratuita (no 10 años completos); la funcion trae todo lo disponible,
    hasta 'max_years' años, y avisa si hay menos historial del solicitado.

    Devuelve un dict con listas paralelas ordenadas cronologicamente
    (la mas antigua primero) bajo la clave 'quarters' (fechas) y una clave
    por metrica, mas 'warnings' (lista de avisos).
    """
    result = {
        "quarters": [], "total_revenue": [], "net_income": [],
        "operating_cash_flow": [], "free_cash_flow": [],
        "gross_margin": [], "operating_margin": [], "warnings": [],
    }
    tk = yf.Ticker(ticker_symbol.upper())

    try:
        qfin = tk.quarterly_financials
    except Exception as e:
        qfin = None
        result["warnings"].append(f"No se pudo leer el estado de resultados trimestral: {e}")
    try:
        qcf = tk.quarterly_cashflow
    except Exception as e:
        qcf = None
        result["warnings"].append(f"No se pudo leer el flujo de caja trimestral: {e}")

    if qfin is None or qfin.empty:
        result["warnings"].append("Yahoo Finance no reporta estados de resultados trimestrales para este ticker.")
        return result

    # Columnas = fechas de cierre de cada trimestre, mas reciente primero.
    all_dates = list(qfin.columns)
    cutoff = None
    try:
        cutoff = all_dates[0] - pd.DateOffset(years=max_years)
    except Exception:
        cutoff = None

    dates_chrono = sorted(all_dates)  # mas antigua primero
    if cutoff is not None:
        dates_chrono = [d for d in dates_chrono if d >= cutoff]

    span_years = None
    if dates_chrono:
        span_years = (dates_chrono[-1] - dates_chrono[0]).days / 365.25
    if span_years is not None and span_years < max_years - 0.5:
        result["warnings"].append(
            f"Yahoo Finance solo tiene ~{span_years:.1f} años de historial trimestral disponible "
            f"para este ticker (se pidieron {max_years})."
        )

    def _row(df, labels, col):
        if df is None:
            return None
        for label in labels:
            if label in df.index and col in df.columns:
                val = df.loc[label, col]
                return float(val) if val is not None else None
        return None

    for col in dates_chrono:
        revenue = _row(qfin, ["Total Revenue", "Operating Revenue"], col)
        net_income = _row(qfin, ["Net Income"], col)
        gross_profit = _row(qfin, ["Gross Profit"], col)
        operating_income = _row(qfin, ["Operating Income"], col)
        ocf = _row(qcf, ["Operating Cash Flow"], col)
        fcf = _row(qcf, ["Free Cash Flow"], col)
        if fcf is None and ocf is not None:
            capex = _row(qcf, ["Capital Expenditure"], col)
            if capex is not None:
                fcf = ocf + capex  # capex ya viene negativo en yfinance

        result["quarters"].append(col.date() if hasattr(col, "date") else col)
        result["total_revenue"].append(revenue)
        result["net_income"].append(net_income)
        result["operating_cash_flow"].append(ocf)
        result["free_cash_flow"].append(fcf)
        result["gross_margin"].append((gross_profit / revenue) if (gross_profit is not None and revenue) else None)
        result["operating_margin"].append((operating_income / revenue) if (operating_income is not None and revenue) else None)

    if not result["quarters"]:
        result["warnings"].append("No se encontraron trimestres con datos validos para graficar.")

    return result


def fetch_price_history(ticker_symbol: str, years: int = 10) -> dict:
    """Trae el precio de cierre historico (mensual) de los ultimos 'years'
    años. Devuelve {'dates': [...], 'close': [...], 'warnings': [...]}."""
    result = {"dates": [], "close": [], "warnings": []}
    tk = yf.Ticker(ticker_symbol.upper())
    try:
        hist = tk.history(period=f"{years}y", interval="1mo", auto_adjust=False)
    except Exception as e:
        result["warnings"].append(f"No se pudo leer el precio historico: {e}")
        return result

    if hist is None or hist.empty:
        result["warnings"].append("Yahoo Finance no devolvio precios historicos para este ticker.")
        return result

    result["dates"] = [d.date() if hasattr(d, "date") else d for d in hist.index]
    result["close"] = [float(v) for v in hist["Close"].values]

    span_years = (hist.index[-1] - hist.index[0]).days / 365.25
    if span_years < years - 0.5:
        result["warnings"].append(
            f"Yahoo Finance solo tiene ~{span_years:.1f} años de historial de precio disponible "
            f"para este ticker (se pidieron {years})."
        )
    return result
