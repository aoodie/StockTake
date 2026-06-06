import { readFile } from "node:fs/promises";
import test from "node:test";
import assert from "node:assert/strict";

const appSource = await readFile(new URL("./app.js", import.meta.url), "utf8");

test("main scanner uses ZXing-owned camera with direct video fallback", () => {
  assert.match(appSource, /decodeFromConstraints/);
  assert.match(appSource, /startZxingCameraLoop/);
  assert.match(appSource, /decodeFromVideoElementContinuously/);
  assert.match(appSource, /runZxingVideoLoop/);
  assert.doesNotMatch(appSource, /decodeFromImageElement/);
  assert.doesNotMatch(appSource, /runZxingRoiLoop/);
});

test("scanner build cache is bumped for owned camera rollout", () => {
  assert.match(appSource, /frontend-utils\.js\?v=scanner-owned-1/);
  assert.match(appSource, /zxing-library\.min\.js\?v=scanner-owned-1/);
});

test("IndexedDB state uses an explicit serializable allowlist", () => {
  assert.match(appSource, /const persistent = \{/);
  assert.match(appSource, /await put\("state", persistent\)/);
  assert.doesNotMatch(appSource, /key: "active",\s+\.\.\.state/);
});
