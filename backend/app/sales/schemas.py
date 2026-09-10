from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CustomerCreate(BaseModel):
    code: str
    name: str
    contact_info: dict = {}


class CustomerOut(BaseModel):
    id: str
    code: str
    name: str
    contact_info: dict

    model_config = ConfigDict(from_attributes=True)


class SalesOrderCreate(BaseModel):
    customer_id: str
    farm_id: Optional[str] = None
    season_id: Optional[str] = None
    harvest_lot_id: Optional[str] = None
    quantity_kg: float
    unit_price: float
    order_date: Optional[date] = None


class SalesOrderOut(BaseModel):
    id: str
    customer_id: str
    farm_id: Optional[str] = None
    season_id: Optional[str] = None
    harvest_lot_id: Optional[str] = None
    quantity_kg: float
    unit_price: float
    status: str
    order_date: date

    model_config = ConfigDict(from_attributes=True)


class InvoiceCreate(BaseModel):
    amount: Optional[float] = None
    due_date: Optional[date] = None


class InvoiceOut(BaseModel):
    id: str
    order_id: str
    invoice_number: str
    amount: float
    issued_at: datetime
    due_date: Optional[date] = None
    is_paid: bool

    model_config = ConfigDict(from_attributes=True)


class PaymentCreate(BaseModel):
    amount: float
    method: Optional[str] = None
    paid_at: Optional[datetime] = None


class PaymentOut(BaseModel):
    id: str
    invoice_id: str
    amount: float
    method: Optional[str] = None
    paid_at: datetime

    model_config = ConfigDict(from_attributes=True)
