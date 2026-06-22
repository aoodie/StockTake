import json
import os
import re
import sqlite3
import uuid
from typing import Any

from fastapi import APIRouter, Cookie, HTTPException

from ..auth import ADMIN_COOKIE, require_admin
from ..database import get_db, init_db, normalize_identifier, now_iso, set_setting
from ..models import (
    AiSuggestionApplyRequest,
    AiSuggestionGenerateRequest,
    AiSuggestionIssueBatchRequest,
    LlmSettingsRequest,
)
from ..services.enrichment import (
    build_ai_product_suggestion,
    clear_openai_api_key,
    fetch_product_suggestion,
    openai_key_status,
    openai_model,
    save_openai_api_key,
    test_openai_connection,
)
from .admin import audit_product_change, product_issue_rows, product_snapshot, task_from_row

router = APIRouter()

OPENAI_MODEL_SETTING = "openai_model"


def ai_suggestion_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["suggestion"] = json.loads(item.pop("suggestion_json") or "{}")
    item["field_values"] = json.loads(item.pop("field_values_json") or "{}")
    item["reasons"] = json.loads(item.pop("reasons_json") or "[]")
    item["sources"] = json.loads(item.pop("sources_json") or "[]")
    return item


def product_issue_names(db: sqlite3.Connection, product_id: str) -> list[str]:
    row = db.execute(
        """
        SELECT p.*, COUNT(pb.barcode) AS barcode_count
        FROM products p
        LEFT JOIN product_barcodes pb ON pb.product_id = p.id
        WHERE p.id = ?
        GROUP BY p.id
        """,
        (product_id,),
    ).fetchone()
    if not row:
        return []
    issues = []
    product = dict(row)
    if not (product.get("bin") or "").strip():
        issues.append("missing_bin")
    if product.get("draft_status") == "draft":
        issues.append("draft_product")
    if not (product.get("unit") or "").strip():
        issues.append("missing_unit")
    if not product.get("barcode_count"):
        issues.append("missing_barcode")
    return issues


def procurewizard_evidence(db: sqlite3.Connection, product_id: str | None) -> dict[str, Any]:
    if not product_id:
        return {}
    row = db.execute(
        """
        SELECT ptr.id, ptr.pid, ptr.bin_number, ptr.pos, ptr.category, ptr.description,
               ptr.pack_size, prm.status AS match_status, prm.score AS match_score,
               prm.reason AS match_reason, pwt.filename
        FROM procurewizard_template_rows ptr
        JOIN procurewizard_row_mappings prm ON prm.row_id = ptr.id
        JOIN procurewizard_templates pwt ON pwt.id = ptr.template_id
        WHERE prm.product_id = ?
        ORDER BY pwt.archived_at IS NOT NULL, pwt.created_at DESC, ptr.row_index
        LIMIT 1
        """,
        (product_id,),
    ).fetchone()
    return dict(row) if row else {}


def build_ai_evidence(db: sqlite3.Connection, request: AiSuggestionGenerateRequest) -> dict[str, Any]:
    product: dict[str, Any] | None = None
    task: dict[str, Any] | None = None
    target_type = "barcode"
    target_id = normalize_identifier(request.barcode or "")
    barcode = normalize_identifier(request.barcode or "")

    if request.task_id:
        task_row = db.execute(
            """
            SELECT pt.*, p.name AS current_name, p.bin AS current_bin
            FROM product_tasks pt
            LEFT JOIN products p ON p.id = pt.draft_product_id
            WHERE pt.id = ?
            """,
            (request.task_id,),
        ).fetchone()
        if not task_row:
            raise HTTPException(status_code=404, detail="Task not found")
        task = task_from_row(task_row)
        target_type = "task"
        target_id = request.task_id
        barcode = normalize_identifier(barcode or task.get("barcode"))
        if task.get("draft_product_id"):
            product = product_snapshot(db, task["draft_product_id"])

    if request.product_id:
        product = product_snapshot(db, request.product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        target_type = "product"
        target_id = request.product_id
        barcode = normalize_identifier(barcode or product.get("barcode"))

    if not barcode and product:
        for alias in product.get("barcodes") or []:
            if alias.get("label") != "ProcureWizard PID":
                barcode = normalize_identifier(alias.get("barcode"))
                break

    online = fetch_product_suggestion(barcode) if barcode else {}
    product_id = (product or {}).get("id") or (task or {}).get("draft_product_id")
    return {
        "target_type": target_type,
        "target_id": target_id,
        "barcode": barcode,
        "product": product or {},
        "task": task or {},
        "online": online,
        "procurewizard": procurewizard_evidence(db, product_id),
        "issues": product_issue_names(db, product_id) if product_id else [],
    }


def save_ai_suggestion(
    db: sqlite3.Connection,
    evidence: dict[str, Any],
    suggestion: dict[str, Any],
    force: bool = False,
) -> dict[str, Any]:
    target_type = evidence.get("target_type") or "barcode"
    target_id = evidence.get("target_id") or evidence.get("barcode") or ""
    if not force:
        existing = db.execute(
            """
            SELECT * FROM ai_suggestions
            WHERE target_type = ? AND COALESCE(target_id, '') = ? AND status = 'pending'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (target_type, target_id),
        ).fetchone()
        if existing:
            return ai_suggestion_row(existing)

    current = now_iso()
    suggestion_id = f"ai-{uuid.uuid4().hex[:12]}"
    field_values = suggestion.get("field_values") or {}
    reasons = suggestion.get("reasons") or []
    sources = suggestion.get("sources") or []
    db.execute(
        """
        INSERT INTO ai_suggestions (
            id, target_type, target_id, barcode, title, status, suggestion_json,
            field_values_json, confidence, risk_level, reasons_json, sources_json,
            error, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            suggestion_id,
            target_type,
            target_id,
            evidence.get("barcode") or None,
            suggestion.get("title") or "AI product suggestion",
            json.dumps(suggestion, separators=(",", ":")),
            json.dumps(field_values, separators=(",", ":")),
            float(suggestion.get("confidence") or 0),
            suggestion.get("risk_level") or "review",
            json.dumps(reasons, separators=(",", ":")),
            json.dumps(sources, separators=(",", ":")),
            suggestion.get("error"),
            current,
            current,
        ),
    )
    row = db.execute("SELECT * FROM ai_suggestions WHERE id = ?", (suggestion_id,)).fetchone()
    return ai_suggestion_row(row)


@router.get("/admin/api/settings/llm")
def admin_llm_settings(_: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict:
    require_admin(_)
    init_db()
    configured_default = os.getenv("OPENAI_MODEL", "gpt-4.1")
    model = openai_model()
    return {
        "openai_model": model,
        "env_default": configured_default,
        **openai_key_status(),
    }


@router.patch("/admin/api/settings/llm")
def admin_update_llm_settings(
    request: LlmSettingsRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    model = normalize_identifier(request.openai_model)
    if not re.fullmatch(r"[A-Za-z0-9._:/-]{2,120}", model):
        raise HTTPException(status_code=400, detail="OpenAI model must use letters, numbers, dots, dashes, underscores, slashes, or colons.")
    set_setting(OPENAI_MODEL_SETTING, model)

    if request.clear_openai_api_key:
        clear_openai_api_key()
    elif request.openai_api_key is not None:
        api_key = request.openai_api_key.strip()
        if len(api_key) < 20:
            raise HTTPException(status_code=400, detail="OpenAI API key looks too short.")
        save_openai_api_key(api_key)

    return {"openai_model": model, "status": "saved", **openai_key_status()}

@router.post("/admin/api/settings/llm/test")
def admin_test_llm_settings(_: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict:
    require_admin(_)
    init_db()
    result = test_openai_connection()
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {**result, **openai_key_status()}


@router.get("/admin/api/ai-suggestions")
def admin_ai_suggestions(
    status: str = "pending",
    limit: int = 50,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    limit = max(1, min(limit, 100))
    with get_db() as db:
        if status:
            rows = db.execute(
                """
                SELECT * FROM ai_suggestions
                WHERE status = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM ai_suggestions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return {"suggestions": [ai_suggestion_row(row) for row in rows]}


@router.post("/admin/api/ai-suggestions/generate")
def admin_generate_ai_suggestion(
    request: AiSuggestionGenerateRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    if not (request.product_id or request.task_id or request.barcode):
        raise HTTPException(status_code=400, detail="Choose a product, task, or barcode for AI suggestion.")
    with get_db() as db:
        evidence = build_ai_evidence(db, request)
        suggestion = build_ai_product_suggestion(evidence)
        saved = save_ai_suggestion(db, evidence, suggestion, force=request.force)
        db.commit()
    return {"suggestion": saved}


@router.post("/admin/api/ai-suggestions/generate-issues")
def admin_generate_issue_ai_suggestions(
    request: AiSuggestionIssueBatchRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    generated: list[dict[str, Any]] = []
    with get_db() as db:
        for row in product_issue_rows(db)[: request.limit]:
            product = row.get("product") or {}
            product_id = product.get("id")
            if not product_id:
                continue
            evidence = build_ai_evidence(
                db,
                AiSuggestionGenerateRequest(product_id=product_id, force=request.force),
            )
            evidence["issues"] = row.get("issues") or evidence.get("issues") or []
            suggestion = build_ai_product_suggestion(evidence)
            generated.append(save_ai_suggestion(db, evidence, suggestion, force=request.force))
        db.commit()
    return {"suggestions": generated, "total": len(generated)}


@router.post("/admin/api/ai-suggestions/{suggestion_id}/reject")
def admin_reject_ai_suggestion(
    suggestion_id: str,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    current = now_iso()
    with get_db() as db:
        result = db.execute(
            """
            UPDATE ai_suggestions
            SET status = 'rejected', rejected_at = ?, updated_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (current, current, suggestion_id),
        )
        db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Pending AI suggestion not found")
    return {"suggestion_id": suggestion_id, "status": "rejected"}


@router.post("/admin/api/ai-suggestions/{suggestion_id}/apply")
def admin_apply_ai_suggestion(
    suggestion_id: str,
    request: AiSuggestionApplyRequest,
    _: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> dict:
    require_admin(_)
    init_db()
    current = now_iso()
    allowed = ["bin", "name", "category", "size", "unit", "photo_url", "notes", "draft_status"]
    with get_db() as db:
        row = db.execute("SELECT * FROM ai_suggestions WHERE id = ?", (suggestion_id,)).fetchone()
        if not row or row["status"] != "pending":
            raise HTTPException(status_code=404, detail="Pending AI suggestion not found")
        item = ai_suggestion_row(row)
        selected_fields = request.fields
        values = {
            key: value
            for key, value in (item.get("field_values") or {}).items()
            if key in allowed and key in selected_fields and normalize_identifier(value)
        }
        target_type = item.get("target_type")
        target_id = item.get("target_id")
        product_id = target_id if target_type == "product" else None
        if target_type == "task" and target_id:
            task = db.execute("SELECT * FROM product_tasks WHERE id = ?", (target_id,)).fetchone()
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            product_id = task["draft_product_id"]
            task_suggestion = json.loads(task["suggested_json"] or "{}")
            task_suggestion.update(values)
            db.execute(
                """
                UPDATE product_tasks
                SET suggested_json = ?, status = CASE WHEN status = 'queued' THEN 'review_needed' ELSE status END,
                    updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(task_suggestion, separators=(",", ":")), current, target_id),
            )
        if not product_id:
            raise HTTPException(status_code=400, detail="This AI suggestion is not linked to a product yet.")
        before = product_snapshot(db, product_id)
        if not before:
            raise HTTPException(status_code=404, detail="Product not found")
        if values:
            assignments = [f"{key} = ?" for key in allowed if key in values]
            args = [values[key] for key in allowed if key in values]
            assignments.append("product_updated_at = ?")
            args.extend([current, product_id])
            db.execute(f"UPDATE products SET {', '.join(assignments)} WHERE id = ?", args)
            audit_product_change(db, product_id, "apply_ai_suggestion", before, product_snapshot(db, product_id))
        db.execute(
            """
            UPDATE ai_suggestions
            SET status = 'applied', applied_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (current, current, suggestion_id),
        )
        db.commit()
    return {"suggestion_id": suggestion_id, "product_id": product_id, "status": "applied", "fields": list(values.keys())}
