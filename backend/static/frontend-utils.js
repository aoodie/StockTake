export const APP_VERSION = "2026.06.11.1";
export const CACHE_NAME = "stocktake-v31";
export const SCAN_DEBOUNCE_MS = 700;
export const CAMERA_DETECT_INTERVAL_MS = 90;
export const ZXING_DETECT_INTERVAL_MS = 130;

export const BARCODE_FORMATS = [
  "code_128",
  "ean_8",
  "ean_13",
  "upc_a",
  "upc_e"
];

export const ZXING_FAST_FORMATS = [
  "EAN_13",
  "EAN_8",
  "UPC_A",
  "UPC_E",
  "CODE_128"
];

export function normalizeBarcode(value) {
  return String(value ?? "").trim();
}

export function barcodeLookupKeys(value) {
  const raw = normalizeBarcode(value);
  if (!raw) return [];
  const keys = [raw];
  if (/^\d+$/.test(raw)) {
    keys.push(String(Number(raw)));
    keys.push(raw.padStart(8, "0"), raw.padStart(12, "0"), raw.padStart(13, "0"));
  }
  return [...new Set(keys)];
}

export function decodedBarcodeText(result) {
  if (!result) return "";
  if (typeof result.getText === "function") return normalizeBarcode(result.getText());
  return normalizeBarcode(result.rawValue || result.text || result.toString?.() || "");
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
