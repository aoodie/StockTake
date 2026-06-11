import { readFile } from "node:fs/promises";
import test from "node:test";
import assert from "node:assert/strict";

const mappingSource = await readFile(new URL("./mapping.js", import.meta.url), "utf8");
const mappingHtml = await readFile(new URL("./mapping.html", import.meta.url), "utf8");

test("mapping search clears its suggested query on focus", () => {
  assert.match(mappingSource, /els\.productSearch\.addEventListener\("focus"/);
  assert.match(mappingSource, /els\.productSearch\.value = ""/);
});

test("Scan Next is the only page-level reset action", () => {
  assert.match(mappingHtml, /id="mappingScanNext"/);
  assert.doesNotMatch(mappingHtml, /id="mappingClear"/);
  assert.match(mappingSource, /els\.scanNext\.addEventListener\("click", \(\) => resetForNext\(true\)\)/);
});
