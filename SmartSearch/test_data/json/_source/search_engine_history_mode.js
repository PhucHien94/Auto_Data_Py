// Restricted-dimension search mode — ONLY for the "search-history verification"
// dataset (NSG_ExpectedData_history_top1000_<date>.json), NOT used by any of
// the regular NSG/WLE batches or the main "NSG Expected data" Artifact.
//
// Purpose (per user request 2026-08-27): this dataset re-runs the real
// 6-month search-history queries that returned the FEWEST results in the OLD
// production system (data/common_data/history_keywords_ranked.json, sorted
// worst-first) through the CURRENT engine, to verify whether search actually
// improved for them. For THIS round specifically, the user wants a narrower
// rule than the full engine:
//
//   - Only prioritize: exact/description keyword match, intent, "semantic"
//     (approximated here as the category/browse-intent tier, since this
//     simulator has no real embedding model — see search_engine.js's own
//     TIER_BRANCH "ai" grouping for the same equivalence), synonym, regional.
//   - Explicitly NOT this round: multi-language (name_en/name_kr) matching,
//     typo/spelling-correction. Diacritics-stripped ("no_diacritics") matching
//     is treated as the same class of "tolerate imperfect input" as typo
//     correction and also excluded, for the same reason - confirm this
//     reading is correct if it's not what was meant.
//   - Avoid 0-result answers: the weak last-resort "partial" (single-token
//     overlap) tier is kept as a safety net so a query isn't forced to 0 just
//     because it doesn't hit a stronger tier - it still can never outrank a
//     real match (unchanged scoring, see search_engine.js).
//   - New rule this dataset adds on top: a product whose name STARTS WITH the
//     query phrase ranks above a product where the query phrase appears
//     later in the name (e.g. query "nước ngọt" -> "Nước Ngọt Coca Cola..."
//     ranks above "Lốc 24 Lon Nước Ngọt Coca Cola..." / "Thùng 24 Lon Nước
//     Ngọt..." even if their tier/score/matchedWords are identical).
//
// This is implemented as a POST-FILTER + RE-RANK over the shared engine's own
// search() output, not a fork of the scoring logic itself - every tier/score
// number a result carries is still exactly what search_engine.js computed;
// this file only decides which tiers are allowed to survive into this
// dataset's results, and reorders survivors by the name-prefix rule.

(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.SearchEngineHistoryMode = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // exact/description/brand/partial = "keyword"; intent = "intent";
  // category = "semantic" (closest analog to the AI/embedding branch this
  // simulator doesn't have a real model for); synonym/regional as named.
  // Deliberately excluded: no_diacritics, typo, multilang.
  var ALLOWED_TIERS = { exact: 1, description: 1, brand: 1, partial: 1, intent: 1, category: 1, synonym: 1, regional: 1 };
  var SAFETY_NET_TIER = "partial";

  function normalizeForPrefix(s) {
    return String(s || "").trim().toLowerCase().replace(/\s+/g, " ");
  }

  // True if the product name starts with the query phrase (word-boundary
  // safe - "nước ngọt" must not match "nướcngọt" or "nước ngọtx" as a name
  // start, only a real leading-phrase match).
  function nameStartsWithQuery(productName, qNorm) {
    var name = normalizeForPrefix(productName);
    if (!qNorm) return false;
    if (!name.startsWith(qNorm)) return false;
    var next = name.charAt(qNorm.length);
    return next === "" || /[^\p{L}\p{N}]/u.test(next);
  }

  // SE: the loaded search_engine.js module (buildIndex/search/... exports).
  // index: result of SE.buildIndex(catalog) - same index the shared engine uses.
  function search(SE, index, query, opts) {
    opts = opts || {};
    var limit = opts.limit || Infinity;
    var full = SE.search(index, query, { skipTypo: true }); // belt-and-suspenders: also excludes typo at the source

    var filtered = full.filter(function (r) { return ALLOWED_TIERS[r.tier]; });
    var usedSafetyNet = false;
    if (filtered.length === 0 && full.some(function (r) { return r.tier === SAFETY_NET_TIER; })) {
      // already covered by ALLOWED_TIERS above (partial is allowed), kept
      // here only as an explicit documented fallback path in case the
      // allowed-tier set is narrowed further later.
      filtered = full.filter(function (r) { return r.tier === SAFETY_NET_TIER; });
      usedSafetyNet = true;
    }

    var qNorm = normalizeForPrefix(query);
    var withPrefix = filtered.map(function (r) {
      return { r: r, startsWithQuery: nameStartsWithQuery(r.product.name, qNorm) };
    });
    // Stable re-sort: name-prefix match first, then the engine's own already-
    // computed ordering (matchedWords > score > popularity) is preserved
    // among ties since Array#sort is stable and `filtered` arrived pre-sorted
    // from SE.search().
    withPrefix.sort(function (a, b) {
      if (a.startsWithQuery !== b.startsWithQuery) return a.startsWithQuery ? -1 : 1;
      return 0;
    });

    var out = withPrefix.map(function (x) { return x.r; });
    return {
      results: limit === Infinity ? out : out.slice(0, limit),
      totalBeforeCap: out.length,
      usedSafetyNet: usedSafetyNet,
      zeroResult: out.length === 0,
    };
  }

  return { search: search, ALLOWED_TIERS: ALLOWED_TIERS, nameStartsWithQuery: nameStartsWithQuery };
});
