"""
Motor de valoracion (Valor Intrinseco) - replica exacta de las formulas
de la hoja "VMI IV Calculator (20 years)" del archivo VMI_Investing_template.xlsx

Metodo: Descuento a 20 anios de un flujo base (Ingreso Neto, Flujo de Caja
Operativo o Flujo de Caja Libre), con 3 tramos de crecimiento:
  - Anios 1-5:   growth_1_5
  - Anios 6-10:  growth_6_10
  - Anios 11-20: growth_11_20
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ValuationInputs:
    ticker: str
    company_name: str
    valuation_method: str  # "Discounted Net Income" | "Discounted Cash Flow" | "Discounted Free Cash Flow"

    financial_statement_currency: str
    stock_listing_currency: str
    exchange_rate: float  # 1 unidad de financial_statement_currency = exchange_rate unidades de stock_listing_currency

    base_metric_current: float   # G14: Net Income / Operating CF / Free CF (periodo actual)
    total_debt: float            # G16
    cash_and_st_investments: float  # G18

    growth_1_5: float    # F20
    growth_6_10: float   # F22
    growth_11_20: float  # F24

    shares_outstanding: float  # F26 (mismas unidades que base_metric_current, p.ej. millones)
    discount_rate: float       # E28
    current_year: int          # E30
    last_close_price: float    # N30 (en stock_listing_currency)

    beta: Optional[float] = None
    risk_free_rate: Optional[float] = None
    market_risk_premium: Optional[float] = None


@dataclass
class ValuationResult:
    years_1_10: list = field(default_factory=list)          # [(year, valor_proyectado, factor_descuento, valor_descontado)]
    years_11_20: list = field(default_factory=list)
    present_value_20y_statement_ccy: float = 0.0             # N14
    intrinsic_value_before_cash_debt: float = 0.0             # N16
    debt_per_share: float = 0.0                                # N18
    cash_per_share: float = 0.0                                # N20
    intrinsic_value_per_share_statement_ccy: float = 0.0       # N24
    final_intrinsic_value_per_share_listing_ccy: float = 0.0   # N26  <-- CLAVE
    discount_premium: float = 0.0                              # M28  <-- CLAVE


def discount_rate_from_beta(beta: float, risk_free_rate: float, market_risk_premium: float) -> float:
    """Discount Rate = Risk Free Rate + Beta x Market Risk Premium (formula continua
    equivalente a la tabla de referencia por tramos de Beta de la hoja de calculo)."""
    return risk_free_rate + beta * market_risk_premium


def compute_intrinsic_value(inp: ValuationInputs) -> ValuationResult:
    r = inp.discount_rate
    res = ValuationResult()

    # --- Anios 1 a 10 (F33:O33 y F34:O34 y F35:O35) ---
    values_1_10 = []
    prev = inp.base_metric_current
    for i in range(1, 11):
        g = inp.growth_1_5 if i <= 5 else inp.growth_6_10
        prev = prev * (1 + g)
        values_1_10.append(prev)

    discount_factors_1_10 = [(1 / (1 + r)) ** n for n in range(1, 11)]
    discounted_1_10 = [v * f for v, f in zip(values_1_10, discount_factors_1_10)]

    for idx in range(10):
        res.years_1_10.append((
            inp.current_year + idx + 1,
            values_1_10[idx],
            discount_factors_1_10[idx],
            discounted_1_10[idx],
        ))

    # --- Anios 11 a 20 (F38:O38 y F39:O39 y F40:O40) ---
    values_11_20 = []
    prev = values_1_10[-1]  # O33 = valor del anio 10
    for i in range(11, 21):
        prev = prev * (1 + inp.growth_11_20)
        values_11_20.append(prev)

    discount_factors_11_20 = [(1 / (1 + r)) ** n for n in range(11, 21)]
    discounted_11_20 = [v * f for v, f in zip(values_11_20, discount_factors_11_20)]

    for idx in range(10):
        res.years_11_20.append((
            inp.current_year + idx + 11,
            values_11_20[idx],
            discount_factors_11_20[idx],
            discounted_11_20[idx],
        ))

    # --- Agregados (N14, N16, N18, N20, N24, N26, M28) ---
    res.present_value_20y_statement_ccy = sum(discounted_1_10) + sum(discounted_11_20)  # N14

    shares = inp.shares_outstanding
    res.intrinsic_value_before_cash_debt = (
        res.present_value_20y_statement_ccy / shares if shares else 0.0
    )  # N16
    res.debt_per_share = (inp.total_debt / shares) if shares else 0.0             # N18
    res.cash_per_share = (inp.cash_and_st_investments / shares) if shares else 0.0  # N20

    res.intrinsic_value_per_share_statement_ccy = (
        res.intrinsic_value_before_cash_debt - res.debt_per_share + res.cash_per_share
    )  # N24

    res.final_intrinsic_value_per_share_listing_ccy = (
        res.intrinsic_value_per_share_statement_ccy * inp.exchange_rate
    )  # N26

    res.discount_premium = (
        (inp.last_close_price / res.final_intrinsic_value_per_share_listing_ccy) - 1
        if res.final_intrinsic_value_per_share_listing_ccy else 0.0
    )  # M28  (negativo = accion con DESCUENTO / infravalorada; positivo = PRIMA / sobrevalorada)

    return res
