"""
Motor de valoración (Valor Intrínseco).

Horizonte de proyeccion: 10 años, en 3 tramos de crecimiento
(el "Año 0" es el año actual / base, sin crecer todavia):
  - Años 1 a 3:   growth_0_3
  - Años 4 a 7:   growth_4_7
  - Años 8 a 10:  growth_8_10
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ValuationInputs:
    ticker: str
    company_name: str
    valuation_method: str  # "Ingreso Neto Descontado" | "Flujo de Efectivo Descontado" | "Flujo de Caja Libre Descontado"

    financial_statement_currency: str
    stock_listing_currency: str
    exchange_rate: float  # 1 unidad de financial_statement_currency = exchange_rate unidades de stock_listing_currency

    base_metric_current: float   # Año 0: Net Income / Operating CF / Free CF (periodo actual)
    total_debt: float
    cash_and_st_investments: float

    growth_0_3: float    # tasa de crecimiento años 1-3
    growth_4_7: float    # tasa de crecimiento años 4-7
    growth_8_10: float   # tasa de crecimiento años 8-10
    terminal_growth_rate: float  # g: crecimiento perpetuo despues del año 10 (conservador, ej. 2-3%)

    shares_outstanding: float
    discount_rate: float
    current_year: int          # Año 0
    last_close_price: float    # en stock_listing_currency

    beta: Optional[float] = None
    risk_free_rate: Optional[float] = None
    market_risk_premium: Optional[float] = None


@dataclass
class ProjectedYear:
    year_offset: int          # 1..10 (años despues del Año 0)
    calendar_year: int
    tranche: str              # "Años 1-3" | "Años 4-7" | "Años 8-10"
    projected_value: float
    discount_factor: float
    discounted_value: float


@dataclass
class ValuationResult:
    years: list = field(default_factory=list)  # list[ProjectedYear], años 1 a 10

    present_value_explicit_10y: float = 0.0             # suma de los 10 años descontados (sin valor terminal)
    terminal_value_undiscounted: float = 0.0             # valor terminal al final del año 10 (sin descontar)
    terminal_value_discounted: float = 0.0               # valor terminal traido a valor presente
    present_value_10y_statement_ccy: float = 0.0         # explicito + valor terminal descontado (total)
    intrinsic_value_before_cash_debt: float = 0.0        # PV / acciones
    debt_per_share: float = 0.0
    cash_per_share: float = 0.0
    intrinsic_value_per_share_statement_ccy: float = 0.0
    final_intrinsic_value_per_share_listing_ccy: float = 0.0   # <-- CLAVE
    discount_premium: float = 0.0                               # <-- CLAVE


def discount_rate_from_beta(beta: float, risk_free_rate: float, market_risk_premium: float) -> float:
    """Discount Rate = Risk Free Rate + Beta x Market Risk Premium."""
    return risk_free_rate + beta * market_risk_premium


# Tabla de referencia (EE.UU.): tasa de descuento por rango de Beta.
# Busqueda tipo VLOOKUP aproximado -- se usa la tasa del punto de la tabla
# igual o inmediatamente inferior al Beta de la acción (sin interpolar).
US_BETA_DISCOUNT_TABLE = [
    (0.80, 0.054),  # "Less than 0.80" -> 5.4%
    (1.0, 0.060),
    (1.1, 0.063),
    (1.2, 0.066),
    (1.3, 0.069),
    (1.4, 0.072),
    (1.5, 0.075),
    (1.6, 0.078),  # "More than 1.6" -> 7.8%
]


def discount_rate_from_beta_table_us(beta: Optional[float]) -> float:
    """Tasa de descuento para acciones de EE.UU. segun la tabla de
    referencia por Beta (ver US_BETA_DISCOUNT_TABLE)."""
    if beta is None:
        beta = 1.0
    if beta < US_BETA_DISCOUNT_TABLE[0][0]:
        return US_BETA_DISCOUNT_TABLE[0][1]
    if beta >= US_BETA_DISCOUNT_TABLE[-1][0]:
        return US_BETA_DISCOUNT_TABLE[-1][1]
    rate = US_BETA_DISCOUNT_TABLE[0][1]
    for bp_beta, bp_rate in US_BETA_DISCOUNT_TABLE:
        if beta >= bp_beta:
            rate = bp_rate
        else:
            break
    return rate


def compute_intrinsic_value(inp: ValuationInputs) -> ValuationResult:
    r = inp.discount_rate
    res = ValuationResult()

    labels = ["Años 1-3"] * 3 + ["Años 4-7"] * 4 + ["Años 8-10"] * 3
    growth_by_offset = (
        [inp.growth_0_3] * 3 + [inp.growth_4_7] * 4 + [inp.growth_8_10] * 3
    )

    prev = inp.base_metric_current
    for offset in range(1, 11):
        g = growth_by_offset[offset - 1]
        prev = prev * (1 + g)
        factor = (1 / (1 + r)) ** offset
        discounted = prev * factor
        res.years.append(ProjectedYear(
            year_offset=offset,
            calendar_year=inp.current_year + offset,
            tranche=labels[offset - 1],
            projected_value=prev,
            discount_factor=factor,
            discounted_value=discounted,
        ))

    res.present_value_explicit_10y = sum(y.discounted_value for y in res.years)

    # --- Valor terminal (perpetuidad de Gordon) ---
    # Asume que, despues del año 10, el flujo crece a una tasa perpetua
    # sostenible 'g' (normalmente conservadora, ej. 2-3%), para siempre:
    #   TV_año10 = Flujo_año10 x (1+g) / (r-g)
    # y se trae a valor presente con el mismo factor de descuento del año 10.
    r_minus_g = r - inp.terminal_growth_rate
    last_year_value = res.years[-1].projected_value
    if r_minus_g > 0:
        res.terminal_value_undiscounted = last_year_value * (1 + inp.terminal_growth_rate) / r_minus_g
        res.terminal_value_discounted = res.terminal_value_undiscounted * res.years[-1].discount_factor
    else:
        # Formula inestable/indefinida si g >= r (perpetuidad no converge).
        res.terminal_value_undiscounted = 0.0
        res.terminal_value_discounted = 0.0

    res.present_value_10y_statement_ccy = res.present_value_explicit_10y + res.terminal_value_discounted

    shares = inp.shares_outstanding
    res.intrinsic_value_before_cash_debt = (
        res.present_value_10y_statement_ccy / shares if shares else 0.0
    )
    res.debt_per_share = (inp.total_debt / shares) if shares else 0.0
    res.cash_per_share = (inp.cash_and_st_investments / shares) if shares else 0.0

    res.intrinsic_value_per_share_statement_ccy = (
        res.intrinsic_value_before_cash_debt - res.debt_per_share + res.cash_per_share
    )

    res.final_intrinsic_value_per_share_listing_ccy = (
        res.intrinsic_value_per_share_statement_ccy * inp.exchange_rate
    )

    res.discount_premium = (
        (inp.last_close_price / res.final_intrinsic_value_per_share_listing_ccy) - 1
        if res.final_intrinsic_value_per_share_listing_ccy else 0.0
    )

    return res


# --------------------------------------------------------------------------
# Indicador de apalancamiento: Deuda Neta / EBITDA
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Indicador de apalancamiento: Deuda Total / EBITDA
# --------------------------------------------------------------------------
def total_debt_to_ebitda(total_debt: float, ebitda: float) -> Optional[float]:
    """Deuda Total / EBITDA del último periodo. Devuelve None si el EBITDA no
    es valido (cero, negativo o desconocido) -- el indicador no aplica."""
    if not ebitda or ebitda <= 0:
        return None
    return total_debt / ebitda


def interpret_debt_ratio(ratio: Optional[float]) -> tuple:
    """Devuelve (etiqueta, color_css) segun el umbral de Deuda Total/EBITDA."""
    if ratio is None:
        return "No disponible", "#6b7280"
    if ratio < 2:
        return "Excelente", "#0f8f4f"
    if ratio < 4:
        return "Saludable", "#2f9e44"
    if ratio <= 5:
        return "Alerta", "#e08e0b"
    return "Riesgosa", "#c0392b"


# --------------------------------------------------------------------------
# Interpretacion de la recomendacion de analistas
# --------------------------------------------------------------------------
_RECOMMENDATION_LABELS = {
    "strong_buy": ("Compra Fuerte", "#0f5132"),
    "buy": ("Compra", "#2f9e44"),
    "hold": ("Mantener", "#e08e0b"),
    "sell": ("Venta", "#c0392b"),
    "strong_sell": ("Venta Fuerte", "#7a1f1f"),
}


def interpret_recommendation(key: Optional[str]) -> tuple:
    """Traduce la clave de recomendacion de yfinance (ej. 'buy') a una
    etiqueta en español y un color. Devuelve ('Sin datos', gris) si no hay
    informacion disponible."""
    if not key:
        return "Sin datos", "#6b7280"
    return _RECOMMENDATION_LABELS.get(key.lower(), ("Sin datos", "#6b7280"))


# --------------------------------------------------------------------------
# ROIC (Return on Invested Capital)
# --------------------------------------------------------------------------
def compute_roic(ebit: Optional[float], effective_tax_rate: Optional[float],
                  total_debt: Optional[float], total_equity: Optional[float],
                  cash_and_st_investments: Optional[float]) -> Optional[float]:
    """ROIC = NOPAT / Capital Invertido
    NOPAT (utilidad operativa neta despues de impuestos) = EBIT x (1 - tasa de impuesto)
    Capital Invertido = Deuda Total + Patrimonio - Caja e inversiones a corto plazo
    Devuelve None si falta algun dato necesario o el capital invertido no es valido."""
    if ebit is None or effective_tax_rate is None or total_debt is None or total_equity is None:
        return None
    invested_capital = total_debt + total_equity - (cash_and_st_investments or 0.0)
    if invested_capital <= 0:
        return None
    nopat = ebit * (1 - effective_tax_rate)
    return nopat / invested_capital


# --------------------------------------------------------------------------
# PEG Ratio (P/E ajustado por crecimiento)
# --------------------------------------------------------------------------
def compute_peg_ratio(pe_ratio_ttm: Optional[float], growth_rate: Optional[float]) -> Optional[float]:
    """PEG = P/E (TTM) / (tasa de crecimiento esperada, en %).
    Se usa la tasa de crecimiento de los años 1-3 del modelo como estimado
    de crecimiento cercano. Devuelve None si el P/E o el crecimiento no son
    validos (crecimiento <= 0 hace que el PEG no tenga una lectura util)."""
    if pe_ratio_ttm is None or growth_rate is None or growth_rate <= 0:
        return None
    return pe_ratio_ttm / (growth_rate * 100)


# --------------------------------------------------------------------------
# FCF Margin (Margen de Flujo de Caja Libre)
# --------------------------------------------------------------------------
def compute_fcf_margin(free_cash_flow: Optional[float], total_revenue: Optional[float]) -> Optional[float]:
    """FCF Margin = Flujo de Caja Libre / Ingresos totales.
    Devuelve None si falta algun dato o los ingresos no son validos."""
    if free_cash_flow is None or not total_revenue:
        return None
    return free_cash_flow / total_revenue
