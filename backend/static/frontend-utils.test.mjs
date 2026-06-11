import test from "node:test";
import assert from "node:assert/strict";

import {
  addDecimalStrings,
  barcodeLookupKeys,
  canonicalizeBarcode,
  confirmBarcodeCandidate,
  decodedBarcodeText,
  isValidGtin,
  isValidQuantity,
  normalizeBarcode,
  normalizeQuantity,
  scannerBlockReason
} from "./frontend-utils.js";

test("decimal quantities normalize and add without floating point drift", () => {
  assert.equal(normalizeQuantity("001.5000"), "1.5");
  assert.equal(normalizeQuantity("0"), "0");
  assert.equal(normalizeQuantity("."), "0");
  assert.equal(addDecimalStrings("0.1", "0.2"), "0.3");
  assert.equal(addDecimalStrings("12.25", "0.75"), "13");
});

test("quantity validation accepts explicit zero and decimals", () => {
  assert.equal(isValidQuantity("0"), true);
  assert.equal(isValidQuantity("0.4"), true);
  assert.equal(isValidQuantity("12.25"), true);
  assert.equal(isValidQuantity(""), false);
});

test("barcode helpers display equivalent EAN-13 as printed UPC-A", () => {
  assert.equal(normalizeBarcode(" 001234 "), "001234");
  assert.equal(isValidGtin("088110552404"), true);
  assert.equal(canonicalizeBarcode("0088110552404"), "088110552404");
  assert.deepEqual(barcodeLookupKeys("0088110552404"), ["088110552404", "0088110552404"]);
  assert.deepEqual(barcodeLookupKeys("001234"), ["001234"]);
});

test("decoded barcode text supports native and ZXing results", () => {
  assert.equal(decodedBarcodeText({ rawValue: " 123 " }), "123");
  assert.equal(decodedBarcodeText({ getText: () => " 0088110552404 " }), "088110552404");
});

test("camera barcode requires three matching reads", () => {
  const first = confirmBarcodeCandidate(null, "088110552404", 1000);
  assert.equal(first.confirmed, false);
  const mismatch = confirmBarcodeCandidate(first.candidate, "3081880552404", 1100);
  assert.equal(mismatch.confirmed, false);
  const second = confirmBarcodeCandidate(mismatch.candidate, "3081880552404", 1200);
  assert.equal(second.confirmed, false);
  const confirmed = confirmBarcodeCandidate(second.candidate, "3081880552404", 1300);
  assert.equal(confirmed.confirmed, true);
});

test("scanner block reason reports only active blockers", () => {
  assert.equal(scannerBlockReason({ videoReady: 4 }), "");
  assert.equal(scannerBlockReason({ sleeping: true, videoReady: 4 }), "scanner sleeping");
  assert.equal(scannerBlockReason({ awaitingNextScan: true, videoReady: 4 }), "waiting for next scan");
  assert.equal(scannerBlockReason({ videoReady: 1 }), "video not ready");
  assert.equal(
    scannerBlockReason({ videoReady: 4, mode: "bulk", pendingBarcode: "123" }),
    "waiting for quantity"
  );
});
