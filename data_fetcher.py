"""
Obtiene automaticamente, a partir del "stock symbol", los datos que en la
hoja de Excel original iban en las celdas de fondo blanco (las que el
usuario llenaba a mano). Usa la libreria `yfinance` (datos de Yahoo Finance).

Todo lo que no se pueda obtener automaticamente se deja en None para que la
app se lo pida al usuario (igual que una celda blanca vacia en Excel).
"""
from dataclasses import dataclass
from typing import Optional
import datetime

import yfinance as yf


# Prima de riesgo de mercado y tasa libre de riesgo por defecto (igual que las
# celdas E73/E74 y L73/L74 de la hoja original). El usuario puede sobreescribirlas.
DEFAULT_ASSUMPTIONS = {
    "US": {"risk_free_rate": 0.02958, "market_risk_premium": 0.0301,
           "source": "market-risk-premia.com/us.html"},
    "CN_HK": {"risk_free_rate": 0.02604, "market_risk_premium": 0.07412,
              "source": "market-risk-premia.com/hk.html"},
}


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

    # --- Tasa libre de riesgo / prima de riesgo por defecto segun region ---
    exch = _safe_get(info, "exchange", "fullExchangeName") or ""
    region_key = "CN_HK" if any(x in str(exch).upper() for x in ["HKG", "HONG KONG", "SHANGHAI", "SHENZHEN"]) else "US"
    assumptions = DEFAULT_ASSUMPTIONS[region_key]
    data.risk_free_rate = assumptions["risk_free_rate"]
    data.market_risk_premium = assumptions["market_risk_premium"]

    if data.shares_outstanding:
        # Escalamos utilidad/deuda/caja a la misma unidad que las acciones (unidades absolutas)
        data.scale = "unidades"

    return data
