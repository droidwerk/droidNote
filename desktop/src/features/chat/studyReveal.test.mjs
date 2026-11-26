// Rodar: cd desktop && node --test src/features/chat/studyReveal.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";

import { splitReveal } from "./studyReveal.ts";

test("hides the part after the last rule line", () => {
  const out = splitReveal("## Ideia\ntexto\n---\n## Perguntas\n1. A? [1]\n---\n1. Resposta A");
  assert.equal(out.visible, "## Ideia\ntexto\n---\n## Perguntas\n1. A? [1]");
  assert.equal(out.hidden, "1. Resposta A");
});

test("keeps text without a rule, with an empty tail, or with a rule inside code", () => {
  assert.equal(splitReveal("só texto").hidden, null);
  assert.equal(splitReveal("texto\n---\n  ").hidden, null);
  assert.equal(splitReveal("```\n---\ncode\n```").hidden, null);
});

test("details block becomes the hidden part without raw tags", () => {
  const out = splitReveal("1. A? [1]\n\n<details><summary>Resposta</summary>\nB\n</details>");
  assert.equal(out.visible, "1. A? [1]");
  assert.equal(out.hidden, "B");
});

test("a rule used as a section break keeps everything visible", () => {
  assert.equal(splitReveal("## Ideia\ntexto\n---\n## Mais\noutro texto").hidden, null);
  assert.equal(splitReveal("Pergunta [1]\n---\n- item").hidden, null);
});

test("flashcards and exam answers after --- are hidden", () => {
  const out = splitReveal("1. O que é A? [1]\n2. E B? [2]\n\n---\n\n1) A é x.\n2) B é y.");
  assert.equal(out.hidden, "1) A é x.\n2) B é y.");
});

