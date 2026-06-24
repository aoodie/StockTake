from pydantic import BaseModel, Field
from typing import Any, Literal
from datetime import datetime

class SyncEvent(BaseModel):
    local_id: str = Field(min_length=1, max_length=160)
    device_id: str = Field(min_length=1, max_length=160)
    session_id: str = Field(min_length=1, max_length=160)
    location_id: str | None = Field(default=None, max_length=160)
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
    idempotency_key: str = Field(min_length=1, max_length=320)

class SyncRequest(BaseModel):
    events: list[SyncEvent] = Field(max_length=100)

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
    source_screen: Literal["admin", "admin_mapping", "phone_mapping"] = "admin"

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
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    period_date: str = Field(min_length=1, max_length=20)

class SessionStatusRequest(BaseModel):
    status: Literal["draft", "open", "counting", "review", "approved", "exported", "archived"]
    reason: str = Field(default="", max_length=500)

class LocationUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    id: str | None = Field(default=None, max_length=80)

class LocationPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    active: bool | None = None

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
    confirm_additional_barcode: bool = False
    source_screen: Literal["admin", "admin_mapping", "phone_mapping"] = "admin"

class ProductMergeRequest(BaseModel):
    source_product_id: str = Field(min_length=1)
    target_product_id: str = Field(min_length=1)

class ProcureWizardImportRequest(BaseModel):
    filename: str = "procurewizard.csv"
    csv_text: str = Field(min_length=1)
    outlet_id: str = Field(default="cellar", min_length=1, max_length=80)

class CatalogRestoreRequest(BaseModel):
    filename: str = "mapped-products.csv"
    csv_text: str = Field(min_length=1, max_length=20_000_000)

class ProcureWizardLinkRequest(BaseModel):
    product_id: str | None = None

class AiSuggestionGenerateRequest(BaseModel):
    product_id: str | None = None
    task_id: str | None = None
    barcode: str | None = None
    force: bool = False

class AiSuggestionIssueBatchRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)
    force: bool = False

class AiSuggestionApplyRequest(BaseModel):
    fields: list[
        Literal["name", "bin", "category", "size", "unit", "photo_url", "notes", "draft_status"]
    ] = Field(min_length=1)

class LlmSettingsRequest(BaseModel):
    openai_model: str = Field(min_length=1, max_length=120)
    openai_api_key: str | None = Field(default=None, min_length=1, max_length=500)
    clear_openai_api_key: bool = False
