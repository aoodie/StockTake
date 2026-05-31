from pydantic import BaseModel, Field
from typing import Any, Literal
from datetime import datetime

class SyncEvent(BaseModel):
    local_id: str
    device_id: str
    session_id: str
    location_id: str | None = None
    event_type: Literal[
        "scan",
        "quantity_edit",
        "draft_product",
        "photo_capture",
        "location_change",
        "session_change",
        "undo_scan",
        "delete_line",
    ]
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    idempotency_key: str

class SyncRequest(BaseModel):
    events: list[SyncEvent]

class LoginRequest(BaseModel):
    password: str = Field(min_length=1)

class BinUpdateRequest(BaseModel):
    bin: str = Field(min_length=1)

class ProductUpsertRequest(BaseModel):
    barcode: str = Field(min_length=1)
    bin: str | None = None
    name: str = Field(min_length=1)
    category: str = ""
    size: str = ""
    unit: str = "each"
    photo_url: str | None = None
    notes: str | None = None
    draft_status: Literal["confirmed", "draft"] = "confirmed"

class ProductPatchRequest(BaseModel):
    barcode: str | None = None
    bin: str | None = None
    name: str | None = None
    category: str | None = None
    size: str | None = None
    unit: str | None = None
    photo_url: str | None = None
    notes: str | None = None
    draft_status: Literal["confirmed", "draft"] | None = None

class SessionCreateRequest(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    period_date: str = Field(min_length=1)

class TaskPatchRequest(BaseModel):
    status: Literal["queued", "enriching", "review_needed", "approved", "failed"] | None = None
    suggested: dict[str, Any] | None = None
    error: str | None = None

class TaskApproveRequest(BaseModel):
    name: str = Field(min_length=1)
    bin: str = ""
    category: str = ""
    size: str = ""
    unit: str = "each"
    photo_url: str | None = None
    notes: str | None = None

class BulkProductUpdateRequest(BaseModel):
    product_ids: list[str] = Field(..., min_length=1)
    bin: str | None = None
    category: str | None = None

class BulkProductDeleteRequest(BaseModel):
    product_ids: list[str] = Field(..., min_length=1)

class ProductBarcodeRequest(BaseModel):
    barcode: str = Field(min_length=1)
    label: str = "Alias barcode"
    is_primary: bool = False

class ProductMergeRequest(BaseModel):
    source_product_id: str = Field(min_length=1)
    target_product_id: str = Field(min_length=1)

class ProcureWizardImportRequest(BaseModel):
    filename: str = "procurewizard.csv"
    csv_text: str = Field(min_length=1)

class ProcureWizardLinkRequest(BaseModel):
    product_id: str | None = None
