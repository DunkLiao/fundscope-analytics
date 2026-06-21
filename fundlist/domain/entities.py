from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from uuid import uuid4

from .value_objects import CAGR, DateRange, ReturnRate, Volatility


def _normalize_fund_code(fund_code):
    normalized = str(fund_code).strip().upper()
    if not normalized:
        raise ValueError("fund_code is required")
    return normalized


def _utc_now_text():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Fund:
    fund_code: str
    name: str
    market_type: str = ""
    category: str = ""
    currency: str = ""
    issuer: str = ""
    risk_level: str = ""
    status: str = "active"
    source_updated_at: str = ""
    fund_id: str = ""
    base_code: str = ""
    can_sell: str = ""

    def __post_init__(self):
        self.fund_code = _normalize_fund_code(self.fund_code)
        self.name = str(self.name).strip()
        if not self.name:
            raise ValueError("name is required")


@dataclass(frozen=True)
class FundPrice:
    fund_code: str
    price_date: date
    nav: float
    change_amount: float | None = None
    change_rate: ReturnRate | None = None
    source: str = ""
    created_at: str = field(default_factory=_utc_now_text)

    def __post_init__(self):
        object.__setattr__(self, "fund_code", _normalize_fund_code(self.fund_code))
        if self.nav <= 0:
            raise ValueError("nav must be greater than 0")


@dataclass
class FundHolding:
    fund_code: str
    holding_type: str
    amount: int
    holding_id: int | None = None
    units: float | None = None
    cost_basis: int | None = None
    start_date: date | None = None
    status: str = "active"

    def __post_init__(self):
        self.fund_code = _normalize_fund_code(self.fund_code)
        self.holding_type = str(self.holding_type).strip()
        if self.holding_type not in {"holdings", "recurring", "lump-sum"}:
            raise ValueError("holding_type must be holdings, recurring, or lump-sum")
        if isinstance(self.amount, bool) or int(self.amount) <= 0:
            raise ValueError("amount must be a positive integer")
        self.amount = int(self.amount)
        if self.cost_basis is None and self.holding_type == "holdings":
            self.cost_basis = self.amount


@dataclass
class Prediction:
    fund_code: str
    date_range: DateRange
    prediction_horizon: DateRange
    expected_return: ReturnRate
    expected_volatility: Volatility
    expected_cagr: CAGR
    method: str
    prediction_id: str = field(default_factory=lambda: str(uuid4()))
    generated_at: str = field(default_factory=_utc_now_text)

    def __post_init__(self):
        self.fund_code = _normalize_fund_code(self.fund_code)
        self.method = str(self.method).strip()
        if not self.method:
            raise ValueError("method is required")


@dataclass
class SimulationResult:
    fund_code: str
    date_range: DateRange
    initial_amount: int
    recurring_amount: int
    final_value: float
    total_cost: int
    total_return: ReturnRate
    cagr: CAGR
    volatility: Volatility
    simulation_id: str = field(default_factory=lambda: str(uuid4()))
    holding_id: int | None = None
    prediction_id: str | None = None
    prediction: Prediction | None = None
    generated_at: str = field(default_factory=_utc_now_text)

    def __post_init__(self):
        self.fund_code = _normalize_fund_code(self.fund_code)
        if self.initial_amount < 0:
            raise ValueError("initial_amount cannot be negative")
        if self.recurring_amount < 0:
            raise ValueError("recurring_amount cannot be negative")
        if self.total_cost < 0:
            raise ValueError("total_cost cannot be negative")
        if self.final_value < 0:
            raise ValueError("final_value cannot be negative")
        if self.prediction is not None:
            if self.prediction.fund_code != self.fund_code:
                raise ValueError("prediction must belong to the same fund")
            if self.prediction_id is None:
                self.prediction_id = self.prediction.prediction_id
