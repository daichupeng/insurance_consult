/**
 * comparefirst.sg scraper
 *
 * Scrapes ALL product listings from comparefirst.sg via embedded XML,
 * then fetches rich detail pages for each requested policy.
 * Optionally performs a premium search with personal profile data.
 *
 * Usage:
 *   npm run scrape -- --type term --count 10
 *   npm run scrape -- --type all --count 5
 *   npm run scrape -- --type whole --count 20 --out results.json
 *
 *   # With premium search:
 *   npm run scrape -- --type term --count 10 \
 *     --dob 01/01/1990 --gender male --smoker no --sa 500000 --term 20
 *
 * Flags:
 *   --type   <term|whole|endowment|ilp|dpi_term|dpi_whole|all>  (default: all)
 *   --count  <N>           How many policies to fetch (default: 10)
 *   --out    <file>        Output filename (default: output/policies_<type>_<ts>.json)
 *
 *   Premium search (all required together):
 *   --dob    <DD/MM/YYYY>  Date of birth
 *   --gender <male|female>
 *   --smoker <yes|no>
 *   --sa     <amount>      Sum assured in SGD (e.g. 500000)
 *   --term   <years>       Coverage term in years — best-match used (e.g. 20)
 */

import "dotenv/config";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

if (!process.env.OPENAI_API_KEY) {
  const { config } = await import("dotenv");
  config({ path: path.resolve(__dirname, "../../.env") });
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface PolicyListing {
  id: string;
  insurerId: string;
  insurerName: string;
  productId: string;
  productName: string;
  productGroup: string;
  productSubCategory: string;
  productSubCategoryLabel: string;
  premiumPaymentMode: string;
  // Feature flags
  srsPremiumAllowed: boolean;
  cpfisAllowed: boolean;
  isLevelSumAssured: boolean;
  hasRenewability: boolean;
  // Riders
  ciRiderAvailable: boolean;
  tpdRiderAvailable: boolean;
  optionalRiders: string[];
  compulsoryRiders: string[];
  // Docs
  productSummaryPdf: string;
  brochureUrl: string;
  insurerInfoUrl: string;
  contactEmail: string;
  lastUpdatedOn: string;
}

interface SearchProfile {
  dob: string;       // "DD/MM/YYYY"
  gender: "M" | "F";
  smoker: "Y" | "N";
  sumAssured: number;
  term: number;      // coverage term in years
}

interface PremiumResult {
  annualPremium: string;
  coverageTerm: string;
  premiumTerm: string;
  totalPremium: string;
  distributionCost: string;
  creditRating: string;
  matchedSA: string;   // actual SA option selected (may differ from requested)
  matchedTerm: string; // actual term option selected
}

/** Premium data available from the search-results card (subset of PremiumResult). */
type ListingPremium = Pick<PremiumResult, "annualPremium" | "coverageTerm" | "premiumTerm" | "matchedSA" | "matchedTerm"> & {
  totalPremium: string;
  distributionCost: string;
  creditRating: string;
};

interface PolicyDetail extends PolicyListing {
  description: string;
  entryAgeMin: string;
  entryAgeMax: string;
  minSumAssured: string;
  maxSumAssured: string;
  policyTermsAvailable: string;
  premiumTermAvailable: string;
  premiumFrequency: string;
  underwritingType: string;
  ridersAvailableFromDetail: string[];
  annualPremium: string;       // only available after search — "Perform search to view"
  premiumResult?: PremiumResult;
  detailScraped: boolean;
}

// ── Sub-category labels ───────────────────────────────────────────────────────

const SUB_CAT: Record<string, string> = {
  LO: "Level SA — Renewable",
  LN: "Level SA — Non-Renewable",
  R3: "Reducing SA @ 3% p.a.",
  R5: "Reducing SA @ 5% p.a.",
  LP: "Level SA — Partial Payout",
  TV: "Varying SA",
  LC: "Limited Pay — Participating",
  SN: "Single Pay — Non-Participating",
  SC: "Single Pay — Participating",
  RC: "Regular Pay — Participating",
  RN: "Regular Pay — Non-Participating",
  SP: "ILP — Single Premium",
  RP: "ILP — Regular Premium",
  D: "Direct Purchase",
  OT: "Others",
};

// ── Product type config ───────────────────────────────────────────────────────

const BASE = "https://www.comparefirst.sg/wap";

const PRODUCT_TYPES: Record<string, { label: string; prodGroup: string; selCategory?: string }> = {
  term: { label: "Term Life", prodGroup: "term" },
  whole: { label: "Whole Life", prodGroup: "whole" },
  endowment: { label: "Endowment", prodGroup: "endow" },
  ilp: { label: "Investment-Linked Products", prodGroup: "invst" },
  dpi_term: { label: "DPI Term Life", prodGroup: "dpi", selCategory: "term-life" },
  dpi_whole: { label: "DPI Whole Life", prodGroup: "dpi", selCategory: "whole-life" },
};

function listingUrl(typeKey: string): string {
  const { prodGroup, selCategory } = PRODUCT_TYPES[typeKey];
  const base = `${BASE}/productsListEvent.action?prodGroup=${prodGroup}&pageAction=prodlisting`;
  return selCategory ? `${base}&selCategory=${selCategory}` : base;
}

// ── XML helpers ───────────────────────────────────────────────────────────────

const _tvCache = new Map<string, RegExp>();
function tv(xml: string, tag: string): string {
  let re = _tvCache.get(tag);
  if (!re) { re = new RegExp(`<${tag}>([\\s\\S]*?)</${tag}>`); _tvCache.set(tag, re); }
  const m = xml.match(re);
  return m ? m[1].trim() : "";
}
function tb(xml: string, tag: string): boolean { return tv(xml, tag).toUpperCase() === "Y"; }
function tl(xml: string, prefix: string, n: number): string[] {
  const r: string[] = [];
  for (let i = 1; i <= n; i++) { const v = tv(xml, `${prefix}${i}`); if (v && v !== "null") r.push(v); }
  return r;
}

// ── Parse embedded XML → listings ────────────────────────────────────────────

function parseXml(xml: string): PolicyListing[] {
  return xml.split("<Product>").slice(1).map(block => {
    const subCat = tv(block, "ProductSubCategory");
    const subCatId = tv(block, "ProductSubCategoryID");
    const subCatLabel = SUB_CAT[subCat] || SUB_CAT[subCatId] || subCat || subCatId;

    return {
      id: tv(block, "id"),
      insurerId: tv(block, "InsurerId"),
      insurerName: tv(block, "InsurerName"),
      productId: tv(block, "ProductId"),
      productName: tv(block, "ProductName"),
      productGroup: tv(block, "ProductGroup"),
      productSubCategory: subCat || subCatId,
      productSubCategoryLabel: subCatLabel,
      premiumPaymentMode: tv(block, "PremiumPaymentMode") === "A" ? "Annual" : tv(block, "PremiumPaymentMode"),
      srsPremiumAllowed: tb(block, "ProductFeatures4"),
      cpfisAllowed: tb(block, "ProductFeatures5"),
      isLevelSumAssured: tb(block, "ProductFeatures6") || subCat.startsWith("L"),
      hasRenewability: tb(block, "ProductFeatures7") || subCat === "LO",
      ciRiderAvailable: tb(block, "CiRideApp"),
      tpdRiderAvailable: tb(block, "TpdRideapp"),
      optionalRiders: tl(block, "OptlRide", 5),
      compulsoryRiders: tl(block, "CompulRide", 5),
      productSummaryPdf: tv(block, "ProductSummary2") ? `https://www.comparefirst.sg/documents/${tv(block, "ProductSummary2")}` : "",
      brochureUrl: tv(block, "brochureURL") !== "NA" ? `https://www.comparefirst.sg/documents/${tv(block, "brochureURL")}` : "",
      insurerInfoUrl: tv(block, "InsurerInfoURL"),
      contactEmail: tv(block, "ContactInsurer"),
      lastUpdatedOn: tv(block, "LastUpdatedOn"),
    };
  });
}

// ── Parse detail page text ────────────────────────────────────────────────────

function parseDetailText(text: string): Omit<PolicyDetail, keyof PolicyListing | "detailScraped"> {
  // Returns the first capture group or undefined (not "N/A") so || fallbacks work
  const find = (pattern: RegExp): string | undefined => text.match(pattern)?.[1]?.trim() || undefined;
  const first = (pattern: RegExp): string => find(pattern) ?? "N/A";

  // ── Description ──────────────────────────────────────────────────────────────
  // Page structure: ... "Perform search\nto\nview payout/premium details\n" + description + benefits
  const afterSearch = text.match(/view (?:payout|premium) details\n+([\s\S]+)/i)?.[1] || "";
  // Trim at the first heading-like line or download link
  const descRaw = afterSearch.match(/^([\s\S]+?)(?:\n[A-Z][^\n]+:|\nDownload|\nLast Updated)/)?.[1] || afterSearch.slice(0, 500);
  const description = descRaw.trim().replace(/\n{3,}/g, "\n\n").slice(0, 500);

  // ── Entry Age ─────────────────────────────────────────────────────────────────
  // Structured: "Entry Age: 16 to 70 age last birthday"
  const entryAgeMatch = text.match(/Entry Age[:\s]+(\d+)\s+to\s+(\d+)/i);
  const entryAgeMin = entryAgeMatch?.[1] || "N/A";
  const entryAgeMax = entryAgeMatch?.[2] || "N/A";

  // ── Sum Assured ───────────────────────────────────────────────────────────────
  // Helper: match a clean dollar amount like S$50,000 or S$1.5 million (no trailing comma)
  // Uses strict thousands-separator: comma MUST be followed by exactly 3 digits
  const SA = /S?\$\d{1,3}(?:,\d{3})*(?:\.\d+)?(?:\s*million)?/;

  // "Sum Assured range from S$X to S$Y"
  const saRangeMatch = text.match(new RegExp(`Sum Assured range from (${SA.source}) to (${SA.source})`, "i"));

  const minSAMatch = saRangeMatch ? [null, saRangeMatch[1]] :
    text.match(new RegExp(`Insured Amount[:\\s]+Min\\s+(${SA.source})`, "i")) ||
    text.match(new RegExp(`[Mm]in(?:imum)?\\.?\\s+[Ss]um [Aa]ssured[:\\s]+(?:of\\s+)?(${SA.source})`, "i")) ||
    text.match(new RegExp(`sum assured of (${SA.source})`, "i"));

  const maxSAMatch = saRangeMatch ? [null, saRangeMatch[2]] :
    text.match(new RegExp(`[Mm]ax(?:imum)?\\.?\\s+(?:Insured Amount|Sum Assured)[:\\s]+(${SA.source})`, "i")) ||
    text.match(new RegExp(`(?:covered|cover(?:age)?|up to)\\s+(?:of\\s+)?(${SA.source})`, "i"));

  // ── Policy Term ───────────────────────────────────────────────────────────────
  // Structured: "Policy Term Available: 5,10,15,20 years"
  // Free-form: "choice of policy terms ranging from 10 to 82 years"
  // Multiline: collect "- Fixed term: X\n- Renewable term: Y" style entries
  const termLines = [...text.matchAll(/^[-•]\s*((?:Fixed|Renewable|Single)\s+(?:term|premium)[^:\n]*?:\s*[^\n]+)/gim)].map(m => m[1].trim());
  const policyTermLine =
    find(/Policy Term Available[:\s]+([^\n]+)/i) ??
    find(/[•\-]\s*Choose your cover term[^:\-\n]*?[\-:]\s*([^\n•]+)/i) ??
    // "choice of policy terms ranging from X to Y" (standalone bullet or line start)
    find(/(?:^|[•\-\n])\s*(?:choice of )?policy terms?\s+(?:ranging from|[:\-])\s*([^\n.•,]+)/im) ??
    (termLines.length ? termLines.join("; ") : undefined) ??
    "N/A";

  // ── Premium Term ──────────────────────────────────────────────────────────────
  const premiumTermLine = first(/Premium Term Available[:\s]+([^\n]+)/i);

  // ── Premium Frequency ─────────────────────────────────────────────────────────
  const premFreqLine = first(/Premium Frequency[:\s]+([^\n]+)/i);

  // ── Underwriting ──────────────────────────────────────────────────────────────
  // Structured: "Type of Underwriting: Full underwriting"
  // Avoid matching mid-sentence occurrences like "...due to underwriting..."
  const uwLine = first(/(?:^|\n)\s*(?:Type of\s+)?Underwriting[:\s]+([^\n]+)/im);

  // ── Riders (from detail page) ─────────────────────────────────────────────────
  const ridersSection = text.match(/Riders Available[:\s•]+([\s\S]*?)(?=\n\n|Download|Last Updated)/i)?.[1] || "";
  const riders = ridersSection.split("\n").map(r => r.replace(/^[•\-\s]+/, "").trim()).filter(Boolean);

  // ── Annual Premium ────────────────────────────────────────────────────────────
  const annualPremium = text.includes("Perform search") ? "Requires search (age/gender/SA specific)" : first(/Annual Premium[:\s]+([^\n]+)/i);

  return {
    description,
    // entryAgeMin,
    // entryAgeMax,
    // minSumAssured: minSAMatch?.[1] || "N/A",
    // maxSumAssured: maxSAMatch?.[1] || "N/A",
    // policyTermsAvailable: policyTermLine,
    // premiumTermAvailable: premiumTermLine,
    // premiumFrequency: premFreqLine,
    underwritingType: uwLine,
    ridersAvailableFromDetail: riders,
    annualPremium,
  };
}

// ── Premium search helpers ────────────────────────────────────────────────────

/** Parse an option label like "S$50,000" or "S$1,000,000" → number */
function parseSALabel(label: string): number {
  return parseInt(label.replace(/[^0-9]/g, ""), 10) || 0;
}

/** Pick the SA option label closest to the requested amount */
function closestSAOption(requested: number, labels: string[]): string {
  let best = labels[0];
  let bestDiff = Infinity;
  for (const lbl of labels) {
    const diff = Math.abs(parseSALabel(lbl) - requested);
    if (diff < bestDiff) { bestDiff = diff; best = lbl; }
  }
  return best;
}

/**
 * Pick the coverage term option that best contains the requested years.
 * Handles: "5 Years", "20 Years", "To Age 65", "1 to 5", "16 to 20", "Above 40"
 */
function bestMatchTermOption(requestedYears: number, labels: string[]): string {
  // Score each option: prefer the option whose midpoint is closest to requestedYears
  let best = labels[0];
  let bestScore = Infinity;

  for (const lbl of labels) {
    const lower = lbl.toLowerCase();
    let lo = 0, hi = 0;

    const exact = lower.match(/^(\d+)\s*years?$/);
    const range = lower.match(/^(\d+)\s+to\s+(\d+)$/);
    const above = lower.match(/above\s+(\d+)/);
    const toAge = lower.match(/to age\s+(\d+)/);
    const singleYr = lower.match(/^(\d+)$/);

    if (exact) { lo = hi = parseInt(exact[1]); }
    else if (range) { lo = parseInt(range[1]); hi = parseInt(range[2]); }
    else if (above) { lo = parseInt(above[1]) + 1; hi = lo + 10; }
    else if (toAge) { lo = 1; hi = parseInt(toAge[1]); }
    else if (singleYr) { lo = hi = parseInt(singleYr[1]); }
    else { continue; }

    // If requested falls within range, score = 0; otherwise distance to nearest edge
    const score = requestedYears >= lo && requestedYears <= hi
      ? 0
      : Math.min(Math.abs(requestedYears - lo), Math.abs(requestedYears - hi));

    if (score < bestScore) { bestScore = score; best = lbl; }
  }
  return best;
}

// ── Per-product-type form field IDs ──────────────────────────────────────────
// Derived from validatefrm() source and DOM inspection of each listing page.
type FormFieldIds = {
  categoryId: string;    // data-id for ul.selCatg-life click (sets validatefrm's `catg`)
  bipsOptionId: string;  // data-id for ul.bips-option click (DPI only, sets bipsCatg)
  saId: string;
  covTermId: string;
  premTermId: string;
  premTypeId: string; premTypeVal: string;
  sortId: string; sortVal: string;   // REQUIRED by validatefrm
  premAmountId: string; premAmountVal: string;  // endowment only
};
const FORM_FIELD_IDS: Record<string, FormFieldIds> = {
  //           categoryId  bipsOption  saId              covTermId                  premTermId          premTypeId          premTypeVal  sortId           sortVal  premAmountId    premAmountVal
  term: { categoryId: "all", bipsOptionId: "", saId: "SATermLifeAll", covTermId: "coverageTermTLAllList", premTermId: "premiumTermAll", premTypeId: "premiumTypeOther", premTypeVal: "Annual", sortId: "sortNonWLGroup", sortVal: "1", premAmountId: "", premAmountVal: "" },
  whole: { categoryId: "all", bipsOptionId: "", saId: "SAWholeLifeAll", covTermId: "", premTermId: "premiumTermAll", premTypeId: "premiumTypeOther", premTypeVal: "Annual", sortId: "sortWLGroup", sortVal: "1", premAmountId: "", premAmountVal: "" },
  endowment: { categoryId: "all", bipsOptionId: "", saId: "", covTermId: "coverageTermEndow", premTermId: "", premTypeId: "premiumTypeOther", premTypeVal: "Annual", sortId: "sortEndoGroup", sortVal: "1", premAmountId: "PremAnnualGroup", premAmountVal: "5000" },
  dpi_term: { categoryId: "", bipsOptionId: "term-life", saId: "SADCIPTermAn", covTermId: "coverageTermTLDCIPs", premTermId: "premiumTermDcips", premTypeId: "premiumTypeDCIPs", premTypeVal: "Annual", sortId: "sortNonWLGroup", sortVal: "1", premAmountId: "", premAmountVal: "" },
  dpi_whole: { categoryId: "", bipsOptionId: "whole-life", saId: "SADCIPWLAn", covTermId: "", premTermId: "premiumTermDcips", premTypeId: "premiumTypeDCIPs", premTypeVal: "Annual", sortId: "sortWLGroup", sortVal: "1", premAmountId: "", premAmountVal: "" },
  ilp: { categoryId: "", bipsOptionId: "", saId: "", covTermId: "", premTermId: "", premTypeId: "", premTypeVal: "", sortId: "", sortVal: "", premAmountId: "", premAmountVal: "" },
};

/**
 * Fills ALL required search form fields on the current page via JS evaluate.
 * Works whether fields are visible (listing page) or hidden (detail page).
 * typeKey directs which product-specific select IDs to target.
 */
async function fillSearchForm(
  page: import("playwright").Page,
  profile: SearchProfile,
  typeKey: string,
): Promise<{ matchedSA: string; matchedTerm: string; matchedPremAmt: string }> {
  const ids = FORM_FIELD_IDS[typeKey] ?? FORM_FIELD_IDS["term"];

  // 0. Category / BIPS option — must be clicked FIRST so validatefrm() reads `catg`/`bipsCatg` correctly
  if (ids.categoryId) {
    await page.evaluate((catId: string) => {
      (document.querySelector(`ul.selCatg-life li[data-id="${catId}"]`) as HTMLElement | null)?.click();
    }, ids.categoryId);
  } else if (ids.bipsOptionId) {
    await page.evaluate((bipsId: string) => {
      (document.querySelector(`ul.bips-option li[data-id="${bipsId}"]`) as HTMLElement | null)?.click();
    }, ids.bipsOptionId);
  }

  // 1. DOB — also fire input + blur for jQuery datepicker compatibility
  await page.evaluate((dob) => {
    const el = document.querySelector<HTMLInputElement>("#date");
    if (!el) return;
    el.value = dob;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
  }, profile.dob);

  // 2. Gender — click the styled <li> AND set the backing hidden field
  await page.evaluate((g) => {
    (document.querySelector(`ul.gender li[data-id="${g}"]`) as HTMLElement | null)?.click();
    const h = document.querySelector<HTMLInputElement>("#selGender");
    if (h) { h.value = g; h.dispatchEvent(new Event("change", { bubbles: true })); }
  }, profile.gender);

  // 3. Smoker — click styled <li> AND set backing hidden field
  await page.evaluate((s) => {
    (document.querySelector(`ul#smoker li[data-id="${s}"]`) as HTMLElement | null)?.click();
    const h = document.querySelector<HTMLInputElement>("#selSmokStatus");
    if (h) { h.value = s; h.dispatchEvent(new Event("change", { bubbles: true })); }
  }, profile.smoker);

  // 4. Critical Illness Benefit — required field; default to "N" (No CI rider)
  await page.evaluate(() => {
    (document.querySelector('ul#illness-benefit li[data-id="N"]') as HTMLElement | null)?.click();
    const h = document.querySelector<HTMLInputElement>("#selCIRider");
    if (h) { h.value = "N"; h.dispatchEvent(new Event("change", { bubbles: true })); }
  });

  // 5. Premium Type — set the type-specific select to "Annual"
  await page.evaluate(({ id, val }: { id: string; val: string }) => {
    if (!id) return;
    const sel = document.querySelector<HTMLSelectElement>(`#${id}`);
    if (sel) { sel.value = val; sel.dispatchEvent(new Event("change", { bubbles: true })); }
  }, { id: ids.premTypeId, val: ids.premTypeVal });

  // 6. Sum Assured — use type-specific select ID
  const saLabels: string[] = await page.evaluate((saId: string) => {
    const sel = (saId ? document.querySelector<HTMLSelectElement>(`#${saId}`) : null)
      ?? (Array.from(document.querySelectorAll("select[id^='SA']")).find((s: any) => s.offsetParent !== null) as HTMLSelectElement | null);
    return sel ? Array.from(sel.options).map(o => o.text.trim()).filter(t => t && t !== "Select") : [];
  }, ids.saId);

  let matchedSA = "N/A";
  if (saLabels.length > 0) {
    matchedSA = closestSAOption(profile.sumAssured, saLabels);
    await page.evaluate(({ saId, lbl }: { saId: string; lbl: string }) => {
      const sel = (saId ? document.querySelector<HTMLSelectElement>(`#${saId}`) : null)
        ?? (Array.from(document.querySelectorAll("select[id^='SA']")).find((s: any) => s.offsetParent !== null) as HTMLSelectElement | null);
      if (sel) {
        const opt = Array.from(sel.options).find(o => o.text.trim() === lbl);
        if (opt) { sel.value = opt.value; sel.dispatchEvent(new Event("change", { bubbles: true })); }
      }
    }, { saId: ids.saId, lbl: matchedSA });
  }

  // 7. Coverage Term — use type-specific select ID
  const termLabels: string[] = await page.evaluate((covId: string) => {
    const sel = (covId ? document.querySelector<HTMLSelectElement>(`#${covId}`) : null)
      ?? (Array.from(document.querySelectorAll("select[id^='coverageTerm']")).find((s: any) => s.offsetParent !== null) as HTMLSelectElement | null);
    return sel ? Array.from(sel.options).map(o => o.text.trim()).filter(t => t && t !== "Select") : [];
  }, ids.covTermId);

  let matchedTerm = "N/A";
  if (termLabels.length > 0) {
    matchedTerm = bestMatchTermOption(profile.term, termLabels);
    await page.evaluate(({ covId, lbl }: { covId: string; lbl: string }) => {
      const sel = (covId ? document.querySelector<HTMLSelectElement>(`#${covId}`) : null)
        ?? (Array.from(document.querySelectorAll("select[id^='coverageTerm']")).find((s: any) => s.offsetParent !== null) as HTMLSelectElement | null);
      if (sel) {
        const opt = Array.from(sel.options).find(o => o.text.trim() === lbl);
        if (opt) { sel.value = opt.value; sel.dispatchEvent(new Event("change", { bubbles: true })); }
      }
    }, { covId: ids.covTermId, lbl: matchedTerm });
  }

  // 8. Premium Term — set to best match (same range format as coverage term)
  if (ids.premTermId) {
    const premTermLabels: string[] = await page.evaluate((id: string) => {
      const sel = document.querySelector<HTMLSelectElement>(`#${id}`);
      return sel ? Array.from(sel.options).map(o => o.text.trim()).filter(t => t && t !== "Select") : [];
    }, ids.premTermId);
    if (premTermLabels.length > 0) {
      const matchedPremTerm = bestMatchTermOption(profile.term, premTermLabels);
      await page.evaluate(({ id, lbl }: { id: string; lbl: string }) => {
        const sel = document.querySelector<HTMLSelectElement>(`#${id}`);
        if (sel) {
          const opt = Array.from(sel.options).find(o => o.text.trim() === lbl);
          if (opt) { sel.value = opt.value; sel.dispatchEvent(new Event("change", { bubbles: true })); }
        }
      }, { id: ids.premTermId, lbl: matchedPremTerm });
    }
  }

  // 9. Sort — REQUIRED by validatefrm; without this it returns false silently
  if (ids.sortId && ids.sortVal) {
    await page.evaluate(({ id, val }: { id: string; val: string }) => {
      const sel = document.querySelector<HTMLSelectElement>(`#${id}`);
      if (sel) { sel.value = val; sel.dispatchEvent(new Event("change", { bubbles: true })); }
    }, { id: ids.sortId, val: ids.sortVal });
  }

  // 10. Premium Amount — endowment only
  let matchedPremAmt = "N/A";
  if (ids.premAmountId && ids.premAmountVal) {
    matchedPremAmt = await page.evaluate(({ id, val }: { id: string; val: string }) => {
      const sel = document.querySelector<HTMLSelectElement>(`#${id}`);
      if (!sel) return "N/A";
      sel.value = val;
      sel.dispatchEvent(new Event("change", { bubbles: true }));
      const opt = Array.from(sel.options).find(o => o.selected);
      return opt?.text.trim() || val;
    }, { id: ids.premAmountId, val: ids.premAmountVal });
  }

  return { matchedSA, matchedTerm, matchedPremAmt };
}

/**
 * Performs the premium search on the LISTING page (where the form is primary/visible).
 * Fills the form, clicks Search via JS, waits for results, then extracts the annual
 * premium shown for each product card in the listing.
 * Returns a map: spanId → { annualPremium, matchedSA, matchedTerm }
 */
async function performListingSearch(
  page: import("playwright").Page,
  profile: SearchProfile,
  clickSelector: string,
  typeKey: string,
): Promise<{
  premiumMap: Map<string, ListingPremium>;
  resultSpanMap: Map<string, string>;   // key → spanId on the results page
  resultClickSelector: string;
  matchedSA: string;
  matchedTerm: string;
}> {
  // premiumMap is keyed by "insurerName|||productName" (not spanId) because
  // search results re-number span IDs sequentially — they don't match original listing IDs.
  const { matchedSA, matchedTerm, matchedPremAmt } = await fillSearchForm(page, profile, typeKey);

  // Click Search — may trigger a full page navigation (form submit) or AJAX reload.
  // Register waitForNavigation BEFORE the click so we don't miss it.
  await Promise.all([
    page.waitForNavigation({ waitUntil: "load", timeout: 20000 }).catch(() => { }),
    page.evaluate(() => {
      const btn = document.querySelector("#viewPopup") as HTMLElement | null;
      if (btn) btn.click();
    }),
  ]);

  // Wait until at least one result card renders (handles both navigation + AJAX responses)
  await page.waitForFunction(
    () => document.querySelectorAll("li.result_content").length > 0,
    { timeout: 15000 },
  ).catch(() => { }); // no results is valid (e.g. no matching products)

  // Click "Show More" until all results are loaded (results page also paginates like the listing)
  for (let tries = 0; tries < 50; tries++) {
    const btn = page.locator("a.load_more_btn, .load-more, #loadMore, [id*='loadMore'], [class*='load-more']").first();
    if (!(await btn.isVisible().catch(() => false))) break;
    const prevCount = await page.locator("li.result_content").count();
    await btn.click();
    await page.waitForFunction(
      (n: number) => document.querySelectorAll("li.result_content").length > n,
      prevCount, { timeout: 5000 },
    ).catch(() => { });
  }

  // Diagnostic: dump first li text so we can identify the premium selector
  const diag = await page.evaluate((sel: string) => {
    const firstLi = document.querySelector("li.result_content") as HTMLElement | null;
    const clickEl = firstLi?.querySelector(sel + "[id]") as HTMLElement | null;
    return {
      spanId: clickEl?.id || firstLi?.id || "",
      text: firstLi?.innerText?.replace(/\s+/g, " ").trim().slice(0, 600) || "(no li)",
      total: document.querySelectorAll("li.result_content").length,
    };
  }, clickSelector);
  console.log(`\n  [listing-search] ${diag.total} products shown. First full card (id=${diag.spanId}): ${diag.text}`);

  // Detect click selector on results page
  const resultClickSelector: string = await page.evaluate(() => {
    const li = document.querySelector("li.result_content");
    if (!li) return "span.detail_view";
    if (li.querySelector("span.detail_view[id]")) return "span.detail_view";
    if (li.querySelector("a.detail_view[id]")) return "a.detail_view";
    if (li.querySelector("span[id]")) return "span";
    if (li.querySelector("a[id]")) return "a";
    return "span.detail_view";
  });

  // Debug: find the search_detail click handler (look in external scripts via fetch)
  const dbgScriptUrls = await page.evaluate(() => {
    return Array.from(document.querySelectorAll("script[src]"))
      .map(s => (s as HTMLScriptElement).src)
      .filter(s => s.includes("comparefirst") || s.includes("wap"));
  });
  let found = false;
  for (const url of dbgScriptUrls.slice(0, 5)) {
    const resp = await page.evaluate(async (u: string) => {
      try {
        const r = await fetch(u);
        const txt = await r.text();
        const idx = txt.indexOf("search_detail");
        if (idx >= 0) return txt.slice(Math.max(0, idx - 100), idx + 400);
        return "";
      } catch { return ""; }
    }, url);
    if (resp) {
      console.log(`  [DBG-handler] Found in ${url.slice(-60)}: ${resp.replace(/\s+/g, " ").slice(0, 400)}`);
      found = true;
      break;
    }
  }
  if (!found) console.log(`  [DBG-handler] search_detail not found in ${dbgScriptUrls.length} scripts`);

  // Extract annual premium, coverage/premium term, spanId, and hidden detail fields from each listing card.
  const entries: { key: string; annualPremium: string; coverageTerm: string; premiumTerm: string; spanId: string; totalPremium: string; distributionCost: string; creditRating: string }[] = await page.evaluate((sel: string) => {
    return Array.from(document.querySelectorAll("li.result_content")).flatMap((li: any) => {
      const insurer = li.querySelector("h3")?.innerText?.trim() || "";
      const product = li.querySelector("p#sProdName, p[id='sProdName']")?.innerText?.trim() || "";
      if (!insurer && !product) return [];
      const key = `${insurer}|||${product}`;

      const clickEl = li.querySelector(sel + "[id]") as HTMLElement | null;
      const spanId = clickEl?.id || li.id || "";

      // Annual premium from dedicated element, or regex fallback on full card text
      const premiumEl =
        li.querySelector(".annual-premium") ||
        li.querySelector("[class*='annual-premium']") ||
        li.querySelector("[class*='annualPremium']");
      let annualPremium = (premiumEl as HTMLElement | null)?.innerText?.replace(/\s+/g, " ").trim() || "";
      const liText = (li as HTMLElement).innerText || "";
      if (!annualPremium) {
        annualPremium = liText.match(/S?\$\s*[\d,]+(?:\.\d{2})?(?:\s*p\.a\.)?/)?.[0]?.trim() || "";
      }

      // Coverage/premium term from "annually for N years" pattern (whole life cards)
      // or from a dedicated element (term/DPI cards).
      let coverageTerm = "N/A";
      let premiumTerm = "N/A";
      const payoutM = liText.match(/(?:annually|per year)[^\d]*for[^\d]*(\d+)\s*years?/i);
      if (payoutM) {
        premiumTerm  = payoutM[1] + " Years";
        coverageTerm = payoutM[1] + " Years";
      } else {
        const covEl = li.querySelector("[class*='coverage-term'], [class*='coverageTerm'], [class*='policy-term']") as HTMLElement | null;
        if (covEl) coverageTerm = covEl.innerText?.trim() || "N/A";
      }

      // Try to extract hidden detail fields from embedded panel sections within the card.
      // These may be CSS-hidden but DOM-present; use textContent (not innerText) to read them.
      // Note: avoid named helper functions here to prevent esbuild's __name helper being
      // serialized into the browser context where it is unavailable.
      const totRaw = (li.querySelector(".tot-premium, [class*='tot-premium']")?.textContent || "").replace(/\s+/g, " ").trim();
      const totMatch = totRaw.match(/S\$\s*[\d,]+(?:\.\d+)?/);
      const totalPremium = totMatch ? totMatch[0] : (totRaw || "N/A");
      const distRaw = (li.querySelector(".tot-dist-cost, [class*='tot-dist-cost'], [class*='dist-cost']")?.textContent || "").replace(/\s+/g, " ").trim();
      const distMatch = distRaw.match(/S\$\s*[\d,]+(?:\.\d+)?/);
      const distributionCost = distMatch ? distMatch[0] : (distRaw || "N/A");
      const creditRating = (li.querySelector(".insu-cr-rating, .insu-cr-rating1, [class*='cr-rating'], [class*='creditRating']")?.textContent || "").replace(/\s+/g, " ").trim() || "N/A";

      return [{ key, annualPremium, coverageTerm, premiumTerm, spanId, totalPremium, distributionCost, creditRating }];
    });
  }, resultClickSelector);

  const premiumMap = new Map<string, ListingPremium>();
  const resultSpanMap = new Map<string, string>();
  for (const { key, annualPremium, coverageTerm, premiumTerm, spanId, totalPremium, distributionCost, creditRating } of entries) {
    // For endowment: result cards show total premium over term, not annual.
    // Use the annual premium amount that was searched for (matchedPremAmt) instead.
    const effectivePremium = (typeKey === "endowment" && matchedPremAmt !== "N/A")
      ? matchedPremAmt + " p.a."
      : annualPremium;
    // For endowment, the card has no "annually for N years" text — fall back to matchedTerm for coverage/premium term.
    const effectiveCovTerm = (coverageTerm === "N/A" && matchedTerm !== "N/A") ? matchedTerm : coverageTerm;
    const effectivePremTerm = (premiumTerm === "N/A" && matchedTerm !== "N/A") ? matchedTerm : premiumTerm;
    if (effectivePremium) premiumMap.set(key, { annualPremium: effectivePremium, coverageTerm: effectiveCovTerm, premiumTerm: effectivePremTerm, matchedSA, matchedTerm, totalPremium, distributionCost, creditRating });
    resultSpanMap.set(key, spanId || "1");
  }
  return { premiumMap, resultSpanMap, resultClickSelector, matchedSA, matchedTerm };
}

// ── Expand Show More until a specific span element is in the DOM ──────────────
// Used by fetchDetailPage to avoid a full buildSpanMap rebuild on every product.

async function expandUntilVisible(page: import("playwright").Page, spanId: string, clickSelector: string): Promise<void> {
  for (let tries = 0; tries < 50; tries++) {
    if (await page.locator(`${clickSelector}[id="${spanId}"]`).count() > 0) break;
    const btn = page.locator("a.load_more_btn, .load-more, #loadMore, [id*='loadMore'], [class*='load-more']").first();
    if (!(await btn.isVisible().catch(() => false))) break;
    const prevCount = await page.locator("li.result_content").count();
    await btn.click();
    await page.waitForFunction(
      (n: number) => document.querySelectorAll("li.result_content").length > n,
      prevCount, { timeout: 5000 },
    ).catch(() => { });
  }
}

// ── Build product→spanId map from rendered page ───────────────────────────────
// The page renders li.result_content#{spanId} elements, each containing
// h3 (insurer) and p#sProdName (product name). The span inherits that id.
// We load all products by clicking "Show More" until no more exist, then
// build a map keyed by "insurerName|||productName".

interface SpanMapResult {
  map: Map<string, string>;
  clickSelector: string; // CSS selector for the clickable detail element
}

async function buildSpanMap(page: import("playwright").Page): Promise<SpanMapResult> {
  // Click "Show More" until all products are rendered
  for (let tries = 0; tries < 50; tries++) {
    const btn = page.locator("a.load_more_btn, .load-more, #loadMore, [id*='loadMore'], [class*='load-more']").first();
    if (!(await btn.isVisible().catch(() => false))) break;
    const prevCount = await page.locator("li.result_content").count();
    await btn.click();
    await page.waitForFunction(
      (n: number) => document.querySelectorAll("li.result_content").length > n,
      prevCount, { timeout: 5000 },
    ).catch(() => { });
  }

  // Detect the click selector used on this page (span.detail_view or an anchor/other)
  const clickSelector: string = await page.evaluate(() => {
    const li = document.querySelector("li.result_content");
    if (!li) return "span.detail_view";
    // Try common selectors in order of preference
    if (li.querySelector("span.detail_view[id]")) return "span.detail_view";
    if (li.querySelector("a.detail_view[id]")) return "a.detail_view";
    if (li.querySelector("span[id]")) return "span";
    if (li.querySelector("a[id]")) return "a";
    return "span.detail_view"; // fallback
  });

  // Extract (insurer, productName, elementId) from all li.result_content elements
  const entries: { key: string; spanId: string }[] = await page.evaluate((sel: string) => {
    return Array.from(document.querySelectorAll("li.result_content")).map((li: any) => {
      const insurer = li.querySelector("h3")?.innerText?.trim() || "";
      const product = li.querySelector("p#sProdName, p[id='sProdName']")?.innerText?.trim() || "";
      // Get the ID from the clickable element within the li
      const clickEl = li.querySelector(sel + "[id]") as HTMLElement | null;
      const spanId = (clickEl?.id || li.id || "");
      return { key: `${insurer}|||${product}`, spanId };
    }).filter((e: any) => e.spanId && e.key !== "|||");
  }, clickSelector);

  const map = new Map<string, string>();
  for (const { key, spanId } of entries) {
    map.set(key, spanId);
  }
  return { map, clickSelector };
}

// ── Fetch detail page by navigating and extracting rendered DOM ───────────────
// Clicks the span (navigates to detail page), waits for JS to render the
// product info, extracts innerText, then navigates back to the listing page.

/**
 * Navigate to a product detail page FROM the search results page.
 * The detail page loads with the premium breakdown pre-populated (search context carried over).
 * Returns the full detail including Coverage Term, Premium Term, Total Premium, etc.
 */
async function fetchDetailFromResultsPage(
  page: import("playwright").Page,
  listing: PolicyListing,
  resultSpanMap: Map<string, string>,
  clickSelector: string,
  resultsUrl: string,
  listingPremium: ListingPremium | undefined,
): Promise<PolicyDetail> {
  const mapKey = `${listing.insurerName}|||${listing.productName}`;
  if (!resultSpanMap.has(mapKey)) throw new Error(`Not found in search results: "${listing.productName}"`);

  // Intercept the network request to see what POST data is sent when clicking "View Details"
  const spanId = resultSpanMap.get(mapKey);
  let capturedRequest: { url: string; method: string; postData: string } | null = null;
  const capturedRequests: { url: string; method: string; postData: string }[] = [];
  const reqHandler = (request: import("playwright").Request) => {
    const url = request.url();
    // Capture ALL non-analytics requests
    if (!url.includes("google") && !url.includes("analytics") && !url.includes("gtag") && !url.includes("g.doubleclick")) {
      capturedRequests.push({ url: url.slice(-120), method: request.method(), postData: (request.postData() || "").slice(0, 200) });
    }
  };
  const navUrls: string[] = [];
  const navHandler = (frame: import("playwright").Frame) => {
    if (frame === page.mainFrame()) navUrls.push(frame.url().slice(-80));
  };
  page.on("request", reqHandler);
  page.on("framenavigated", navHandler);

  const preClickUrl = page.url();

  let clickAttempted = false;
  if (spanId) {
    // Try a.search_detail (whole life / term results page) or span.detail_view (DPI results page)
    for (const sel of [`a.search_detail[id="${spanId}"]`, `span.detail_view[id="${spanId}"]`, `a[id="${spanId}"]`, `span[id="${spanId}"]`]) {
      const locator = page.locator(sel).first();
      if (await locator.count() > 0) {
        await locator.click({ timeout: 5000 }).catch(() => { });
        clickAttempted = true;
        break;
      }
    }
  }
  if (!clickAttempted) {
    // Fallback: find by product name text and click any "View Details" link within
    const loc = page.locator(`li.result_content:has-text("${listing.productName.replace(/"/g, "'")}") a:has-text("View"), li.result_content:has-text("${listing.productName.replace(/"/g, "'")}") span.detail_view`).first();
    if (await loc.count() > 0) {
      await loc.click({ timeout: 5000 }).catch(() => { });
      clickAttempted = true;
    }
  }
  if (!clickAttempted) {
    throw new Error(`li/button not found in search results DOM for "${listing.productName}"`);
  }

  // Pause briefly and check URL to see if click caused any change
  await page.waitForTimeout(2000);
  console.log(`  [DBG-postclick] url=${page.url().slice(-80)}, navUrls=${navUrls.join("|")}`);

  // After click, detect EITHER:
  // (a) URL navigates away from search results (any URL that is not searchProductsEvent),
  //     then confirm by waiting for "Last Updated" text (detail page signal), OR
  // (b) In-page popup with .tab-area-content1.annual-premium populated (some non-DPI products).
  // Waiting for ANY departing URL (not just productDetailsEvent) covers whole-life detail pages
  // that may use a different event name. The "Last Updated" wait ensures we don't act on
  // fleeting intermediate URLs — if it never appears, the page wasn't a real detail page.
  let navigatedToDetail = false;
  let inPagePopup = false;
  try {
    await Promise.race([
      // Arm: any navigation away from the search results page
      page.waitForURL(url => {
        const h = url.href;
        return h !== preClickUrl && !h.includes("searchProductsEvent") && h !== resultsUrl;
      }, { timeout: 12000 }).then(() => { navigatedToDetail = true; }),
      // Arm: in-page popup without URL change.
      // Whole-life panels may embed the label ("Annual Premium") alongside the value
      // in the same element, so we detect by the presence of an S$ dollar amount.
      page.waitForFunction(() => {
        const el = document.querySelector(".tab-area-content1.annual-premium");
        const txt = ((el as HTMLElement | null)?.innerText ?? el?.textContent ?? "").trim();
        return /S\$\s*[\d,]/.test(txt);
      }, { timeout: 12000 }).then(() => { inPagePopup = true; }),
    ]);
  } catch {
    const curUrl = page.url();
    navigatedToDetail = curUrl !== preClickUrl && !curUrl.includes("searchProductsEvent")
      && curUrl !== resultsUrl;
  }
  if (!navigatedToDetail && !inPagePopup) {
    // Restore results page state so caller can continue with remaining products
    const currentUrl = page.url();
    if (!currentUrl.includes("searchProducts") && currentUrl !== preClickUrl) {
      await page.goto(resultsUrl, { waitUntil: "load", timeout: 20000 }).catch(() => { });
    }
    // Re-expand results list if collapsed
    for (let tries = 0; tries < 20; tries++) {
      const more = page.locator("a.load_more_btn, .load-more, #loadMore, [id*='loadMore'], [class*='load-more']").first();
      if (!(await more.isVisible().catch(() => false))) break;
      const prevMoreCount = await page.locator("li.result_content").count();
      await more.click();
      await page.waitForFunction(
        (n: number) => document.querySelectorAll("li.result_content").length > n,
        prevMoreCount, { timeout: 5000 },
      ).catch(() => { });
    }
    // Debug: capture page state to understand why detection failed
    const dbgUrl = page.url();
    const dbgInfo = await page.evaluate(() => {
      const ap = document.querySelector(".tab-area-content1.annual-premium") as HTMLElement | null;
      // Look for ANY element containing "S$" in a premium context
      const allPremiumEls = Array.from(document.querySelectorAll("[class*='premium'], [class*='Premium'], [class*='tot-'], [class*='pay-period'], [class*='coverage-term'], [class*='cr-rating']")).slice(0, 10)
        .map(el => `${el.className.slice(0, 40)}→"${(el as HTMLElement).innerText?.replace(/\s+/g, " ").trim().slice(0, 40)}"`);
      const detailSection = document.querySelector(".detail-content, .prodDetail, #prodDetail, .product-detail") as HTMLElement | null;
      const bodySnippet = (document.body as HTMLElement)?.innerText?.replace(/\s+/g, " ").trim().slice(0, 200);
      return {
        apFound: !!ap,
        apText: ap ? (ap.innerText || "").replace(/\s+/g, " ").trim().slice(0, 80) : "",
        allPremiumEls,
        detailSectionText: detailSection ? detailSection.innerText.replace(/\s+/g, " ").trim().slice(0, 100) : "",
        bodySnippet,
      };
    });
    page.off("request", reqHandler);
    page.off("framenavigated", navHandler);
    console.log(`  [DBG] url=...${dbgUrl.slice(-60)}`);
    console.log(`  [DBG] ap.found=${dbgInfo.apFound} ap.text="${dbgInfo.apText}"`);
    console.log(`  [DBG] premEls: ${dbgInfo.allPremiumEls.join(" | ").slice(0, 200)}`);
    console.log(`  [DBG] navUrls after click: ${navUrls.join(" → ") || "(none)"}`);
    capturedRequests.filter(r => r.url.includes("comparefirst") || r.url.includes("wap")).forEach((r, i) => {
      console.log(`  [DBG-req${i}] ${r.method} ${r.url}`);
      if (r.postData) console.log(`  [DBG-req${i}-post] ${r.postData}`);
    });
    throw new Error(`NEEDS_LISTING_NAV: "${listing.productName}" (no detail view appeared)`);
  }

  page.off("request", reqHandler);
  page.off("framenavigated", navHandler);
  // Debug: capture the URL we actually ended up at (term vs whole-life detail page)
  console.log(`  [DBG-detail-url] navigated=${navigatedToDetail} popup=${inPagePopup} url=...${page.url().slice(-80)}`);

  await page.waitForSelector("text=Last Updated", { timeout: 15000 }).catch(() => { });

  // Wait for premium elements to populate (filled async after page load)
  if (navigatedToDetail) {
    await Promise.race([
      page.waitForFunction(() => {
        const el = document.querySelector(".tab-area-content1.annual-premium");
        const txt = ((el as HTMLElement | null)?.innerText ?? el?.textContent ?? "").trim();
        return /S\$\s*[\d,]/.test(txt);
      }, { timeout: 8000 }),
      page.waitForFunction(() => {
        const el = document.querySelector(".txt-amt.payout");
        const txt = (el as HTMLElement | null)?.innerText?.trim() || "";
        return txt.length > 3;
      }, { timeout: 8000 }),
    ]).catch(() => { });
  }

  // Extract detail text
  const detailText = await page.evaluate(() => {
    document.querySelectorAll("script, style, noscript").forEach(el => el.remove());
    return (document.body as HTMLElement).innerText;
  });

  // Extract full premium breakdown.
  // Term/DPI: .tab-area-content1.* (popup). Whole life: .txt-amt.payout ("You will pay S$ X annually").
  // Note: whole-life panels may include the field label ("Annual Premium") in the same element as the
  // value, so we extract the S$ amount via regex rather than using the raw text verbatim.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const extracted: { annualPremium: string; coverageTerm: string; premiumTerm: string; totalPremium: string; distributionCost: string; creditRating: string } = await (page.evaluate as (s: string) => Promise<any>)(`(function() {
    function t(sel) {
      var el = document.querySelector(sel);
      if (!el) return "N/A";
      var text = (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
      return text || "N/A";
    }
    function amt(raw) {
      var m = raw.match(/S\\$\\s*[\\d,]+(?:\\.\\d+)?/);
      return m ? m[0] : raw;
    }
    var apRaw = t(".tab-area-content1.annual-premium");
    var apVal = amt(apRaw);
    if (/S\\$\\s*[\\d,]/.test(apVal)) {
      return {
        annualPremium:    apVal,
        coverageTerm:     t(".tab-area-content1.policy-coverage-term") || t(".tab-area-content1.policy-term"),
        premiumTerm:      t(".tab-area-content1.pay-period"),
        totalPremium:     amt(t(".tab-area-content1.tot-premium")),
        distributionCost: amt(t(".tab-area-content1.tot-dist-cost")),
        creditRating:     t(".tab-area-content1.insu-cr-rating") !== "N/A"
                            ? t(".tab-area-content1.insu-cr-rating")
                            : t(".tab-area-content1.insu-cr-rating1"),
      };
    }
    var payoutText = t(".txt-amt.payout");
    if (payoutText.indexOf("annually") !== -1) {
      var annualMatch = payoutText.match(/S\\$ ([\\d,]+) annually/);
      var termMatch   = payoutText.match(/for (\\d+) years/);
      return {
        annualPremium:    annualMatch ? "S$ " + annualMatch[1] : payoutText,
        coverageTerm:     termMatch ? termMatch[1] + " Years" : "N/A",
        premiumTerm:      termMatch ? termMatch[1] + " Years" : "N/A",
        totalPremium:     "N/A",
        distributionCost: "N/A",
        creditRating:     "N/A",
      };
    }
    return { annualPremium: "N/A", coverageTerm: "N/A", premiumTerm: "N/A", totalPremium: "N/A", distributionCost: "N/A", creditRating: "N/A" };
  })()`);

  const isPremiumPopulated = /S\$\s*[\d,]/.test(extracted.annualPremium);

  const premiumResult: PremiumResult | undefined = isPremiumPopulated
    ? { ...extracted, matchedSA: listingPremium?.matchedSA ?? "N/A", matchedTerm: listingPremium?.matchedTerm ?? "N/A" }
    : listingPremium
      ? {
        annualPremium: listingPremium.annualPremium,
        coverageTerm: listingPremium.coverageTerm,
        premiumTerm: listingPremium.premiumTerm,
        // Use card-extracted values (may have been populated from hidden DOM); fall back to N/A.
        totalPremium: listingPremium.totalPremium,
        distributionCost: listingPremium.distributionCost,
        creditRating: listingPremium.creditRating,
        matchedSA: listingPremium.matchedSA, matchedTerm: listingPremium.matchedTerm
      }
      : undefined;

  // Go back to results page
  await page.goBack({ waitUntil: "load", timeout: 20000 });

  // After goBack the results page may have reverted to its initial un-expanded state
  // (bfcache may not restore Show More clicks). Re-expand to restore all results.
  const liAfterBack = await page.locator("li.result_content").count().catch(() => 0);
  if (liAfterBack === 0) {
    // Full state lost — reload results URL
    await page.goto(resultsUrl, { waitUntil: "load", timeout: 30000 });
    await page.waitForFunction(
      () => document.querySelectorAll("li.result_content").length > 0,
      { timeout: 10000 },
    ).catch(() => { });
  }
  // Click Show More until all results are restored (may be needed if history state was lost)
  for (let tries = 0; tries < 50; tries++) {
    const btn2 = page.locator("a.load_more_btn, .load-more, #loadMore, [id*='loadMore'], [class*='load-more']").first();
    if (!(await btn2.isVisible().catch(() => false))) break;
    const prevCount2 = await page.locator("li.result_content").count();
    await btn2.click();
    await page.waitForFunction(
      (n: number) => document.querySelectorAll("li.result_content").length > n,
      prevCount2, { timeout: 5000 },
    ).catch(() => { });
  }

  const parsed = parseDetailText(detailText);
  return { ...listing, ...parsed, premiumResult, detailScraped: true };
}

async function fetchDetailPage(
  page: import("playwright").Page,
  listing: PolicyListing,
  spanMap: Map<string, string>,
  clickSelector: string,
  listingUrl: string,
  listingPremium?: ListingPremium,
  profile?: SearchProfile,
  typeKey?: string,
): Promise<PolicyDetail> {
  const mapKey = `${listing.insurerName}|||${listing.productName}`;
  const spanId = spanMap.get(mapKey);

  if (!spanId) {
    throw new Error(`No span found for "${listing.insurerName} — ${listing.productName}"`);
  }

  // Expand "Show More" only until this product's span is in the DOM (avoids full rebuild)
  await expandUntilVisible(page, spanId, clickSelector);

  // Click via JS using the detected selector for this page type
  const clickResult = await page.evaluate(({ id, sel }) => {
    const el = document.querySelector(`${sel}[id="${id}"]`) as HTMLElement | null;
    if (!el) {
      // Fallback: try any element with the id inside li.result_content
      const fallback = document.querySelector(`li.result_content[id="${id}"] span, li.result_content[id="${id}"] a`) as HTMLElement | null;
      if (fallback) { fallback.click(); return { ok: true, allSpans: -1 }; }
      const allEls = document.querySelectorAll(sel).length;
      return { ok: false, allSpans: allEls };
    }
    el.click();
    return { ok: true, allSpans: -1 };
  }, { id: spanId, sel: clickSelector });
  if (!clickResult.ok) {
    throw new Error(`Element [${clickSelector}][id="${spanId}"] not found (${clickResult.allSpans} total)`);
  }

  // Wait for navigation away from listing page
  const listingPageUrl = page.url();
  await page.waitForURL(url => url.href !== listingPageUrl, { timeout: 15000 });
  // Wait for "Last Updated" which appears after the product detail section renders
  await page.waitForSelector("text=Last Updated", { timeout: 15000 }).catch(() => { });

  // Debug: capture detail page URL and form structure
  const dbgDetail = await page.evaluate(() => {
    const detailUrl = window.location.href;
    const apEl = document.querySelector(".tab-area-content1.annual-premium") as HTMLElement | null;
    const dateInput = document.querySelector("#date, input[id*='date'], input[name*='date']") as HTMLInputElement | null;
    const forms = Array.from(document.querySelectorAll("form")).map(f => f.id || f.name || f.action || "unnamed");
    const fnNames = Object.keys(window).filter(k => k.toLowerCase().includes("search") || k.toLowerCase().includes("premium") || k.toLowerCase().includes("calc") || k.toLowerCase().includes("validate")).slice(0, 10);
    return {
      url: detailUrl.slice(-80),
      apFound: !!apEl,
      apText: apEl ? (apEl.innerText || "").replace(/\s+/g, " ").trim().slice(0, 80) : "",
      dateInputId: dateInput?.id || "",
      forms,
      globalFns: fnNames,
    };
  });
  const dbgFnSrc = await page.evaluate(() => {
    const fns: Record<string, string> = {};
    ["raiseSearchProductEvent", "modifySearch", "validatefrm"].forEach(name => {
      const fn = (window as any)[name];
      if (fn) fns[name] = fn.toString().replace(/\s+/g, " ").slice(0, 600);
    });
    // Also get all select ids on page
    const selects = Array.from(document.querySelectorAll("select")).map(s => `${s.id}(${s.options.length}opts)`);
    return { fns, selects };
  });
  console.log(`  [DBG-pass2] url=...${dbgDetail.url}`);
  console.log(`  [DBG-pass2] ap.found=${dbgDetail.apFound} ap="${dbgDetail.apText}"`);
  console.log(`  [DBG-pass2] dateInputId="${dbgDetail.dateInputId}" forms=${JSON.stringify(dbgDetail.forms)}`);
  console.log(`  [DBG-pass2] window fns: ${dbgDetail.globalFns.join(", ")}`);
  Object.entries(dbgFnSrc.fns).forEach(([k, v]) => console.log(`  [DBG-fn] ${k}: ${v}`));
  console.log(`  [DBG-selects] ${dbgFnSrc.selects.join(", ")}`);

  // Wait for premium elements — they may be pre-populated when browser carries search context
  await Promise.race([
    page.waitForFunction(() => {
      const el = document.querySelector(".tab-area-content1.annual-premium");
      const txt = ((el as HTMLElement | null)?.innerText ?? el?.textContent ?? "").trim();
      return /S\$\s*[\d,]/.test(txt);
    }, { timeout: 5000 }),
    page.waitForFunction(() => {
      const el = document.querySelector(".txt-amt.payout");
      return ((el as HTMLElement | null)?.innerText?.trim() || "").length > 3;
    }, { timeout: 5000 }),
  ]).catch(() => { });

  const detailText = await page.evaluate(() => {
    document.querySelectorAll("script, style, noscript").forEach(el => el.remove());
    return (document.body as HTMLElement).innerText;
  });

  // Try to extract premium from the detail page (.tab-area-content1.* or .txt-amt.payout).
  // Falls back to listingPremium (from card data) when not populated.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const extracted: { annualPremium: string; coverageTerm: string; premiumTerm: string; totalPremium: string; distributionCost: string; creditRating: string } = await (page.evaluate as (s: string) => Promise<any>)(`(function() {
    function t(sel) {
      var el = document.querySelector(sel);
      if (!el) return "N/A";
      var text = (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
      return text || "N/A";
    }
    function amt(raw) {
      var m = raw.match(/S\\$\\s*[\\d,]+(?:\\.\\d+)?/);
      return m ? m[0] : raw;
    }
    var apRaw = t(".tab-area-content1.annual-premium");
    var apVal = amt(apRaw);
    if (/S\\$\\s*[\\d,]/.test(apVal)) {
      return {
        annualPremium:    apVal,
        coverageTerm:     t(".tab-area-content1.policy-coverage-term") || t(".tab-area-content1.policy-term"),
        premiumTerm:      t(".tab-area-content1.pay-period"),
        totalPremium:     amt(t(".tab-area-content1.tot-premium")),
        distributionCost: amt(t(".tab-area-content1.tot-dist-cost")),
        creditRating:     t(".tab-area-content1.insu-cr-rating") !== "N/A"
                            ? t(".tab-area-content1.insu-cr-rating")
                            : t(".tab-area-content1.insu-cr-rating1"),
      };
    }
    var payoutText = t(".txt-amt.payout");
    if (payoutText.indexOf("annually") !== -1) {
      var annualMatch = payoutText.match(/S\\$ ([\\d,]+) annually/);
      var termMatch   = payoutText.match(/for (\\d+) years/);
      return {
        annualPremium:    annualMatch ? "S$ " + annualMatch[1] : payoutText,
        coverageTerm:     termMatch ? termMatch[1] + " Years" : "N/A",
        premiumTerm:      termMatch ? termMatch[1] + " Years" : "N/A",
        totalPremium:     "N/A", distributionCost: "N/A", creditRating: "N/A",
      };
    }
    return { annualPremium: "N/A", coverageTerm: "N/A", premiumTerm: "N/A", totalPremium: "N/A", distributionCost: "N/A", creditRating: "N/A" };
  })()`);

  const detailHasPremium = /S\$\s*[\d,]/.test(extracted.annualPremium);

  // If premium is not available from the detail page itself AND either listingPremium is missing
  // or incomplete, fill the search form on the detail page and submit it to get premium data
  // from the resulting search-results card. This handles whole-life products whose cards omit
  // the annual premium text and whose in-page popup doesn't work in headless mode.
  let formExtracted: { annualPremium: string; coverageTerm: string; premiumTerm: string; totalPremium: string; distributionCost: string; creditRating: string; matchedSA: string; matchedTerm: string } | undefined;
  if (!detailHasPremium && profile && typeKey && !listingPremium) {
    try {
      const { matchedSA, matchedTerm } = await fillSearchForm(page, profile, typeKey);
      await Promise.all([
        page.waitForNavigation({ waitUntil: "load", timeout: 20000 }).catch(() => { }),
        page.evaluate(() => { (window as any).validatefrm(); }),
      ]);
      // Load all products from the search results
      await page.waitForFunction(
        () => document.querySelectorAll("li.result_content").length > 0,
        { timeout: 15000 },
      ).catch(() => { });
      for (let tries = 0; tries < 50; tries++) {
        const btn = page.locator("a.load_more_btn, .load-more, #loadMore, [id*='loadMore'], [class*='load-more']").first();
        if (!(await btn.isVisible().catch(() => false))) break;
        const prevCount = await page.locator("li.result_content").count();
        await btn.click();
        await page.waitForFunction(
          (n: number) => document.querySelectorAll("li.result_content").length > n,
          prevCount, { timeout: 5000 },
        ).catch(() => { });
      }
      // Extract premium for this specific product from the results page card
      const searchInsurer = listing.insurerName;
      const searchProduct = listing.productName;
      const cardData: { annualPremium: string; coverageTerm: string; premiumTerm: string; totalPremium: string; distributionCost: string; creditRating: string } | null =
        await page.evaluate(({ ins, prod }) => {
          for (const li of Array.from(document.querySelectorAll("li.result_content"))) {
            const liEl = li as HTMLElement;
            const liIns = li.querySelector("h3")?.textContent?.trim() || "";
            const liProd = li.querySelector("p#sProdName, p[id='sProdName']")?.textContent?.trim() || "";
            if (liIns !== ins || liProd !== prod) continue;
            const liText = liEl.innerText || liEl.textContent || "";
            const annualMatch = liText.match(/S\$\s*([\d,]+)/);
            const payoutM = liText.match(/annually[^\d]*for[^\d]*(\d+)\s*years?/i);
            const totRaw = (li.querySelector(".tot-premium, [class*='tot-premium']")?.textContent || "").replace(/\s+/g, " ").trim();
            const totM = totRaw.match(/S\$\s*[\d,]+(?:\.\d+)?/);
            const distRaw = (li.querySelector(".tot-dist-cost, [class*='tot-dist-cost']")?.textContent || "").replace(/\s+/g, " ").trim();
            const distM = distRaw.match(/S\$\s*[\d,]+(?:\.\d+)?/);
            return {
              annualPremium:    annualMatch ? "S$ " + annualMatch[1] : "N/A",
              coverageTerm:     payoutM ? payoutM[1] + " Years" : "N/A",
              premiumTerm:      payoutM ? payoutM[1] + " Years" : "N/A",
              totalPremium:     totM ? totM[0] : (totRaw || "N/A"),
              distributionCost: distM ? distM[0] : (distRaw || "N/A"),
              creditRating:     (li.querySelector(".insu-cr-rating, .insu-cr-rating1, [class*='cr-rating']")?.textContent || "").replace(/\s+/g, " ").trim() || "N/A",
            };
          }
          return null;
        }, { ins: searchInsurer, prod: searchProduct });
      if (cardData && /S\$\s*[\d,]/.test(cardData.annualPremium)) {
        formExtracted = { ...cardData, matchedSA, matchedTerm };
      }
    } catch {
      // Ignore: form submit failed — continue with N/A premium
    }
  }

  const premiumResult: PremiumResult | undefined = detailHasPremium
    ? { ...extracted, matchedSA: listingPremium?.matchedSA ?? "N/A", matchedTerm: listingPremium?.matchedTerm ?? "N/A" }
    : formExtracted
      ? { ...formExtracted }
      : listingPremium
        ? {
          annualPremium: listingPremium.annualPremium,
          coverageTerm: listingPremium.coverageTerm,
          premiumTerm: listingPremium.premiumTerm,
          totalPremium: listingPremium.totalPremium,
          distributionCost: listingPremium.distributionCost,
          creditRating: listingPremium.creditRating,
          matchedSA: listingPremium.matchedSA,
          matchedTerm: listingPremium.matchedTerm,
        }
        : undefined;

  // Return to listing page.
  await page.goto(listingUrl, { waitUntil: "load", timeout: 30000 });
  await page.waitForFunction(
    () => { const el = document.querySelector<HTMLInputElement>("input[name=prodStringXML]"); return el && el.value.length > 0; },
    { timeout: 20000 },
  ).catch(() => { });

  // No span map rebuild needed — spanMap IDs are stable; expandUntilVisible at the
  // start of each fetchDetailPage call handles DOM visibility for the next product.

  const parsed = parseDetailText(detailText);
  return { ...listing, ...parsed, premiumResult, detailScraped: true };
}

// ── Playwright browser import ─────────────────────────────────────────────────

async function getPlaywright() {
  const pw = await import(path.resolve(__dirname, "node_modules/playwright/index.js"));
  const playwright = (pw as { default?: typeof pw } & typeof pw).default || pw;
  return playwright as { chromium: { launch: (opts: object) => Promise<import("playwright").Browser> } };
}

async function getBrowser() {
  const playwright = await getPlaywright();
  return playwright.chromium.launch({ headless: true });
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  const args = process.argv.slice(2);
  const get = (flag: string, def: string) => { const i = args.indexOf(flag); return i !== -1 ? args[i + 1] : def; };

  // Special: --dump-form loads the listing page and prints every form element then exits
  if (args.includes("--dump-form")) {
    const typeKey = get("--type", "term");
    const url = listingUrl(typeKey);
    const browser = await getBrowser();
    const page = await (await browser.newContext()).newPage();
    await page.goto(url, { waitUntil: "load", timeout: 30000 });
    await page.waitForFunction(
      () => { const el = document.querySelector<HTMLInputElement>("input[name=prodStringXML]"); return el && el.value.length > 0; },
      { timeout: 10000 },
    ).catch(() => { });
    const formDump = await page.evaluate(() => {
      const out: string[] = [];
      document.querySelectorAll("input, select, textarea, button").forEach((el: any) => {
        const tag = el.tagName.toLowerCase();
        const id = el.id || "";
        const name = el.name || "";
        const type = el.type || "";
        const cls = el.className || "";
        const val = el.value || "";
        if (tag === "select") {
          const opts = Array.from(el.options).map((o: any) => `${o.value}="${o.text.trim()}"`).join(", ");
          out.push(`<select id="${id}" name="${name}" class="${cls}"> OPTIONS: [${opts}]`);
        } else {
          out.push(`<${tag} id="${id}" name="${name}" type="${type}" class="${cls}" value="${val}">`);
        }
      });
      // Dump styled-li "radio" elements (gender, smoker, CI)
      document.querySelectorAll("ul li[data-id]").forEach((li: any) => {
        const ulId = li.closest("ul")?.id || li.closest("ul")?.className || "";
        out.push(`<li data-id="${li.dataset.id}" ul="${ulId}" text="${li.innerText?.trim()}">`);
      });
      // Dump span/a/div elements with onclick (search buttons etc.)
      document.querySelectorAll("[onclick][id]").forEach((el: any) => {
        out.push(`<${el.tagName.toLowerCase()} id="${el.id}" class="${el.className}" onclick="${el.getAttribute("onclick")}" text="${el.innerText?.trim().slice(0, 20)}">`);
      });
      return out.join("\n");
    });
    console.log("\n=== FORM DUMP ===");
    console.log(formDump);
    await browser.close();
    return;
  }

  const requestedType = get("--type", "all");
  const count = parseInt(get("--count", "10"));
  const outFlag = get("--out", "");

  // Premium search profile (all flags required together; skip if any missing)
  const dobFlag = get("--dob", "");
  const genderFlag = get("--gender", "");
  const smokerFlag = get("--smoker", "");
  const saFlag = get("--sa", "");
  const termFlag = get("--term", "");

  let profile: SearchProfile | undefined;
  if (dobFlag && genderFlag && smokerFlag && saFlag && termFlag) {
    profile = {
      dob: dobFlag,
      gender: genderFlag.toLowerCase().startsWith("m") ? "M" : "F",
      smoker: smokerFlag.toLowerCase().startsWith("y") ? "Y" : "N",
      sumAssured: parseInt(saFlag.replace(/[^0-9]/g, ""), 10),
      term: parseInt(termFlag, 10),
    };
    console.log(`\nPremium search profile: DOB=${profile.dob}, Gender=${profile.gender === "M" ? "Male" : "Female"}, Smoker=${profile.smoker === "Y" ? "Yes" : "No"}, SA=S$${profile.sumAssured.toLocaleString()}, Term=${profile.term}yr`);
  }

  const typesToScrape = requestedType === "all" ? Object.keys(PRODUCT_TYPES) : [requestedType];

  for (const t of typesToScrape) {
    if (!PRODUCT_TYPES[t]) {
      console.error(`Unknown type: "${t}". Valid: ${Object.keys(PRODUCT_TYPES).join(", ")}, all`);
      process.exit(1);
    }
  }

  const browser = await getBrowser();
  const context = await browser.newContext();
  const page = await context.newPage();

  const output: Record<string, { label: string; totalProducts: number; policies: PolicyDetail[] }> = {};

  try {
    for (const typeKey of typesToScrape) {
      const { label } = PRODUCT_TYPES[typeKey];
      const url = listingUrl(typeKey);

      console.log(`\n[${label}] Loading listing page...`);
      await page.goto(url, { waitUntil: "load", timeout: 30000 });

      // Wait until the hidden XML field is populated by the page's JS
      const xmlReady = await page.waitForFunction(
        () => {
          const el = document.querySelector<HTMLInputElement>("input[name=prodStringXML]");
          return el && el.value.length > 0 && !el.value.includes("<ProdList/>");
        },
        { timeout: 20000 },
      ).then(() => true).catch(() => false);

      const xml = await page.evaluate(() =>
        document.querySelector<HTMLInputElement>("input[name=prodStringXML]")?.value || ""
      );

      if (!xmlReady || !xml || xml.includes("<ProdList/>")) {
        // Diagnostics: show what selectors exist to help identify page structure changes
        const diagInfo = await page.evaluate(() => ({
          hasXmlField: !!document.querySelector("input[name=prodStringXML]"),
          xmlValue: document.querySelector<HTMLInputElement>("input[name=prodStringXML]")?.value?.slice(0, 80) || "",
          liCount: document.querySelectorAll("li.result_content").length,
          title: document.title,
        }));
        console.log(`  ⚠ No products found for ${label}`);
        console.log(`    title="${diagInfo.title}", hasXmlField=${diagInfo.hasXmlField}, liCount=${diagInfo.liCount}`);
        if (diagInfo.xmlValue) console.log(`    xmlValue starts with: ${diagInfo.xmlValue}`);
        continue;
      }

      const all = parseXml(xml);
      const selected = all.slice(0, count);
      console.log(`  ${all.length} products found. Fetching details for ${selected.length}...`);

      // Build span map (loads all products into DOM first)
      process.stdout.write("  Building product→span map...");
      const { map: spanMap, clickSelector } = await buildSpanMap(page);
      console.log(` ${spanMap.size} spans loaded.`);

      const policies: PolicyDetail[] = [];
      const emptyDetail = (listing: PolicyListing): PolicyDetail => ({
        ...listing, description: "", entryAgeMin: "N/A", entryAgeMax: "N/A",
        minSumAssured: "N/A", maxSumAssured: "N/A", policyTermsAvailable: "N/A",
        premiumTermAvailable: "N/A", premiumFrequency: "N/A", underwritingType: "N/A",
        ridersAvailableFromDetail: [], annualPremium: "N/A", detailScraped: false,
      });

      // If profile provided, perform listing search then navigate detail pages
      // FROM the results page so that the full premium breakdown is pre-populated.
      if (profile) {
        process.stdout.write("  Searching listing page for premiums...");
        let resultSpanMap = new Map<string, string>();
        let resultClickSelector = clickSelector;

        try {
          const result = await performListingSearch(page, profile, clickSelector, typeKey);
          resultSpanMap = result.resultSpanMap;
          resultClickSelector = result.resultClickSelector;
          console.log(` done (SA: ${result.matchedSA}, Term: ${result.matchedTerm}, ${result.premiumMap.size} premiums found).`);

          const resultsUrl = page.url(); // capture search results URL for re-navigation if needed

          // Pass 1: products found in search results — navigate from results page.
          // DPI products navigate to productDetailsEvent (full premium breakdown).
          // Non-DPI products (span.detail_view, form-submit) throw NEEDS_LISTING_NAV and go to pass 2.
          const notInResults: PolicyListing[] = [];
          // Preserve listing premiums for NEEDS_LISTING_NAV products so pass 2 can use them.
          const listingPremiumMap = new Map<string, ListingPremium>();
          for (let i = 0; i < selected.length; i++) {
            const listing = selected[i];
            const mapKey = `${listing.insurerName}|||${listing.productName}`;
            const lp = result.premiumMap.get(mapKey);
            process.stdout.write(`  [${i + 1}/${selected.length}] ${listing.insurerName} — ${listing.productName} ... `);
            if (!resultSpanMap.has(mapKey)) {
              // Product not in search results (incompatible SA/term or single-premium plan).
              // Still fetch detail page via listing nav; form-submit fallback will attempt premium extraction.
              console.log("(not in search results — queued for listing nav)");
              notInResults.push(listing);
              continue;
            }
            try {
              const detail = await fetchDetailFromResultsPage(page, listing, resultSpanMap, resultClickSelector, resultsUrl, lp);
              policies.push(detail);
              console.log("✓");
            } catch (err) {
              const msg = (err as Error).message;
              if (msg.startsWith("NEEDS_LISTING_NAV")) {
                // Non-DPI product: span form-submit can't reach productDetailsEvent from results page.
                // Queue for listing-page navigation (pass 2) which can navigate directly to detail page.
                console.log("(non-DPI: queued for listing nav with premium)");
                notInResults.push(listing);
                if (lp) listingPremiumMap.set(mapKey, lp);
              } else {
                console.log(`✗ (${msg.slice(0, 60)})`);
                policies.push(emptyDetail(listing));
              }
            }
          }

          // Pass 2: products not reachable from search results — reload listing and navigate normally.
          // Uses listingPremium (captured from search results card in pass 1) for premium data.
          if (notInResults.length > 0) {
            await page.goto(url, { waitUntil: "load", timeout: 30000 });
            await page.waitForFunction(
              () => { const el = document.querySelector<HTMLInputElement>("input[name=prodStringXML]"); return el && el.value.length > 0; },
              { timeout: 20000 },
            ).catch(() => { });
            const { map: freshMap, clickSelector: freshSel } = await buildSpanMap(page);
            for (const [k, v] of freshMap) spanMap.set(k, v);

            for (const listing of notInResults) {
              const mapKey = `${listing.insurerName}|||${listing.productName}`;
              const lp = listingPremiumMap.get(mapKey);
              process.stdout.write(`  [pass2] ${listing.insurerName} — ${listing.productName} ... `);
              try {
                const detail = await fetchDetailPage(page, listing, spanMap, freshSel, url, lp, profile, typeKey);
                policies.push(detail);
                console.log("✓");
              } catch (err) {
                console.log(`✗ (${(err as Error).message.slice(0, 60)})`);
                policies.push(emptyDetail(listing));
              }
            }
          }
        } catch (err) {
          console.log(` [listing search failed: ${(err as Error).message}]`);
          // Fall through to listing navigation without premium data
          await page.goto(url, { waitUntil: "load", timeout: 30000 });
          await page.waitForFunction(
            () => { const el = document.querySelector<HTMLInputElement>("input[name=prodStringXML]"); return el && el.value.length > 0; },
            { timeout: 20000 },
          ).catch(() => { });
          const { map: freshMap, clickSelector: freshSel } = await buildSpanMap(page);
          for (const [k, v] of freshMap) spanMap.set(k, v);
          for (let i = 0; i < selected.length; i++) {
            const listing = selected[i];
            process.stdout.write(`  [${i + 1}/${selected.length}] ${listing.insurerName} — ${listing.productName} ... `);
            try {
              const detail = await fetchDetailPage(page, listing, spanMap, freshSel, url, undefined, profile, typeKey);
              policies.push(detail);
              console.log("✓");
            } catch (err) {
              console.log(`✗ (${(err as Error).message.slice(0, 60)})`);
              policies.push(emptyDetail(listing));
            }
          }
        }
      } else {
        // No profile — standard listing navigation
        for (let i = 0; i < selected.length; i++) {
          const listing = selected[i];
          process.stdout.write(`  [${i + 1}/${selected.length}] ${listing.insurerName} — ${listing.productName} ... `);
          try {
            const detail = await fetchDetailPage(page, listing, spanMap, clickSelector, url);
            policies.push(detail);
            console.log("✓");
          } catch (err) {
            console.log(`✗ (${(err as Error).message.slice(0, 50)})`);
            policies.push(emptyDetail(listing));
          }
        }
      }

      output[typeKey] = { label, totalProducts: all.length, policies };
    }
  } finally {
    await browser.close();
  }

  // Save
  const outputDir = path.resolve(__dirname, "output");
  fs.mkdirSync(outputDir, { recursive: true });
  const timestamp = new Date().toISOString().slice(0, 19).replace(/[T:]/g, "-");
  const outFile = outFlag
    ? path.resolve(outFlag)
    : path.join(outputDir, `policies_${requestedType}_${timestamp}.json`);
  fs.writeFileSync(outFile, JSON.stringify(output, null, 2));

  // Print results
  for (const [, data] of Object.entries(output)) {
    console.log(`\n${"═".repeat(70)}`);
    console.log(`  ${data.label.toUpperCase()}  (${data.policies.length} of ${data.totalProducts} total products)`);
    console.log("═".repeat(70));

    for (const p of data.policies) {
      console.log(`\n  ┌─ ${p.insurerName}`);
      console.log(`  │  Product:           ${p.productName}`);
      console.log(`  │  Product ID:        ${p.productId}`);
      console.log(`  │  Category:          ${p.productSubCategoryLabel}`);
      console.log(`  │  Annual Premium:    ${p.annualPremium}`);
      if (p.premiumResult) {
        const pr = p.premiumResult;
        console.log(`  │  ── Premium Search Result ──────────────────────────────`);
        console.log(`  │  Annual Premium:    ${pr.annualPremium}  (SA: ${pr.matchedSA}, Term: ${pr.matchedTerm})`);
        console.log(`  │  Coverage Term:     ${pr.coverageTerm}`);
        console.log(`  │  Premium Term:      ${pr.premiumTerm}`);
        console.log(`  │  Total Premium:     ${pr.totalPremium}`);
        console.log(`  │  Distribution Cost: ${pr.distributionCost}`);
        console.log(`  │  Credit Rating:     ${pr.creditRating}`);
        console.log(`  │  ─────────────────────────────────────────────────────`);
      }
      // console.log(`  │  Entry Age:         ${p.entryAgeMin} – ${p.entryAgeMax}`);
      // console.log(`  │  Min Sum Assured:   ${p.minSumAssured}`);
      // console.log(`  │  Max Sum Assured:   ${p.maxSumAssured}`);
      // console.log(`  │  Policy Terms:      ${p.policyTermsAvailable}`);
      // console.log(`  │  Premium Term:      ${p.premiumTermAvailable}`);
      // console.log(`  │  Premium Frequency: ${p.premiumFrequency}`);
      // console.log(`  │  Underwriting:      ${p.underwritingType}`);
      console.log(`  │  Riders (optional): ${p.optionalRiders.join(", ") || "—"}`);
      console.log(`  │  Riders (compul.):  ${p.compulsoryRiders.join(", ") || "—"}`);
      console.log(`  │  SRS Payment:       ${p.srsPremiumAllowed ? "Yes" : "No"}`);
      console.log(`  │  CPFIS:             ${p.cpfisAllowed ? "Yes" : "No"}`);
      console.log(`  │  Renewable:         ${p.hasRenewability ? "Yes" : "No"}`);
      console.log(`  │  CI Rider Avail:    ${p.ciRiderAvailable ? "Yes" : "No"}`);
      console.log(`  │  TPD Rider Avail:   ${p.tpdRiderAvailable ? "Yes" : "No"}`);
      console.log(`  │  Last Updated:      ${p.lastUpdatedOn}`);
      console.log(`  │  Contact:           ${p.contactEmail}`);
      if (p.insurerInfoUrl) console.log(`  │  Info URL:          ${p.insurerInfoUrl}`);
      if (p.description) console.log(`  │  Description:       ${p.description.replace(/\n/g, "\n  │               ")}`);
      console.log("  └" + "─".repeat(60));
    }
  }

  console.log(`\n💾 Full JSON saved → ${outFile}`);
}

main().catch(err => { console.error("Fatal:", err); process.exit(1); });
