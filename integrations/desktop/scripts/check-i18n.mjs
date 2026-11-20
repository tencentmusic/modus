#!/usr/bin/env node
// Enforces the locale rules ("i18n" in AGENTS.md). en.json is the source of
// truth and zh.json must match it key for key. Other locales may lag, since
// missing keys fall back (zh-TW to zh, the rest to en), but they must not keep
// keys en.json has dropped, and every string must use en's placeholders.
import fs from 'node:fs';
import path from 'node:path';

const dir = path.join(process.cwd(), 'src', 'i18n');
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/;
const REQUIRED_COMPLETE = new Set(['zh']);

function flatten(obj, prefix = '', out = new Map()) {
  for (const [key, value] of Object.entries(obj)) {
    const full = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object') flatten(value, full, out);
    else out.set(full, String(value));
  }
  return out;
}

const baseKey = (key) => key.replace(PLURAL_SUFFIX, '');
const placeholders = (text) =>
  new Set([...text.matchAll(/\{\{\s*([\w.]+)/g)].map((m) => m[1]));

// Plural forms differ per language (en has _one/_other, ko only _other), so
// compare by base key, against the placeholders of all of en's forms.
function byBase(entries) {
  const out = new Map();
  for (const [key, text] of entries) {
    const base = baseKey(key);
    if (!out.has(base)) out.set(base, new Set());
    for (const name of placeholders(text)) out.get(base).add(name);
  }
  return out;
}

const read = (file) => flatten(JSON.parse(fs.readFileSync(path.join(dir, file), 'utf8')));
const en = byBase(read('en.json'));
const errors = [];
const summary = [];

for (const file of fs.readdirSync(dir).filter((f) => f.endsWith('.json') && f !== 'en.json').sort()) {
  const locale = file.replace(/\.json$/, '');
  const entries = read(file);
  const seen = new Set();
  for (const [key, text] of entries) {
    const base = baseKey(key);
    seen.add(base);
    const allowed = en.get(base);
    if (!allowed) {
      errors.push(`${file}: ${key} is not in en.json — delete it`);
      continue;
    }
    for (const name of placeholders(text)) {
      if (!allowed.has(name)) errors.push(`${file}: ${key} uses {{${name}}}, which en.json does not`);
    }
    if (!PLURAL_SUFFIX.test(key)) {
      for (const name of allowed) {
        if (!placeholders(text).has(name)) errors.push(`${file}: ${key} drops {{${name}}}`);
      }
    }
  }
  const missing = [...en.keys()].filter((base) => !seen.has(base));
  if (REQUIRED_COMPLETE.has(locale) && missing.length > 0) {
    errors.push(`${file}: missing ${missing.length} key(s) every UI change must add: ${missing.join(', ')}`);
  }
  summary.push(`${locale} ${missing.length} missing`);
}

if (errors.length > 0) {
  console.error(errors.join('\n'));
  console.error(`\ni18n check failed: ${errors.length} problem(s).`);
  process.exit(1);
}
console.log(`i18n check passed (${summary.join(', ')}).`);
