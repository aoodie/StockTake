import test from "node:test";
import assert from "node:assert/strict";

import {
  addDecimalStrings,
  barcodeLookupKeys,
  decodedBarcodeText,
  isValidQuantity,
  normalizeBarcode,
  normalizeQuantity
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

test("barcode helpers preserve leading zeros but add numeric lookup keys", () => {
  assert.equal(normalizeBarcode(" 001234 "), "001234");
  assert.deepEqual(barcodeLookupKeys("001234").slice(0, 2), ["001234", "1234"]);
});

test("decoded barcode text supports native and ZXing results", () => {
  assert.equal(decodedBarcodeText({ rawValue: " 123 " }), "123");
  assert.equal(decodedBarcodeText({ getText: () => " 456 " }), "456");
});
