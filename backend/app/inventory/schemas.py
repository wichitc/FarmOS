from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ItemCreate(BaseModel):
    code: str
    name: str
    category: str
    uom: str
    min_qty: Optional[float] = None
    max_qty: Optional[float] = None


class ItemOut(BaseModel):
    id: str
    code: str
    name: str
    category: str
    uom: str
    min_qty: Optional[float] = None
    max_qty: Optional[float] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class WarehouseCreate(BaseModel):
    farm_id: Optional[str] = None
    code: str
    name: str
    location: Optional[str] = None


class WarehouseOut(BaseModel):
    id: str
    farm_id: Optional[str] = None
    code: str
    name: str
    location: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class StockReceiptRequest(BaseModel):
    """Direct receipt not tied to a PO (e.g. a manual stock-take addition)."""

    item_id: str
    lot_code: str
    quantity: float
    unit_cost: Optional[float] = None
    expiry_date: Optional[date] = None
    notes: Optional[str] = None


class StockMovementRequest(BaseModel):
    quantity_delta: float
    movement_type: str
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    to_warehouse_id: Optional[str] = None
    notes: Optional[str] = None


class StockLotOut(BaseModel):
    id: str
    item_id: str
    warehouse_id: str
    lot_code: str
    quantity: float
    unit_cost: Optional[float] = None
    expiry_date: Optional[date] = None
    received_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StockMovementOut(BaseModel):
    id: str
    lot_id: str
    movement_type: str
    quantity_delta: float
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    from_warehouse_id: Optional[str] = None
    to_warehouse_id: Optional[str] = None
    performed_by: Optional[str] = None
    performed_at: datetime
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ItemValuationOut(BaseModel):
    item_id: str
    total_quantity: float
    total_value: float
    below_reorder_point: bool


class VendorCreate(BaseModel):
    code: str
    name: str
    contact_info: dict = {}


class VendorOut(BaseModel):
    id: str
    code: str
    name: str
    contact_info: dict
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class PurchaseRequestCreate(BaseModel):
    item_id: str
    farm_id: Optional[str] = None
    quantity: float
    needed_by: Optional[date] = None
    reason: Optional[str] = None


class PurchaseRequestOut(BaseModel):
    id: str
    item_id: str
    farm_id: Optional[str] = None
    quantity: float
    needed_by: Optional[date] = None
    reason: Optional[str] = None
    status: str
    workflow_instance_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ApprovalDecisionRequest(BaseModel):
    reason: Optional[str] = None


class PurchaseOrderCreate(BaseModel):
    vendor_id: str
    unit_price: Optional[float] = None


class PurchaseOrderOut(BaseModel):
    id: str
    request_id: str
    vendor_id: str
    item_id: str
    farm_id: Optional[str] = None
    po_number: str
    quantity: float
    unit_price: Optional[float] = None
    status: str
    issued_at: datetime
    received_quantity: Optional[float] = None
    received_at: Optional[datetime] = None
    inspection_status: Optional[str] = None
    inspection_notes: Optional[str] = None
    warehouse_id: Optional[str] = None
    resulting_lot_id: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_amount: Optional[float] = None
    invoice_matched: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderReceiveRequest(BaseModel):
    warehouse_id: str
    received_quantity: float
    lot_code: Optional[str] = None
    expiry_date: Optional[date] = None
    inspection_status: str = "passed"
    inspection_notes: Optional[str] = None


class PurchaseOrderInvoiceRequest(BaseModel):
    invoice_number: str
    invoice_amount: float
    tolerance_pct: float = 2.0
