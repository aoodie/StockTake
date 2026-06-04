import { readFile } from "node:fs/promises";
import test from "node:test";
import assert from "node:assert/strict";

const appSource = await readFile(new URL("./app.js", import.meta.url), "utf8");

test("main scanner uses direct ZXing video decoding", () => {
  assert.match(appSource, /decodeFromVideoElementContinuously/);
  assert.match(appSource, /runZxingVideoLoop/);
  assert.doesNotMatch(appSource, /decodeFromImageElement/);
  assert.doesNotMatch(appSource, /runZxingRoiLoop/);
});

test("scanner build cache is bumped for video decoder rollout", () => {
  assert.match(appSource, /frontend-utils\.js\?v=scanner-video-1/);
  assert.match(appSource, /zxing-library\.min\.js\?v=scanner-video-1/);
});
