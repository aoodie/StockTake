export const APP_VERSION = "2026.06.23.2";
export const CACHE_NAME = "stocktake-v39";
export const SCAN_DEBOUNCE_MS = 700;
export const CAMERA_DETECT_INTERVAL_MS = 90;
export const ZXING_DETECT_INTERVAL_MS = 130;

export const BARCODE_FORMATS = [
  "code_128",
  "ean_8",
  "ean_13",
  "upc_a",
  "upc_e",
  "itf",
  "code_39"
];

export const ZXING_FAST_FORMATS = [
  "EAN_13",
  "EAN_8",
  "UPC_A",
  "UPC_E",
  "ITF",
  "CODE_39",
  "CODE_128"
];

export function normalizeBarcode(value) {
  return String(value ?? "").trim();
}

export function isValidGtin(value) {
  const barcode = normalizeBarcode(value);
  if (!/^\d+$/.test(barcode) || ![8, 12, 13, 14].includes(barcode.length)) return false;
  const digits = [...barcode].map(Number);
  const total = digits
    .slice(0, -1)
    .reduce((sum, digit, index) => sum + digit * ((digits.length - 1 - index) % 2 === 1 ? 3 : 1), 0);
  return (10 - (total % 10)) % 10 === digits.at(-1);
}

export function canonicalizeBarcode(value) {
  const barcode = normalizeBarcode(value);
  return barcode.length === 13 && barcode.startsWith("0") && isValidGtin(barcode) ? barcode.slice(1) : barcode;
}

export function barcodeLookupKeys(value) {
  const raw = normalizeBarcode(value);
  const canonical = canonicalizeBarcode(raw);
  if (!canonical) return [];
  const keys = [canonical, raw];
  if (canonical.length === 12 && isValidGtin(canonical)) keys.push(`0${canonical}`);
  return [...new Set(keys)];
}

export function decodedBarcodeText(result) {
  if (!result) return "";
  const raw = typeof result.getText === "function"
    ? result.getText()
    : result.rawValue || result.text || result.toString?.() || "";
  return canonicalizeBarcode(raw);
}

export function confirmBarcodeCandidate(previous, value, now = Date.now(), windowMs = 3000, requiredReads = 2) {
  const barcode = canonicalizeBarcode(value);
  if (barcode && isValidGtin(barcode)) {
    return { candidate: { barcode, count: requiredReads, at: now }, confirmed: true };
  }
  const repeated = previous?.barcode === barcode && now - previous.at <= windowMs;
  const candidate = { barcode, count: repeated ? previous.count + 1 : 1, at: now };
  return { candidate, confirmed: Boolean(barcode && candidate.count >= requiredReads) };
}

export function scannerBlockReason({
  sleeping = false,
  sessionStarting = false,
  scanInFlight = false,
  awaitingNextScan = false,
  documentHidden = false,
  videoReady = 0,
  mode = "multi",
  pendingBarcode = ""
} = {}) {
  if (sleeping) return "scanner sleeping";
  if (sessionStarting) return "session starting";
  if (scanInFlight) return "scan processing";
  if (awaitingNextScan) return "waiting for next scan";
  if (documentHidden) return "page hidden";
  if (videoReady < 2) return "video not ready";
  if (mode !== "multi" && pendingBarcode) return "waiting for quantity";
  return "";
}

export function normalizeQuantity(value) {
  value = String(value ?? "").trim();
  if (!isValidQuantity(value)) return "0";
  let [whole, fraction = ""] = value.split(".");
  whole = whole.replace(/^0+(?=\d)/, "") || "0";
  fraction = fraction.replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : whole;
}

export function isValidQuantity(value) {
  return value !== "" && value !== "." && /^\d+(\.\d+)?$/.test(value);
}

export function addDecimalStrings(left, right) {
  const a = decimalUnits(left);
  const b = decimalUnits(right);
  const scale = Math.max(a.scale, b.scale);
  const total = a.units * 10n ** BigInt(scale - a.scale) + b.units * 10n ** BigInt(scale - b.scale);
  return formatDecimalUnits(total, scale);
}

function decimalUnits(value) {
  const normalized = normalizeQuantity(value);
  const [whole, fraction = ""] = normalized.split(".");
  return {
    units: BigInt(`${whole}${fraction}`),
    scale: fraction.length
  };
}

function formatDecimalUnits(units, scale) {
  if (scale === 0) return units.toString();
  const raw = units.toString().padStart(scale + 1, "0");
  const whole = raw.slice(0, -scale);
  const fraction = raw.slice(-scale).replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : whole;
}
