import { readFile } from "node:fs/promises";
import test from "node:test";
import assert from "node:assert/strict";

const appSource = await readFile(new URL("./app.js", import.meta.url), "utf8");

test("main scanner uses an app-controlled direct video decode loop", () => {
  assert.match(appSource, /reader\.decode\(els\.preview\)/);
  assert.match(appSource, /runZxingVideoLoop/);
  assert.doesNotMatch(appSource, /decodeFromConstraints/);
  assert.doesNotMatch(appSource, /decodeFromVideoElementContinuously\(els\.preview/);
  assert.doesNotMatch(appSource, /decodeFromImageElement/);
  assert.doesNotMatch(appSource, /runZxingRoiLoop/);
});

test("scanner build cache is bumped for controlled decoder rollout", () => {
  assert.match(appSource, /frontend-utils\.js\?v=scanner-controlled-1/);
  assert.match(appSource, /zxing-library\.min\.js\?v=scanner-controlled-1/);
});

test("IndexedDB state uses an explicit serializable allowlist", () => {
  const saveStateSource = appSource.slice(appSource.indexOf("async function saveState"), appSource.indexOf("async function restoreState"));
  assert.match(saveStateSource, /const persistent = \{/);
  assert.match(saveStateSource, /await put\("state", persistent\)/);
  assert.doesNotMatch(saveStateSource, /key: "active",\s+\.\.\.state/);
  assert.doesNotMatch(saveStateSource, /sleeping: state\.sleeping/);
  assert.doesNotMatch(saveStateSource, /pendingBarcode: state\.pendingBarcode/);
});
