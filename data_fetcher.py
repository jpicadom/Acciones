"""
Obtiene automaticamente, a partir del "stock symbol", los datos que en la
hoja de Excel original iban en las celdas de fondo blanco (las que el
usuario llenaba a mano). Usa la libreria `yfinance` (datos de Yahoo Finance).

Todo lo que no se pueda obtener automaticamente se deja en None para que la
app se lo pida al usuario (igual que una celda blanca vacia en Excel).
"""
from dataclasses import dataclass
from typing import Optional, Tuple
import datetime
import functools
import io

import pandas as pd
import requests
import yfinance as yf


# --------------------------------------------------------------------------
# Prima de riesgo de mercado (IMRP) y tasa libre de riesgo (Rf) de EE.UU.
# --------------------------------------------------------------------------
# market-risk-premia.com/us.html (la pagina sugerida) muestra estos datos en
# un grafico que se genera con JavaScript, por lo que no se puede leer con un
# request HTTP normal (el HTML que llega no trae los numeros, solo el grafico
# vacio). En su lugar se usa la tabla de "Implied Equity Risk Premiums" de
# Aswath Damodaran (NYU Stern) -- la referencia academica/practica estandar
# para el IMRP de EE.UU., publicada en HTML plano y facil de leer por codigo:
#   https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histimpl.html
# De ahi se toman, de la ULTIMA fila con datos: la prima implicita ("Implied
# ERP (FCFE)") como Market Risk Premium, y la tasa del bono del Tesoro a 10
# anios ("T.Bond Rate") como Risk Free Rate.
DAMODARAN_IMPLIED_ERP_URL = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histimpl.html"

# Valores de respaldo (los que traia originalmente la hoja de calculo) por si
# la fuente en linea no esta disponible en el momento de usar la app.
FALLBACK_ASSUMPTIONS = {
    "US": {"risk_free_rate": 0.02958, "market_risk_premium": 0.0301,
           "source": "market-risk-premia.com/us.html (valor de respaldo, sin conexion)"},
    "CN_HK": {"risk_free_rate": 0.02604, "market_risk_premium": 0.07412,
              "source": "market-risk-premia.com/hk.html (valor de respaldo, sin conexion)"},
}

# Se mantiene el nombre anterior por compatibilidad con el resto del codigo.
DEFAULT_ASSUMPTIONS = FALLBACK_ASSUMPTIONS


def _pct_to_float(value) -> Optional[float]:
    try:
        return float(str(value).replace("%", "").replace(",", ".").strip()) / 100
    except (ValueError, TypeError):
        return None


@functools.lru_cache(maxsize=1)
def fetch_us_implied_erp_and_rf() -> Tuple[Optional[float], Optional[float], Optional[str], str]:
    """Trae el IMRP y el Rf mas recientes de EE.UU. desde la tabla de Damodaran.

    Devuelve (risk_free_rate, market_risk_premium, anio_del_dato, fuente).
    Si algo falla, devuelve (None, None, None, mensaje_de_error) para que el
    llamador decida usar el valor de respaldo.
    """
    try:
        resp = requests.get(DAMODARAN_IMPLIED_ERP_URL, timeout=15,
                             headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))
    except Exception as e:
        return None, None, None, f"No se pudo descargar/leer {DAMODARAN_IMPLIED_ERP_URL}: {e}"

    target = None
    for t in tables:
        cols = [str(c) for c in t.columns]
        if any("ERP" in c for c in cols) and any("Bond" in c for c in cols):
            target = t
            break
    if target is None:
        return None, None, None, "No se encontro la tabla de IMRP/Rf en la pagina de Damodaran"

    erp_col = next(c for c in target.columns if "ERP" in str(c))
    bond_col = next(c for c in target.columns if "Bond" in str(c))
    year_col = next((c for c in target.columns if str(c).strip().lower() == "year"), target.columns[0])

    # Ultima fila que tenga tanto ERP como T.Bond Rate validos (la mas reciente)
    valid = target[[year_col, bond_col, erp_col]].copy()
    valid["_erp"] = valid[erp_col].apply(_pct_to_float)
    valid["_rf"] = valid[bond_col].apply(_pct_to_float)
    valid = valid.dropna(subset=["_erp", "_rf"])
    if valid.empty:
        return None, None, None, "La tabla de Damodaran no trae filas completas de ERP/T.Bond Rate"

    last = valid.iloc[-1]
    try:
        year = str(int(float(last[year_col])))
    except (ValueError, TypeError):
        year = str(last[year_col])
    return float(last["_rf"]), float(last["_erp"]), year, DAMODARAN_IMPLIED_ERP_URL


def get_us_market_assumptions() -> dict:
    """Punto de entrada usado por la app: intenta traer los valores mas
    recientes de IMRP/Rf de EE.UU.; si falla, usa el valor de respaldo."""
    rf, erp, year, source = fetch_us_implied_erp_and_rf()
    if rf is not None and erp is not None:
        return {
            "risk_free_rate": rf,
            "market_risk_premium": erp,
            "source": f"{source} (dato mas reciente disponible: {year})",
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
    beta: Optional[float] = None
    risk_free_rate: Optional[float] = None
    market_risk_premium: Optional[float] = None
    historical_growth_estimate: Optional[float] = None  # CAGR de utilidad neta, ultimos anios disponibles
    scale: str = "unidades"  # aviso de unidades ("unidades" o "millones") para mostrar en la UI
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
    except Exception as e:
        data.warnings.append(f"No se pudo leer el balance general: {e}")

    net_income_history = []
    try:
        fin = tk.financials
        if fin is not None and not fin.empty and "Net Income" in fin.index:
            row = fin.loc["Net Income"]
            net_income_history = [float(v) for v in row.values]
            data.net_income = net_income_history[0]
    except Exception as e:
        data.warnings.append(f"No se pudo leer el estado de resultados: {e}")

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
