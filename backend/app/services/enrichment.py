import os
import json
import re
from pathlib import Path
from urllib.parse import urlparse
import httpx
from ..database import get_db, now_iso

IMAGE_DIR = Path(__file__).resolve().parents[2] / "data" / "product-images"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

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
    if not OPENAI_API_KEY:
        return suggestion
    prompt = (
        "Return only compact JSON for a stocktaking product record. "
        "Use the supplied online lookup data, do not invent facts, and leave unknown fields blank. "
        "Fields: barcode,name,brand,category,size,unit,image_url,source_urls,confidence."
    )
    
    # Map model name if user is using a chat model, standard completions endpoint is /v1/chat/completions
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": OPENAI_MODEL,
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
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            # If standard endpoint fails, fallback to legacy/custom endpoint structure
            if response.status_code != 200:
                fallback_url = "https://api.openai.com/v1/responses"
                fallback_payload = {
                    "model": OPENAI_MODEL,
                    "input": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": json.dumps(suggestion, separators=(",", ":"))},
                    ],
                }
                response = client.post(
                    fallback_url,
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
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
