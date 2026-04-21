"""
comparefirst.sg Policy Crawler
================================
Crawls https://www.comparefirst.sg/wap/homeEvent.action and returns structured
policy data for Term Life, Whole Life, or Endowment products.

Usage (CLI):
    python crawler.py --type term   --dob 01/01/1990 --gender M --smoker N \
        --sum_assured 500000 --ci Y --coverage_term 20 --count 5

    python crawler.py --type whole  --dob 01/01/1990 --gender M --smoker N \
        --sum_assured 500000 --ci Y --premium_term 20 --count 5

    python crawler.py --type endowment --dob 01/01/1990 --gender M --smoker N \
        --premium_amount 5000 --ci Y --coverage_term 10 --count 5

Programmatic:
    from crawler import crawl_policies
    results = crawl_policies(
        product_type="term",
        dob="01/01/1990",
        gender="M",
        smoker="N",
        sum_assured=500000,
        ci="Y",
        coverage_term=20,
        count=5,
    )
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from typing import Optional

from playwright.sync_api import Page, sync_playwright

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.comparefirst.sg/wap"

# Form field IDs for each product type — derived from DOM inspection of
# https://www.comparefirst.sg/wap/productsListEvent.action?prodGroup=<X>
FORM_CONFIG: dict[str, dict] = {
    "term": {
        "prod_group": "term",
        "category_id": "all",          # ul.selCatg-life li[data-id]
        "sa_id": "SATermLifeAll",       # <select id="SATermLifeAll">
        "cov_term_id": "coverageTermTLAllList",  # coverage term dropdown
        "prem_term_id": "premiumTermAll",        # premium term dropdown
        "prem_type_id": "premiumTypeOther",      # premium type dropdown
        "sort_id": "sortNonWLGroup",    # sort dropdown
        "sort_val": "1",                # 1 = Lowest Premium
    },
    "whole": {
        "prod_group": "whole",
        "category_id": "all",
        "sa_id": "SAWholeLifeAll",
        "cov_term_id": None,            # no separate coverage term for whole life
        "prem_term_id": "premiumTermAll",
        "prem_type_id": "premiumTypeOther",
        "sort_id": "sortWLGroup",
        "sort_val": "1",
    },
    "endowment": {
        "prod_group": "endow",
        "category_id": "all",
        "sa_id": None,                  # no sum assured for endowment
        "cov_term_id": "coverageTermEndow",
        "prem_term_id": None,
        "prem_type_id": "premiumTypeOther",
        "sort_id": "sortEndoGroup",
        "sort_val": "1",
        "prem_amount_id": "PremAnnualGroup",  # premium amount dropdown
    },
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PolicyResult:
    """Basic policy information extracted from a search result detail page."""
    insurer: str = ""
    product_name: str = ""
    sub_type: str = ""
    sub_information: str = ""
    product_group: str = ""

    # Premiums
    annual_premium: str = "N/A"
    coverage_term: str = "N/A"
    premium_term: str = "N/A"
    total_premium: str = "N/A"
    distribution_cost: str = "N/A"
    credit_rating: str = "N/A"

    # Endowment-specific
    guaranteed_maturity_benefit: str = "N/A"

    # Docs
    product_summary_url: str = ""
    brochure_url: str = ""


# ---------------------------------------------------------------------------
# Helpers — term/SA matching
# ---------------------------------------------------------------------------

def _parse_amount(label: str) -> int:
    """Parse 'S$50,000' or '$1,000,000' → int."""
    digits = re.sub(r"[^\d]", "", label)
    return int(digits) if digits else 0


def _closest_sa(requested: int, labels: list[str]) -> str:
    """Return the SA option label closest to *requested*."""
    best, best_diff = labels[0], float("inf")
    for lbl in labels:
        diff = abs(_parse_amount(lbl) - requested)
        if diff < best_diff:
            best_diff, best = diff, lbl
    return best


def _closest_prem_amount(requested: int, labels: list[str]) -> str:
    """Return the premium-amount option label closest to *requested*."""
    return _closest_sa(requested, labels)  # same logic


def _best_term(requested_years: int, labels: list[str]) -> str:
    """
    Return the term option label that best contains *requested_years*.
    Handles: "5 Years", "20 Years", "To Age 65", "1 to 5", "Above 40", bare integers.
    """
    best, best_score = labels[0], float("inf")
    for lbl in labels:
        lo = hi = 0
        lower = lbl.lower()
        m_exact = re.match(r"^(\d+)\s*years?$", lower)
        m_range = re.match(r"^(\d+)\s+to\s+(\d+)$", lower)
        m_above = re.search(r"above\s+(\d+)", lower)
        m_toage = re.search(r"to\s+age\s+(\d+)", lower)
        m_int   = re.match(r"^(\d+)$", lower)
        if m_exact:
            lo = hi = int(m_exact.group(1))
        elif m_range:
            lo, hi = int(m_range.group(1)), int(m_range.group(2))
        elif m_above:
            lo = int(m_above.group(1)) + 1; hi = lo + 10
        elif m_toage:
            lo = 1; hi = int(m_toage.group(1))
        elif m_int:
            lo = hi = int(m_int.group(1))
        else:
            continue
        score = (0 if lo <= requested_years <= hi
                 else min(abs(requested_years - lo), abs(requested_years - hi)))
        if score < best_score:
            best_score, best = score, lbl
    return best


# ---------------------------------------------------------------------------
# Form filling
# ---------------------------------------------------------------------------

def _fill_form(
    page: Page,
    product_type: str,
    dob: str,
    gender: str,          # "M" or "F"
    smoker: str,          # "Y" or "N"
    ci: str,              # "Y" or "N"
    sum_assured: Optional[int],
    premium_amount: Optional[int],
    coverage_term: Optional[int],
    premium_term: Optional[int],
) -> dict[str, str]:
    """
    Fill all mandatory search-form fields and return a dict of matched options,
    e.g. {"matched_sa": "S$500,000", "matched_term": "20 Years"}.
    """
    cfg = FORM_CONFIG[product_type]

    # 1. Category — click the styled <li data-id="all">
    if cfg.get("category_id"):
        page.evaluate("""(catId) => {
            const el = document.querySelector(`ul.selCatg-life li[data-id="${catId}"]`);
            if (el) el.click();
        }""", cfg["category_id"])

    # 2. Date of birth
    page.evaluate("""(dob) => {
        const el = document.querySelector('#date');
        if (!el) return;
        el.value = dob;
        el.dispatchEvent(new Event('input',  { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur',   { bubbles: true }));
    }""", dob)

    # 3. Gender
    page.evaluate("""(g) => {
        const li = document.querySelector(`ul.gender li[data-id="${g}"]`);
        if (li) li.click();
        const h = document.querySelector('#selGender');
        if (h) { h.value = g; h.dispatchEvent(new Event('change', { bubbles: true })); }
    }""", gender)

    # 4. Smoker
    page.evaluate("""(s) => {
        const li = document.querySelector(`ul#smoker li[data-id="${s}"]`);
        if (li) li.click();
        const h = document.querySelector('#selSmokStatus');
        if (h) { h.value = s; h.dispatchEvent(new Event('change', { bubbles: true })); }
    }""", smoker)

    # 5. Critical Illness Benefit
    page.evaluate("""(ci) => {
        const li = document.querySelector(`ul#illness-benefit li[data-id="${ci}"]`);
        if (li) li.click();
        const h = document.querySelector('#selCIRider');
        if (h) { h.value = ci; h.dispatchEvent(new Event('change', { bubbles: true })); }
    }""", ci)

    # 6. Premium Type = Annual
    prem_type_id = cfg.get("prem_type_id")
    if prem_type_id:
        page.evaluate("""(id) => {
            const sel = document.querySelector(`#${id}`);
            if (sel) { sel.value = 'Annual'; sel.dispatchEvent(new Event('change', { bubbles: true })); }
        }""", prem_type_id)

    # 7. Sum Assured (term / whole life) or Premium Amount (endowment)
    matched = {"matched_sa": "N/A", "matched_term": "N/A", "matched_prem_amount": "N/A"}

    sa_id = cfg.get("sa_id")
    prem_amount_id = cfg.get("prem_amount_id")

    if sa_id and sum_assured is not None:
        sa_labels: list[str] = page.evaluate("""(id) => {
            const sel = document.querySelector(`#${id}`)
                     || Array.from(document.querySelectorAll("select[id^='SA']"))
                            .find(s => s.offsetParent !== null);
            return sel ? Array.from(sel.options).map(o => o.text.trim()).filter(t => t && t !== 'Select') : [];
        }""", sa_id)
        if sa_labels:
            matched_sa = _closest_sa(sum_assured, sa_labels)
            matched["matched_sa"] = matched_sa
            page.evaluate("""([id, lbl]) => {
                const sel = document.querySelector(`#${id}`)
                         || Array.from(document.querySelectorAll("select[id^='SA']"))
                                .find(s => s.offsetParent !== null);
                if (!sel) return;
                const opt = Array.from(sel.options).find(o => o.text.trim() === lbl);
                if (opt) { sel.value = opt.value; sel.dispatchEvent(new Event('change', { bubbles: true })); }
            }""", [sa_id, matched_sa])

    elif prem_amount_id and premium_amount is not None:
        prem_labels: list[str] = page.evaluate("""(id) => {
            const sel = document.querySelector(`#${id}`);
            return sel ? Array.from(sel.options).map(o => o.text.trim()).filter(t => t && t !== 'Select') : [];
        }""", prem_amount_id)
        if prem_labels:
            matched_pa = _closest_prem_amount(premium_amount, prem_labels)
            matched["matched_prem_amount"] = matched_pa
            page.evaluate("""([id, lbl]) => {
                const sel = document.querySelector(`#${id}`);
                if (!sel) return;
                const opt = Array.from(sel.options).find(o => o.text.trim() === lbl);
                if (opt) { sel.value = opt.value; sel.dispatchEvent(new Event('change', { bubbles: true })); }
            }""", [prem_amount_id, matched_pa])

    # 8. Coverage Term (term life, endowment)
    cov_term_id = cfg.get("cov_term_id")
    if cov_term_id and coverage_term is not None:
        cov_labels: list[str] = page.evaluate("""(id) => {
            const sel = document.querySelector(`#${id}`)
                     || Array.from(document.querySelectorAll("select[id^='coverageTerm']"))
                            .find(s => s.offsetParent !== null);
            return sel ? Array.from(sel.options).map(o => o.text.trim()).filter(t => t && t !== 'Select') : [];
        }""", cov_term_id)
        if cov_labels:
            matched_term = _best_term(coverage_term, cov_labels)
            matched["matched_term"] = matched_term
            page.evaluate("""([id, lbl]) => {
                const sel = document.querySelector(`#${id}`)
                         || Array.from(document.querySelectorAll("select[id^='coverageTerm']"))
                                .find(s => s.offsetParent !== null);
                if (!sel) return;
                const opt = Array.from(sel.options).find(o => o.text.trim() === lbl);
                if (opt) { sel.value = opt.value; sel.dispatchEvent(new Event('change', { bubbles: true })); }
            }""", [cov_term_id, matched_term])

    # 9. Premium Term (whole life)
    prem_term_id = cfg.get("prem_term_id")
    if prem_term_id and premium_term is not None:
        pt_labels: list[str] = page.evaluate("""(id) => {
            const sel = document.querySelector(`#${id}`);
            return sel ? Array.from(sel.options).map(o => o.text.trim()).filter(t => t && t !== 'Select') : [];
        }""", prem_term_id)
        if pt_labels:
            matched_pt = _best_term(premium_term, pt_labels)
            # Only update matched_term if coverage_term wasn't already set
            if matched["matched_term"] == "N/A":
                matched["matched_term"] = matched_pt
            page.evaluate("""([id, lbl]) => {
                const sel = document.querySelector(`#${id}`);
                if (!sel) return;
                const opt = Array.from(sel.options).find(o => o.text.trim() === lbl);
                if (opt) { sel.value = opt.value; sel.dispatchEvent(new Event('change', { bubbles: true })); }
            }""", [prem_term_id, matched_pt])

    # 10. Sort — required by validatefrm(); "1" = Lowest Premium first
    sort_id = cfg.get("sort_id")
    if sort_id:
        page.evaluate("""(id) => {
            const sel = document.querySelector(`#${id}`);
            if (sel) { sel.value = '2'; sel.dispatchEvent(new Event('change', { bubbles: true })); }
        }""", sort_id)

    return matched


# ---------------------------------------------------------------------------
# Detail page extraction
# ---------------------------------------------------------------------------

def _extract_detail(page: Page, product_type: str) -> dict[str, str]:
    """
    Extract premium breakdown from a product detail page.
    Handles both the tab-area popup style (term/endowment) and in-line whole-life style.
    """
    result: dict[str, str] = page.evaluate("""(productType) => {
        // t(sel): returns text of FIRST element matching sel that has non-empty content.
        // Falls back to querySelector for backwards compat.
        function t(sel) {
            var els = document.querySelectorAll(sel);
            for (var i = 0; i < els.length; i++) {
                var txt = (els[i].innerText || els[i].textContent || '').replace(/\\s+/g, ' ').trim();
                if (txt) return txt;
            }
            return 'N/A';
        }
        function amt(raw) {
            var m = raw.match(/S\\$\\s*[\\d,]+(?:\\.\\d+)?/);
            return m ? m[0] : raw;
        }

        // --- Primary: tab-area popup (term life, whole life, endowment) ---
        var apRaw = t('.tab-area-content1.annual-premium');
        if (/S\\$\\s*[\\d,]/.test(amt(apRaw))) {
            var covTerm = t('.tab-area-content1.policy-coverage-term');
            if (covTerm === 'N/A') covTerm = t('.tab-area-content1.policy-term');
            var crRaw1 = t('.tab-area-content1.insu-cr-rating');
            var cr1 = crRaw1 !== 'N/A' ? crRaw1 : t('.tab-area-content1.insu-cr-rating1');
            return {
                annual_premium:    amt(apRaw),
                coverage_term:     covTerm,
                premium_term:      t('.tab-area-content1.pay-period'),
                total_premium:     amt(t('.tab-area-content1.tot-premium')),
                distribution_cost: amt(t('.tab-area-content1.tot-dist-cost')),
                credit_rating:     cr1,
                guaranteed_maturity_benefit: productType === 'endowment'
                    ? amt(t('.tab-area-content1.guaranteed-maturity-benefit, .tab-area-content1.maturity-benefit, .tab-area-content1.maturity'))
                    : 'N/A',
            };
        }

        // --- Fallback: whole-life "You will pay S$ X annually for N years" sentence ---
        var payoutText = t('.txt-amt.payout');
        if (payoutText.indexOf('annually') !== -1) {
            var mAmt  = payoutText.match(/S\\$\\s*([\\d,]+)\\s*annually/);
            var mYrs  = payoutText.match(/for\\s+(\\d+)\\s*years/);
            return {
                annual_premium:    mAmt ? 'S$ ' + mAmt[1] : payoutText,
                coverage_term:     mYrs ? mYrs[1] + ' Years' : 'N/A',
                premium_term:      mYrs ? mYrs[1] + ' Years' : 'N/A',
                total_premium:     'N/A',
                distribution_cost: 'N/A',
                credit_rating:     'N/A',
                guaranteed_maturity_benefit: 'N/A',
            };
        }

        return {
            annual_premium: 'N/A', coverage_term: 'N/A', premium_term: 'N/A',
            total_premium: 'N/A', distribution_cost: 'N/A', credit_rating: 'N/A',
            guaranteed_maturity_benefit: 'N/A',
        };
    }""", product_type)
    return result


def _wait_for_premium_content(page: Page, timeout_ms: int = 12000) -> None:
    """
    Poll until any .tab-area-content1.annual-premium element has a S$ value, or timeout.
    Uses page.evaluate() (CDP injection — not subject to page CSP) for polling.
    """
    import time
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        try:
            text = page.evaluate("""() => {
                var els = document.querySelectorAll('.tab-area-content1.annual-premium');
                for (var i = 0; i < els.length; i++) {
                    var t = (els[i].innerText || els[i].textContent || '').trim();
                    if (t.match(/S\\$\\s*[\\d,]/)) return t;
                }
                return '';
            }""") or ""
            if "S$" in text:
                return
        except Exception:
            pass
        page.wait_for_timeout(400)


def _extract_doc_links(page: Page) -> dict[str, str]:
    """
    Extract product summary PDF and brochure links from the detail page.
    Covers /documents/, /wap/prodSummaryPdf/, /wap/brochure/ URL patterns.
    """
    links: dict[str, str] = page.evaluate("""() => {
        var result = { product_summary_url: '', brochure_url: '' };
        var anchors = Array.from(document.querySelectorAll('a[href]'));
        for (var i = 0; i < anchors.length; i++) {
            var a = anchors[i];
            var href = a.href || '';
            var text = (a.innerText || a.textContent || '').toLowerCase().trim();
            var title = (a.title || '').toLowerCase();
            var hrefL = href.toLowerCase();
            var isPdf = hrefL.includes('.pdf') || hrefL.includes('prodsummarypdf') || hrefL.includes('/brochure/');
            if (!isPdf) continue;
            if (!result.product_summary_url &&
                (text.includes('product summary') || title.includes('product summary') ||
                 hrefL.includes('summary') || hrefL.includes('ps_') || hrefL.includes('_ps'))) {
                result.product_summary_url = href;
            } else if (!result.brochure_url &&
                (text.includes('brochure') || title.includes('brochure') ||
                 hrefL.includes('brochure') || hrefL.includes('broc'))) {
                result.brochure_url = href;
            } else if (!result.product_summary_url) {
                result.product_summary_url = href;
            } else if (!result.brochure_url) {
                result.brochure_url = href;
            }
        }
        return result;
    }""")
    return links


# ---------------------------------------------------------------------------
# Load More helper
# ---------------------------------------------------------------------------

def _load_all_results(page: Page, max_items: int) -> None:
    """Click 'Show More' until we have >= max_items results or no more button."""
    for _ in range(50):
        count = page.locator("li.result_content").count()
        if count >= max_items:
            break
        btn = page.locator(
            "a.load_more_btn, .load-more, #loadMore, [id*='loadMore'], [class*='load-more']"
        ).first
        if not btn.is_visible():
            break
        btn.click()
        # Wait for new items — use locator count check to avoid CSP eval restriction
        try:
            page.locator(f"li.result_content:nth-child({count + 1})").wait_for(timeout=7000)
        except Exception:
            break


# ---------------------------------------------------------------------------
# Core crawl logic
# ---------------------------------------------------------------------------

def _detect_click_selector(page: Page) -> str:
    """Detect which selector is used for the 'View Details' element in result cards."""
    return page.evaluate("""() => {
        var li = document.querySelector('li.result_content');
        if (!li) return 'span.detail_view';
        if (li.querySelector('span.detail_view[id]')) return 'span.detail_view';
        if (li.querySelector('a.search_detail[id]'))  return 'a.search_detail';
        if (li.querySelector('a.detail_view[id]'))    return 'a.detail_view';
        if (li.querySelector('span[id]'))             return 'span';
        if (li.querySelector('a[id]'))                return 'a';
        return 'span.detail_view';
    }""")


def _extract_listing_cards(page: Page, click_sel: str, count: int) -> list[dict]:
    """Extract the top *count* result cards from the listing page."""
    return page.evaluate("""([sel, count]) => {
        var items = Array.from(document.querySelectorAll('li.result_content')).slice(0, count);
        return items.map(function(li) {
            var insurer = (li.querySelector('h3') || {}).innerText || '';
            var productEl = li.querySelector("p#sProdName, p[id='sProdName']");
            var product = (productEl || {}).innerText || '';
            var subInfo = '';
            if (productEl && productEl.nextElementSibling && productEl.nextElementSibling.tagName === 'P') {
                subInfo = productEl.nextElementSibling.innerText || '';
            }
            var clickEl = li.querySelector(sel + '[id]');
            var spanId  = (clickEl && clickEl.id) || li.id || '';
            // Best-effort annual premium from the card (may say "Perform search to view")
            var premEl = li.querySelector('.annual-premium, [class*="annual-premium"], [class*="annualPremium"]');
            var cardPremium = premEl ? (premEl.innerText || '').trim() : '';
            return {
                insurer:      insurer.trim(),
                product_name: product.trim(),
                sub_type:     product.trim(),
                sub_information: subInfo.trim(),
                span_id:      spanId,
                card_premium: cardPremium,
            };
        }).filter(function(e) { return e.span_id && (e.insurer || e.product_name); });
    }""", [click_sel, count])


def crawl_policies(
    product_type: str,
    dob: str,
    gender: str,
    smoker: str,
    ci: str = "N",
    sum_assured: Optional[int] = None,
    premium_amount: Optional[int] = None,
    coverage_term: Optional[int] = None,
    premium_term: Optional[int] = None,
    count: int = 10,
    headless: bool = True,
) -> list[dict]:
    """
    Crawl comparefirst.sg and return a list of policy dicts.

    Parameters
    ----------
    product_type   : "term" | "whole" | "endowment"
    dob            : Date of birth, "DD/MM/YYYY"
    gender         : "M" or "F"
    smoker         : "Y" or "N"
    ci             : Critical Illness Benefit, "Y" or "N" (default "N")
    sum_assured    : Sum assured in SGD — used for term and whole life
    premium_amount : Annual premium amount in SGD — used for endowment
    coverage_term  : Coverage term in years — used for term life and endowment
    premium_term   : Premium payment term in years — used for whole life
    count          : Number of policies to return (default 10)
    headless       : Run browser headlessly (default True)

    Returns
    -------
    List of dicts, each representing one policy's basic information.
    """
    if product_type not in FORM_CONFIG:
        raise ValueError(f"product_type must be 'term', 'whole', or 'endowment'; got {product_type!r}")

    cfg = FORM_CONFIG[product_type]
    listing_url = f"{BASE_URL}/productsListEvent.action?prodGroup={cfg['prod_group']}&pageAction=prodlisting"

    results: list[PolicyResult] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()

        try:
            # -----------------------------------------------------------------
            # 1. Navigate to listing page
            # -----------------------------------------------------------------
            print(f"[Fetching Policies] Loading {product_type} listing page…")
            page.goto(listing_url, wait_until="networkidle", timeout=30000)

            # -----------------------------------------------------------------
            # 2. Fill the search form
            # -----------------------------------------------------------------
            print("[Fetching Policies] Filling search form…")
            matched = _fill_form(
                page,
                product_type=product_type,
                dob=dob,
                gender=gender,
                smoker=smoker,
                ci=ci,
                sum_assured=sum_assured,
                premium_amount=premium_amount,
                coverage_term=coverage_term,
                premium_term=premium_term,
            )
            print(f"    matched: {matched}")

            # -----------------------------------------------------------------
            # 3. Submit the search form
            # -----------------------------------------------------------------
            print("[Fetching Policies] Submitting search…")
            page.evaluate("""() => {
                var btn = document.querySelector('#viewPopup');
                if (btn) btn.click();
            }""")

            # Wait for first result card — handles both navigation and in-page AJAX
            try:
                page.locator("li.result_content").first.wait_for(timeout=20000)
            except Exception:
                print("[!] No results appeared after search — check your inputs.", file=sys.stderr)
                return []

            results_url = page.url
            print(f"[*] Results page: …{results_url[-60:]}")

            # -----------------------------------------------------------------
            # 4. Load enough results
            # -----------------------------------------------------------------
            _load_all_results(page, max_items=count)
            total_shown = page.locator("li.result_content").count()
            print(f"[*] {total_shown} results loaded; collecting top {count}")

            # -----------------------------------------------------------------
            # 5. Extract listing card metadata
            # -----------------------------------------------------------------
            click_sel = _detect_click_selector(page)
            cards = _extract_listing_cards(page, click_sel, count)
            print(f"[*] {len(cards)} cards parsed; fetching details…")

            # -----------------------------------------------------------------
            # 6. For each card, navigate to detail page and extract info
            # -----------------------------------------------------------------
            for i, card in enumerate(cards):
                product_name = card["product_name"]
                sub_type     = card["sub_type"]
                sub_info     = card["sub_information"]
                insurer      = card["insurer"]
                span_id      = card["span_id"]
                print(f"  [{i+1}/{len(cards)}] {insurer} — {product_name} / {sub_type} / {sub_info}")

                policy = PolicyResult(
                    insurer=insurer,
                    product_name=product_name,
                    sub_type=sub_type,
                    sub_information=sub_info,
                    product_group=product_type,
                )

                # Try to click into the detail view
                clicked = False
                selectors_to_try = [
                    f'a.search_detail[id="{span_id}"]',
                    f'span.detail_view[id="{span_id}"]',
                    f'a[id="{span_id}"]',
                    f'span[id="{span_id}"]',
                ]
                for sel in selectors_to_try:
                    loc = page.locator(sel).first
                    if loc.count() > 0:
                        try:
                            loc.click(timeout=5000)
                            clicked = True
                            break
                        except Exception:
                            pass

                if not clicked:
                    # Fallback: find by product name text
                    fallback = page.locator(
                        f'li.result_content:has-text("{product_name.replace(chr(34), chr(39))}") '
                        f'a, li.result_content:has-text("{product_name.replace(chr(34), chr(39))}") span.detail_view'
                    ).first
                    if fallback.count() > 0:
                        try:
                            fallback.click(timeout=5000)
                            clicked = True
                        except Exception:
                            pass

                if not clicked:
                    print(f"    [!] Could not click into detail for {product_name}")
                    results.append(asdict(policy))
                    continue

                # Detect whether click caused URL navigation or an in-page popup
                navigated = False
                in_popup  = False
                _res_url = results_url  # avoid late-binding in lambda

                # Primary: wait for URL to change away from search results
                try:
                    page.wait_for_url(
                        lambda u: u != _res_url and "searchProducts" not in u,
                        timeout=10000,
                    )
                    navigated = True
                except Exception:
                    pass

                # Fallback: in-page popup (annual premium element becomes visible)
                if not navigated:
                    try:
                        page.locator(".tab-area-content1.annual-premium").wait_for(
                            state="visible", timeout=5000
                        )
                        in_popup = True
                    except Exception:
                        pass

                if navigated:
                    # Wait for detail page to fully render
                    try:
                        page.wait_for_selector("text=Last Updated", timeout=15000)
                    except Exception:
                        pass
                    # Poll until annual premium is populated (AJAX loads data async)
                    _wait_for_premium_content(page, timeout_ms=12000)

                # Extract info
                detail     = _extract_detail(page, product_type)
                doc_links  = _extract_doc_links(page)

                policy.annual_premium    = detail.get("annual_premium", "N/A")
                policy.coverage_term     = detail.get("coverage_term", "N/A")
                policy.premium_term      = detail.get("premium_term", "N/A")
                policy.total_premium     = detail.get("total_premium", "N/A")
                policy.distribution_cost = detail.get("distribution_cost", "N/A")
                policy.credit_rating     = detail.get("credit_rating", "N/A")
                policy.guaranteed_maturity_benefit = detail.get("guaranteed_maturity_benefit", "N/A")
                policy.product_summary_url = doc_links.get("product_summary_url", "")
                policy.brochure_url        = doc_links.get("brochure_url", "")

                results.append(asdict(policy))

                # Return to results page
                if navigated:
                    page.go_back(wait_until="domcontentloaded", timeout=20000)
                    # Wait for result cards to reappear (loaded async via JS)
                    try:
                        page.locator("li.result_content").first.wait_for(timeout=12000)
                    except Exception:
                        pass
                    # Re-expand so all required cards are visible
                    _load_all_results(page, max_items=count)
                elif in_popup:
                    # Close popup if there's a close button, or just proceed
                    try:
                        page.locator(
                            "button.close, .modal-close, [data-dismiss='modal'], a.close-popup"
                        ).first.click(timeout=2000)
                    except Exception:
                        pass

        finally:
            browser.close()

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Crawl comparefirst.sg for insurance policy data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--type",   dest="product_type", required=True, choices=["term", "whole", "endowment"])
    p.add_argument("--dob",    required=True, help="Date of birth DD/MM/YYYY")
    p.add_argument("--gender", required=True, choices=["M", "F"])
    p.add_argument("--smoker", required=True, choices=["Y", "N"])
    p.add_argument("--ci",     default="N",  choices=["Y", "N"], help="Critical Illness Benefit (default N)")
    p.add_argument("--count",  type=int, default=10, help="Number of policies to retrieve (default 10)")
    p.add_argument("--out",    default=None, help="Output JSON file (default: stdout)")
    p.add_argument("--show",   action="store_true", help="Show browser window (non-headless)")

    # Term / Whole life
    p.add_argument("--sum_assured", type=int, default=None,
                   help="Sum assured in SGD (term & whole life)")
    # Coverage term — term life (and endowment)
    p.add_argument("--coverage_term", type=int, default=None,
                   help="Coverage term in years (term life, endowment)")
    # Premium term — whole life only
    p.add_argument("--premium_term", type=int, default=None,
                   help="Premium payment term in years (whole life)")
    # Endowment
    p.add_argument("--premium_amount", type=int, default=None,
                   help="Annual premium amount in SGD (endowment)")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    policies = crawl_policies(
        product_type=args.product_type,
        dob=args.dob,
        gender=args.gender,
        smoker=args.smoker,
        ci=args.ci,
        sum_assured=args.sum_assured,
        premium_amount=args.premium_amount,
        coverage_term=args.coverage_term,
        premium_term=args.premium_term,
        count=args.count,
        headless=not args.show,
    )

    output = json.dumps(policies, indent=2, ensure_ascii=False)

    json_file = f"./data/policies/{args.product_type}_{args.sum_assured}_{args.coverage_term}_{args.premium_term}_{args.premium_amount}_{args.ci}_{args.gender}_{args.smoker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    import os
    out_dir = os.path.dirname(json_file)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(json_file, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"\n[*] Saved {len(policies)} policies to {json_file}")


if __name__ == "__main__":
    main()
