/// Skill search treats `-`, `_` and whitespace alike, so "wrap up" finds
/// `wrap-up` (#510). Normalize both the query and each searched field.
export function normalizeSkillSearch(value: string) {
  return value.toLowerCase().replace(/[-_\s]+/g, " ").trim();
}

/// `query` must already be normalized; an empty query matches everything.
export function skillSearchMatches(query: string, fields: (string | null | undefined)[]) {
  return !query || fields.some((field) => normalizeSkillSearch(field || "").includes(query));
}
