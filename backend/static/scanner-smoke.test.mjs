import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import test from "node:test";
import assert from "node:assert/strict";

const appSource = await readFile(new URL("./app.js", import.meta.url), "utf8");
const require = createRequire(import.meta.url);
const ZXing = require("./vendor/zxing-library.min.js");

test("main scanner uses ZXing's supported video-element decode loop", () => {
  assert.match(appSource, /runZxingVideoLoop/);
  assert.match(appSource, /reader\.decodeFromVideoElementContinuously\(els\.preview/);
  assert.doesNotMatch(appSource, /decodeFromConstraints/);
  assert.doesNotMatch(appSource, /reader\.decode\(els\.preview\)/);
  assert.doesNotMatch(appSource, /decodeFromImageElement/);
  assert.doesNotMatch(appSource, /runZxingRoiLoop/);
});

test("bundled ZXing exposes the video-element decoder used by the scanner", () => {
  const reader = new ZXing.BrowserMultiFormatReader();
  assert.equal(typeof reader.decodeFromVideoElementContinuously, "function");
  assert.equal(typeof reader.stopContinuousDecode, "function");
  assert.equal(typeof reader.reset, "function");
});

test("scanner build cache is bumped for scanner recovery", () => {
  assert.match(appSource, /frontend-utils\.js\?v=outlet-pw-1/);
  assert.match(appSource, /zxing-library\.min\.js\?v=typed-pw-suggest-1/);
  assert.match(appSource, /data-action="save-next"/);
  assert.match(appSource, /state\.awaitingNextScan = true/);
  assert.match(appSource, /fetch\(`\/products\/lookup\//);
  assert.match(appSource, /location_id=\$\{encodeURIComponent\(state\.locationId\)\}/);
});

test("resolved catalog products preserve the exact scanned barcode", () => {
  const getProductSource = appSource.slice(appSource.indexOf("async function getProduct"), appSource.indexOf("function productSubtitle"));
  assert.match(getProductSource, /barcode: normalized/);
  assert.match(getProductSource, /catalog_barcode:/);
  assert.match(appSource, /barcode: line\.barcode/);
  assert.match(appSource, /currentProductCount\(product\)/);
});

test("camera validates barcode candidates and excludes ProcureWizard PIDs from physical index", () => {
  assert.match(appSource, /confirmBarcodeCandidate/);
  assert.match(appSource, /alias\.label === "ProcureWizard PID"/);
});

test("scanner startup attempts the camera regardless of permission-query support", () => {
  const initSource = appSource.slice(appSource.indexOf("async function init()"), appSource.indexOf("async function initServiceWorker()"));
  assert.match(initSource, /ensureCameraStarted\(\)\.catch\(reportCameraError\)/);
  assert.doesNotMatch(initSource, /camera_permission !== "granted"/);
});

test("phone export exposes all scanned lines without mapping", () => {
  assert.match(appSource, /downloadRawExportLink/);
  assert.match(appSource, /\/export\/scanned\//);
});

test("unknown scan can choose a ProcureWizard match before saving", () => {
  assert.match(appSource, /renderProcureWizardMatches/);
  assert.match(appSource, /data-action="choose-pw"/);
  assert.match(appSource, /Save & Next will map this barcode and count it against the PW row/);
  assert.match(appSource, /await cacheProduct\(product\)/);
});

test("unknown description suggests existing catalog products", () => {
  assert.match(appSource, /matchingCatalogProducts/);
  assert.match(appSource, /catalogProducts/);
  assert.match(appSource, /data-action="choose-existing-product"/);
  assert.match(appSource, /Start typing a product name/);
  assert.match(appSource, /No existing products match/);
  assert.match(appSource, /Save & Next will remember this barcode/);
});

test("typed unknown description searches ProcureWizard matches", () => {
  assert.match(appSource, /suggestUnknownDescription/);
  assert.match(appSource, /\/products\/matches\?name=/);
  assert.match(appSource, /data-action="choose-unknown-pw"/);
});

test("IndexedDB state uses an explicit serializable allowlist", () => {
  const saveStateSource = appSource.slice(appSource.indexOf("async function saveState"), appSource.indexOf("async function restoreState"));
  assert.match(saveStateSource, /const persistent = \{/);
  assert.match(saveStateSource, /await put\("state", persistent\)/);
  assert.doesNotMatch(saveStateSource, /key: "active",\s+\.\.\.state/);
  assert.doesNotMatch(saveStateSource, /sleeping: state\.sleeping/);
  assert.doesNotMatch(saveStateSource, /pendingBarcode: state\.pendingBarcode/);
});

test("a scan is only committed from the full-screen quantity confirmation", () => {
  const handleScanSource = appSource.slice(appSource.indexOf("async function handleScan"), appSource.indexOf("function rejectScan"));
  assert.match(handleScanSource, /showScanHud\(product, state\.quantity, total\)/);
  assert.doesNotMatch(handleScanSource, /commitScanQuantity/);
  assert.match(appSource, /data-action="save-next"/);
  assert.match(appSource, /if \(button\?\.dataset\.action === "save-next"\) confirmQuantity\(\)/);
});

test("full-screen confirmation has a thumb quantity keypad", () => {
  assert.match(appSource, /class="hud-keypad"/);
  assert.match(appSource, /data-action="quantity-key"/);
  assert.match(appSource, /data-replace-on-entry="true"/);
  assert.match(appSource, /data-action="quantity-backspace"/);
});

test("full-screen confirmation separates full and split case counts", () => {
  assert.match(appSource, /data-action="set-case-type"/);
  assert.match(appSource, /data-case-type="full"/);
  assert.match(appSource, /data-case-type="split"/);
  assert.match(appSource, /case_type: state\.caseType/);
  assert.match(appSource, /findExistingLineForProduct\(product, state\.caseType\)/);
});

test("phone outlet fallback includes the operational outlet list", () => {
  assert.match(appSource, /\{ id: "cellar", name: "Cellar" \}/);
  assert.match(appSource, /\{ id: "main-bar", name: "Bar" \}/);
  assert.match(appSource, /\{ id: "brasseries", name: "Brasseries" \}/);
  assert.match(appSource, /\{ id: "m-and-e", name: "M&E" \}/);
  assert.match(appSource, /state\.locationName = currentLocation\.name/);
});

test("go-live data epoch clears old phone queues before sync", () => {
  assert.match(appSource, /async function applyDataEpoch/);
  assert.match(appSource, /\["products", "lines", "events", "audit", "state"\]/);
  assert.match(appSource, /if \(!\(await syncCatalog\(\)\)\) return/);
  assert.match(appSource, /if \(await syncCatalog\(\)\) syncEvents\(\)/);
});
