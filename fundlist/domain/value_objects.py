from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DateRange:
    start_date: date
    end_date: date

    def __post_init__(self):
        if self.start_date > self.end_date:
            raise ValueError("start_date must be earlier than or equal to end_date")

    @property
    def days(self):
        return (self.end_date - self.start_date).days


@dataclass(frozen=True)
class ReturnRate:
    value: float
    period: str

    @classmethod
    def from_percent(cls, percent, period):
        return cls(float(percent) / 100, period)

    def to_percent(self):
        return self.value * 100


@dataclass(frozen=True)
class Volatility:
    value: float
    period: str
    annualized: bool = False

    def __post_init__(self):
        if self.value < 0:
            raise ValueError("Volatility cannot be negative")


@dataclass(frozen=True)
class CAGR:
    value: float
    date_range: DateRange

    @classmethod
    def from_values(cls, start_value, end_value, date_range):
        start_value = float(start_value)
        end_value = float(end_value)
        if start_value <= 0:
            raise ValueError("CAGR start_value must be greater than 0")
        if end_value <= 0:
            raise ValueError("CAGR end_value must be greater than 0")
        if date_range.days <= 0:
            raise ValueError("CAGR date_range must span at least one day")
        years = date_range.days / 365
        return cls((end_value / start_value) ** (1 / years) - 1, date_range)
