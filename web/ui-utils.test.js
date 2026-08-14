import test from "node:test";
import assert from "node:assert/strict";
import { formatDuration, historyRows, presetId, tempColor } from "./ui-utils.js";
test("duration labels", () => { assert.equal(formatDuration(3660), "1h 01m"); assert.equal(formatDuration(NaN), "Not reached"); });
test("history triples", () => { assert.deepEqual(historyRows([0, 5, 5, 30, 6, 7]), [{time:0,cold:5,probe:5},{time:30,cold:6,probe:7}]); });
test("preset ids and colors", () => { assert.equal(presetId("bird"), 1); assert.equal(tempColor(NaN)[3], 0); assert.equal(tempColor(60).length, 4); });
