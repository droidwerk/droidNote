// Rodar: cd desktop && node --test src/features/session/sessionActions.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";

import { BULK_CHUNK, UNDO_MS, createSessionActions } from "./sessionActions.ts";

function setup({ live = null, confirmAnswer = true } = {}) {
  const calls = [];
  const toasts = [];
  const confirms = [];
  const actions = createSessionActions({
    bulk: async (ids, action) => {
      calls.push({ ids: [...ids], action });
      return { done: [...ids], failed: [] };
    },
    onChanged: async () => undefined,
    liveSessionId: live,
    t: (key) => key,
    plural: () => "other",
    push: (toast) => toasts.push(toast),
    confirm: async (options) => {
      confirms.push(options);
      return confirmAnswer;
    },
  });
  return { actions, calls, toasts, confirms };
}

const items = (n) => Array.from({ length: n }, (_, i) => ({ id: `s${i}`, title: `T${i}` }));

test("trash sends one bulk call and an undo toast of 10 s", async () => {
  const { actions, calls, toasts } = setup();
  await actions.apply(items(2), "trash");
  assert.deepEqual(calls, [{ ids: ["s0", "s1"], action: "trash" }]);
  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].durationMs, UNDO_MS);
  assert.equal(UNDO_MS, 10_000);
  assert.equal(toasts[0].action.undo, true);
});

test("undo restores the same ids", async () => {
  const { actions, calls, toasts } = setup();
  await actions.apply(items(2), "trash");
  toasts[0].action.onClick();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(calls[1], { ids: ["s0", "s1"], action: "restore" });
  assert.equal(toasts.at(-1).title, "archive.undone");
});

test("purge asks first and sends nothing on cancel", async () => {
  const { actions, calls, confirms } = setup({ confirmAnswer: false });
  const result = await actions.purge(items(1));
  assert.equal(result, null);
  assert.equal(confirms.length, 1);
  assert.equal(calls.length, 0);
});

test("purge on yes sends purge with no undo toast", async () => {
  const { actions, calls, toasts } = setup();
  await actions.purge(items(1));
  assert.deepEqual(calls, [{ ids: ["s0"], action: "purge" }]);
  assert.equal(toasts.length, 0);
});

test("the live session is left out and the toast says so", async () => {
  const { actions, calls, toasts } = setup({ live: "s1" });
  await actions.apply(items(3), "trash");
  assert.deepEqual(calls[0].ids, ["s0", "s2"]);
  assert.equal(toasts[0].description, "archive.liveSkipped");
});

test("only the live session: no call, info toast", async () => {
  const { actions, calls, toasts } = setup({ live: "s0" });
  await actions.apply(items(1), "archive");
  assert.equal(calls.length, 0);
  assert.equal(toasts[0].title, "archive.liveLocked");
});

test("empty trash of 1201 items goes in chunks of 500 after one confirm", async () => {
  const { actions, calls, confirms } = setup();
  const result = await actions.purge(items(1201), true);
  assert.equal(confirms.length, 1);
  assert.deepEqual(calls.map((call) => call.ids.length), [BULK_CHUNK, BULK_CHUNK, 201]);
  assert.equal(result.done.length, 1201);
});
