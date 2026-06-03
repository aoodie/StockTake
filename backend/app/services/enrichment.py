import os
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from typing import Any
import httpx
from ..database import DATA_DIR, get_db, get_setting, now_iso

IMAGE_DIR = Path(__file__).resolve().parents[2] / "data" / "product-images"
DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_API_KEY_FILE = DATA_DIR / "openai_api_key.txt"

def openai_model() -> str:
    return get_setting("openai_model", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL

def openai_api_key() -> str:
    if OPENAI_API_KEY_FILE.exists():
        return OPENAI_API_KEY_FILE.read_text(encoding="utf-8").strip()
    return os.getenv("OPENAI_API_KEY", "").strip()

def openai_key_status() -> dict[str, str | bool]:
    key = openai_api_key()
    if not key:
        return {"has_openai_key": False, "openai_key_source": "none", "openai_key_preview": ""}
    source = "admin" if OPENAI_API_KEY_FILE.exists() else "environment"
    preview = f"{key[:6]}...{key[-4:]}" if len(key) > 12 else "configured"
    return {"has_openai_key": True, "openai_key_source": source, "openai_key_preview": preview}

def save_openai_api_key(api_key: str) -> None:
    key = api_key.strip()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OPENAI_API_KEY_FILE.write_text(f"{key}\n", encoding="utf-8")
    OPENAI_API_KEY_FILE.chmod(0o600)

def clear_openai_api_key() -> None:
    if OPENAI_API_KEY_FILE.exists():
        OPENAI_API_KEY_FILE.unlink()

def parse_open_food_facts(product: dict, barcode: str) -> dict:
    name = product.get("product_name") or product.get("generic_name") or f"Product {barcode}"
    quantity = product.get("quantity") or ""
    category = ""
    categories = product.get("categories_tags") or product.get("categories_hierarchy") or []
    if categories:
        category = str(categories[0]).split(":")[-1].replace("-", " ").title()
    image_candidates = []
    for key in ("image_front_url", "image_url", "image_packaging_url", "image_ingredients_url"):
        url = product.get(key)
        if url and url not in image_candidates:
            image_candidates.append(url)
    selected_images = product.get("selected_images") or {}
    for image_group in selected_images.values():
        if not isinstance(image_group, dict):
            continue
        for size_group in image_group.values():
            if isinstance(size_group, dict):
                for url in size_group.values():
                    if url and url not in image_candidates:
                        image_candidates.append(url)
    image_url = image_candidates[0] if image_candidates else ""
    brand = (product.get("brands") or "").split(",")[0].strip()
    return {
        "barcode": barcode,
        "name": " ".join([brand, name]).strip() if brand and brand.lower() not in name.lower() else name,
        "brand": brand,
        "category": category,
        "size": quantity,
        "unit": "bottle" if re.search(r"\b(cl|ml|l)\b", quantity, re.I) else "each",
        "image_url": image_url,
        "image_candidates": image_candidates[:6],
        "source_urls": [f"https://world.openfoodfacts.org/product/{barcode}"],
        "source_name": "Open Food Facts",
        "confidence": 0.72 if name else 0.4,
    }

def extract_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.I | re.M).strip()
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}

def llm_refine_product(suggestion: dict) -> dict:
    api_key = openai_api_key()
    if not api_key:
        return suggestion
    prompt = (
        "Return only compact JSON for a stocktaking product record. "
        "Use the supplied online lookup data, do not invent facts, and leave unknown fields blank. "
        "Fields: barcode,name,brand,category,size,unit,image_url,source_urls,confidence."
    )
    
    # Map model name if user is using a chat model, standard completions endpoint is /v1/chat/completions
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": openai_model(),
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(suggestion, separators=(",", ":"))},
        ],
        "response_format": {"type": "json_object"}
    }
    
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            # If standard endpoint fails, fallback to legacy/custom endpoint structure
            if response.status_code != 200:
                fallback_url = "https://api.openai.com/v1/responses"
                fallback_payload = {
                    "model": openai_model(),
                    "input": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": json.dumps(suggestion, separators=(",", ":"))},
                    ],
                }
                response = client.post(
                    fallback_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=fallback_payload,
                )
            
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        suggestion["llm_error"] = str(exc)
        return suggestion

    output = ""
    if "choices" in data:
        output = data["choices"][0].get("message", {}).get("content", "")
    else:
        output = data.get("output_text", "")
        if not output:
            output_parts = []
            for item in data.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") in {"output_text", "text"}:
                        output_parts.append(content.get("text", ""))
            output = "\n".join(output_parts)
            
    refined = extract_json_object(output)
    return {**suggestion, **{k: v for k, v in refined.items() if v not in (None, "")}}

def _compact_sources(*items: Any) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if not item:
            continue
        if isinstance(item, str):
            url = item.strip()
            if url and url not in seen:
                sources.append({"name": urlparse(url).netloc or "Source", "url": url})
                seen.add(url)
            continue
        if isinstance(item, dict):
            for url in item.get("source_urls") or []:
                clean = str(url or "").strip()
                if clean and clean not in seen:
                    sources.append({"name": item.get("source_name") or urlparse(clean).netloc or "Source", "url": clean})
                    seen.add(clean)
    return sources[:8]

def _clean_field_values(values: dict[str, Any]) -> dict[str, str]:
    allowed = {"name", "bin", "category", "size", "unit", "photo_url", "notes", "draft_status"}
    cleaned: dict[str, str] = {}
    for key, value in values.items():
        if key not in allowed or value is None:
            continue
        text = str(value).strip()
        if text:
            cleaned[key] = text
    return cleaned

def _llm_refine_ai_suggestion(evidence: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    api_key = openai_api_key()
    if not api_key:
        return draft
    prompt = (
        "You are an admin-side product data copilot for a bar stocktake system. "
        "Return compact JSON only. Use evidence, do not invent unsupported facts. "
        "Suggest only fields that improve an inventory product record. "
        "Schema: title, field_values, confidence, risk_level, reasons, sources. "
        "risk_level must be one of auto_safe, review, low_confidence, blocked. "
        "field_values may contain name, bin, category, size, unit, photo_url, notes, draft_status."
    )
    payload = {
        "model": openai_model(),
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps({"evidence": evidence, "draft": draft}, separators=(",", ":"))},
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        with httpx.Client(timeout=25) as client:
            response = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0].get("message", {}).get("content", "")
    except Exception as exc:
        return {**draft, "error": str(exc)}
    refined = extract_json_object(content)
    if not refined:
        return draft
    field_values = _clean_field_values(refined.get("field_values") or draft.get("field_values") or {})
    reasons = refined.get("reasons") if isinstance(refined.get("reasons"), list) else draft.get("reasons", [])
    sources = refined.get("sources") if isinstance(refined.get("sources"), list) else draft.get("sources", [])
    confidence = refined.get("confidence", draft.get("confidence", 0.3))
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = draft.get("confidence", 0.3)
    risk = refined.get("risk_level") or draft.get("risk_level") or "review"
    if risk not in {"auto_safe", "review", "low_confidence", "blocked"}:
        risk = "review"
    return {
        **draft,
        "title": str(refined.get("title") or draft.get("title") or "AI product suggestion").strip(),
        "field_values": field_values,
        "confidence": confidence,
        "risk_level": risk,
        "reasons": [str(reason) for reason in reasons if str(reason or "").strip()][:8],
        "sources": sources[:8] if isinstance(sources, list) else draft.get("sources", []),
    }

def build_ai_product_suggestion(evidence: dict[str, Any]) -> dict[str, Any]:
    product = evidence.get("product") or {}
    task = evidence.get("task") or {}
    online = evidence.get("online") or {}
    procurewizard = evidence.get("procurewizard") or {}
    issues = evidence.get("issues") or []

    field_values: dict[str, str] = {}
    current_name = str(product.get("name") or task.get("current_name") or "").strip()
    online_name = str(online.get("name") or "").strip()
    weak_current_name = (
        not current_name
        or current_name.lower().startswith("draft ")
        or current_name.lower().startswith("product ")
    )
    if online_name and weak_current_name:
        field_values["name"] = online_name
    if not str(product.get("bin") or "").strip() and procurewizard.get("bin_number"):
        field_values["bin"] = str(procurewizard["bin_number"]).strip()
    if not str(product.get("category") or "").strip() and (online.get("category") or procurewizard.get("category")):
        field_values["category"] = str(online.get("category") or procurewizard.get("category")).strip()
    if not str(product.get("size") or "").strip() and (online.get("size") or procurewizard.get("pack_size")):
        field_values["size"] = str(online.get("size") or procurewizard.get("pack_size")).strip()
    if not str(product.get("unit") or "").strip() or product.get("unit") == "each":
        if online.get("unit") and online.get("unit") != "each":
            field_values["unit"] = str(online["unit"]).strip()
    if not str(product.get("photo_url") or "").strip() and (online.get("image_url") or ""):
        field_values["photo_url"] = str(online["image_url"]).strip()
    if product.get("draft_status") == "draft" and field_values.get("name"):
        field_values["draft_status"] = "confirmed"

    note_parts = []
    if online.get("brand"):
        note_parts.append(f"Brand: {online['brand']}")
    if online.get("source_name"):
        note_parts.append(f"AI evidence source: {online['source_name']}")
    if online.get("confidence"):
        note_parts.append(f"Lookup confidence: {online['confidence']}")
    if note_parts and not str(product.get("notes") or "").strip():
        field_values["notes"] = "\n".join(note_parts)

    reasons = []
    if issues:
        reasons.append(f"Product has open issues: {', '.join(str(issue).replace('_', ' ') for issue in issues[:5])}.")
    if online_name:
        reasons.append("Online product lookup supplied a candidate identity.")
    if procurewizard:
        reasons.append("Active ProcureWizard row supplies local BIN/category/pack-size evidence.")
    if field_values.get("photo_url"):
        reasons.append("A real online product image candidate is available for approval.")
    if not reasons:
        reasons.append("No strong automated repair was found; keep this for manual review.")

    confidence = float(online.get("confidence") or 0.35)
    if procurewizard:
        confidence = max(confidence, 0.62)
    if not field_values:
        confidence = min(confidence, 0.25)
    risk_level = "review"
    if confidence < 0.45:
        risk_level = "low_confidence"
    if not field_values:
        risk_level = "blocked"

    draft = {
        "title": field_values.get("name") or current_name or f"Product {evidence.get('barcode') or ''}".strip(),
        "field_values": _clean_field_values(field_values),
        "confidence": max(0.0, min(1.0, confidence)),
        "risk_level": risk_level,
        "reasons": reasons[:8],
        "sources": _compact_sources(online, *(online.get("source_urls") or [])),
        "evidence": evidence,
    }
    return _llm_refine_ai_suggestion(evidence, draft)

def fetch_product_suggestion(barcode: str) -> dict:
    # 1. Check SQLite lookup cache first
    with get_db() as db:
        cached = db.execute(
            "SELECT suggested_json FROM product_lookup_cache WHERE barcode = ?",
            (barcode,)
        ).fetchone()
        if cached:
            try:
                return json.loads(cached["suggested_json"])
            except json.JSONDecodeError:
                pass
                
    # 2. Run Open Food Facts API lookup
    suggestion = {
        "barcode": barcode,
        "name": f"Product {barcode}",
        "brand": "",
        "category": "",
        "size": "",
        "unit": "each",
        "image_url": "",
        "image_candidates": [],
        "source_urls": [],
        "source_name": "",
        "confidence": 0.25,
    }
    try:
        with httpx.Client(timeout=12, follow_redirects=True) as client:
            response = client.get(f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == 1:
                    suggestion = parse_open_food_facts(data.get("product") or {}, barcode)
    except Exception as exc:
        suggestion["lookup_error"] = str(exc)
        
    # 3. LLM Refinement
    suggestion = llm_refine_product(suggestion)
    
    # 4. Save to cache
    with get_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO product_lookup_cache (barcode, suggested_json, cached_at)
            VALUES (?, ?, ?)
            """,
            (barcode, json.dumps(suggestion, separators=(",", ":")), now_iso())
        )
        db.commit()
        
    return suggestion

def image_extension(url: str, content_type: str) -> str:
    path = urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    return ".jpg"

def save_product_image(product_id: str, image_url: str) -> str | None:
    if not image_url:
        return None
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            response = client.get(image_url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                return None
            ext = image_extension(image_url, content_type)
            safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", product_id)
            path = IMAGE_DIR / f"{safe_id}{ext}"
            path.write_bytes(response.content)
            return f"/product-images/{path.name}"
    except Exception:
        return None
