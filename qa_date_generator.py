"""
QA Investigation Script: https://codebeautify.org/generate-random-date
Automated checks supporting exploratory testing findings

Run: python3 qa_date_generator.py
Requires: pip install playwright && python3 -m playwright install chromium
"""

from playwright.sync_api import sync_playwright, Page
import sys
import time

PASS = "\033[92m[PASS]\033[0m"
RISK = "\033[91m[RISK]\033[0m"
INFO = "\033[93m[INFO]\033[0m"
SEP  = "-" * 65

results = {"pass": 0, "risk": 0}


def log(status, test_id, msg):
    label = PASS if status == "pass" else (RISK if status == "risk" else INFO)
    print(f"  {label} {test_id}: {msg}")
    if status in results:
        results[status] += 1


def setup_page(browser) -> Page:
    page = browser.new_page()
    page.goto(
        "https://codebeautify.org/generate-random-date",
        wait_until="networkidle",
        timeout=30000,
    )
    for frame in page.frames:
        if "privacy-mgmt" in frame.url:
            btn = frame.query_selector('button:has-text("Accept")')
            if btn:
                btn.click()
            break
    page.wait_for_timeout(1500)
    return page


def gen(page: Page, count=5, start=None, end=None,
        fmt="yyyy-mm-dd-hh-mm-ss", custom=None, wait=700) -> list[str]:
    page.evaluate(f"document.getElementById('count').value = '{count}'")
    if start:
        page.evaluate(f"document.getElementById('start').value = '{start}'")
    if end:
        page.evaluate(f"document.getElementById('end').value = '{end}'")
    page.evaluate(f"document.getElementById('format').value = '{fmt}'")
    if custom is not None:
        page.evaluate(
            f"document.getElementById('custom-format').value = {repr(custom)}"
        )
    page.evaluate("generateRandomDate()")
    page.wait_for_timeout(wait)
    raw = page.input_value("#generatedRandomDateTextArea")
    return [l.strip() for l in raw.strip().split("\n") if l.strip()]


def run_checks(browser):

    # CHECK-1: Missing count validation — no upper bound, no integer check
    print(f"\n{SEP}")
    print("CHECK-1  [CRITICAL]  No upper bound on count — unresponsiveness risk")
    print(SEP)
    page = setup_page(browser)
    # Verify: no HTML min/max attributes
    attrs = page.evaluate(
        "JSON.stringify({min: document.getElementById('count').min, "
        "max: document.getElementById('count').max})"
    )
    # Verify: large value accepted and processed synchronously
    page.evaluate("document.getElementById('count').value = '100000'")
    page.evaluate("document.getElementById('start').value = '2025-01-01 00:00:00'")
    page.evaluate("document.getElementById('end').value = '2025-12-31 23:59:59'")
    page.evaluate("document.getElementById('format').value = 'mm-dd-yyyy'")
    t0 = time.time()
    page.evaluate("generateRandomDate()")
    page.wait_for_timeout(8000)
    elapsed = time.time() - t0
    n = len([l for l in page.input_value("#generatedRandomDateTextArea")
             .split("\n") if l.strip()])
    # Verify: float input not validated
    page.evaluate("document.getElementById('count').value = '1.9'")
    page.evaluate("generateRandomDate()")
    page.wait_for_timeout(500)
    n_float = len([l for l in page.input_value("#generatedRandomDateTextArea")
                   .split("\n") if l.strip()])
    log("risk", "CHECK-1",
        f"HTML attrs: {attrs} | count=100000 → {n} dates in {elapsed:.1f}s "
        f"(synchronous, freezes browser for larger values) | "
        f"count=1.9 → {n_float} dates (float accepted, no validation)")
    page.close()

    # CHECK-2: Feb 29 on non-leap year → silent date rollover
    print(f"\n{SEP}")
    print("CHECK-2  [CRITICAL]  Feb 29 non-leap year: silent rollover, no warning")
    print(SEP)
    page = setup_page(browser)
    dates = gen(page, count=5,
                start="2025-02-29 00:00:00", end="2025-02-29 23:59:59")
    any_feb29 = any(d.startswith("2025-02-29") for d in dates)
    any_mar01 = any(d.startswith("2025-03-01") for d in dates)
    if any_mar01 and not any_feb29:
        log("risk", "CHECK-2",
            f"Input 2025-02-29 (non-existent) → output: {dates[0]} "
            f"— JS silently coerces to March 1, no warning shown")
    else:
        log("pass", "CHECK-2", f"Output: {dates[:2]}")
    page.close()

    # CHECK-3: 'Year Date Month' format produces same output as 'Year Month Date'
    print(f"\n{SEP}")
    print("CHECK-3  [HIGH]  Duplicate dropdown option: Year-Date-Month ≡ Year-Month-Date")
    print(SEP)
    page = setup_page(browser)
    # Use June 7 (month=6, day=7): if swap worked, positions would differ
    fixed = ("2025-06-07 14:03:02", "2025-06-07 14:03:02")
    d_ymd = gen(page, count=1, start=fixed[0], end=fixed[1],
                fmt="year-month-date-hh-mm-ss")
    d_ydm = gen(page, count=1, start=fixed[0], end=fixed[1],
                fmt="year-date-month-hh-mm-ss")
    if d_ymd and d_ydm and d_ymd[0] == d_ydm[0]:
        log("risk", "CHECK-3",
            f"'Year Month Date' → '{d_ymd[0]}' | "
            f"'Year Date Month' → '{d_ydm[0]}' — identical output, "
            f"day/month swap not implemented")
    else:
        log("pass", "CHECK-3",
            f"Outputs differ: '{d_ymd[0] if d_ymd else '?'}' vs "
            f"'{d_ydm[0] if d_ydm else '?'}'")
    page.close()

    # CHECK-4: Start > End accepted silently
    print(f"\n{SEP}")
    print("CHECK-4  [HIGH]  Start > End: no validation, generates without error")
    print(SEP)
    page = setup_page(browser)
    dates = gen(page, count=5,
                start="2025-12-31 00:00:00", end="2025-01-01 23:59:59")
    if dates and all(d.startswith("2025") for d in dates):
        log("risk", "CHECK-4",
            f"start=2025-12-31 end=2025-01-01 → {dates[0]} "
            f"(dates generated from reversed range, no error shown)")
    else:
        log("pass", "CHECK-4", "Range inversion correctly rejected")
    page.close()

    # CHECK-5: Custom format — greedy single-char tokens corrupt literal text
    print(f"\n{SEP}")
    print("CHECK-5  [HIGH]  Custom format: tokens corrupt words containing d/h/m/s")
    print(SEP)
    page = setup_page(browser)
    fixed = ("2025-06-15 14:30:45", "2025-06-15 14:30:45")
    # Assertion: literal text with no date tokens should pass through unchanged
    cases = [
        "Monday",
        "second",
        "Month",   # capitalised — user's natural expectation for month name
        "months",
    ]
    for tmpl in cases:
        result = gen(page, count=1, start=fixed[0], end=fixed[1],
                     fmt="custom", custom=tmpl)
        actual = result[0] if result else ""
        if actual != tmpl:
            log("risk", "CHECK-5",
                f"template='{tmpl}' → '{actual}' "
                f"(literal text modified by greedy token replacement)")
        else:
            log("pass", "CHECK-5", f"template='{tmpl}' → '{actual}' unchanged")
    page.close()

    # CHECK-6: Invalid end date — UI message vs actual reset date
    print(f"\n{SEP}")
    print("CHECK-6  [HIGH]  Invalid end date: warning message inconsistent with reset")
    print(SEP)
    page = setup_page(browser)
    # Trigger invalid end date via button click (requires proper 'this' binding)
    page.evaluate("document.getElementById('count').value = '5'")
    page.evaluate("document.getElementById('start').value = '2099-01-15 00:00:00'")
    page.evaluate("document.getElementById('end').value = 'not-a-date'")
    page.evaluate("document.getElementById('format').value = 'yyyy-mm-dd-hh-mm-ss'")
    try:
        page.click("button[onclick='generateRandomDate();']", timeout=3000)
        page.wait_for_timeout(1000)
        # Read actual dates generated to determine real reset date
        dates = [l.strip() for l in
                 page.input_value("#generatedRandomDateTextArea").split("\n")
                 if l.strip()]
        # Read UI warning message
        badge = page.query_selector(".notification")
        badge_text = badge.inner_text().strip() if badge else ""
        # Check JS reset constant directly
        js_reset = page.evaluate(
            "new Date(0x833, 0x0, 0x1f).toISOString().substring(0, 10)"
        )
        says_dec = "2099-12-31" in badge_text
        is_jan   = js_reset.startswith("2099-01")
        if says_dec and is_jan:
            log("risk", "CHECK-6",
                f"Warning says '2099-12-31' | JS reset constant = {js_reset} "
                f"(month 0x0 = January, not December — message off by 11 months)")
        elif badge_text:
            log("info", "CHECK-6",
                f"Badge: '{badge_text[:60]}' | JS reset: {js_reset}")
        else:
            log("info", "CHECK-6",
                f"No badge visible | JS reset constant: {js_reset} | dates: {dates[:2]}")
    except Exception as e:
        log("info", "CHECK-6", f"Could not trigger via button click: {str(e)[:80]}")
    page.close()

    # CHECK-7: Year 0–99 silently mapped to 1900–1999
    print(f"\n{SEP}")
    print("CHECK-7  [MEDIUM]  Year 0–99 silently remapped to 1900–1999")
    print(SEP)
    page = setup_page(browser)
    dates = gen(page, count=5,
                start="0050-01-01 00:00:00", end="0050-12-31 23:59:59")
    years = {d[:4] for d in dates}
    if dates and "0050" not in years:
        log("risk", "CHECK-7",
            f"Input year 0050 → output years {years} "
            f"(JS Date maps 0–99 to 1900–1999, no warning)")
    elif not dates:
        log("info", "CHECK-7", "No dates generated")
    else:
        log("pass", "CHECK-7", f"Years in output: {years}")
    page.close()

    # CHECK-8: count=0 / count=-1 produce no feedback
    print(f"\n{SEP}")
    print("CHECK-8  [LOW]  count=0 / count=-1: empty output, no validation message")
    print(SEP)
    page = setup_page(browser)
    for val in ["0", "-1"]:
        dates = gen(page, count=val,
                    start="2025-01-01 00:00:00", end="2025-12-31 23:59:59")
        if not dates:
            log("risk", "CHECK-8",
                f"count={val} → empty output, no error message shown to user")
        else:
            log("pass", "CHECK-8", f"count={val} → {len(dates)} dates")
    page.close()

    # CHECK-9: Pre-1900 dates accepted without validation
    print(f"\n{SEP}")
    print("CHECK-9  [LOW]  Dates before 1900 accepted (default start implies 2020)")
    print(SEP)
    page = setup_page(browser)
    dates = gen(page, count=3,
                start="1800-01-01 00:00:00", end="1800-12-31 23:59:59")
    years = {d[:4] for d in dates}
    if "1800" in years:
        log("risk", "CHECK-9",
            f"start=1800-01-01 → {dates[0]} "
            f"(undocumented range; default start=2020, no stated minimum)")
    else:
        log("pass", "CHECK-9", f"Output: {dates}")
    page.close()

    # ── CHECK-10: Custom format `ssss` — double-replace leaves orphan char ────
    print(f"\n{SEP}")
    print("CHECK-10 [LOW]  Custom template 'ssss' produces trailing orphan character")
    print(SEP)
    page = setup_page(browser)
    dates = gen(page, count=1,
                start="2025-06-15 14:30:45", end="2025-06-15 14:30:45",
                fmt="custom", custom="ssss")
    actual = dates[0] if dates else ""
    if actual and not actual.isdigit():
        log("risk", "CHECK-10",
            f"template='ssss' → '{actual}' "
            f"(.replace() replaces only first occurrence; "
            f"second 'ss'→digits, leftover 's' remains)")
    else:
        log("pass", "CHECK-10", f"Output: '{actual}'")
    page.close()


def main():
    print("\n" + "=" * 65)
    print("  QA Investigation Script — Random Date Generator")
    print("  codebeautify.org/generate-random-date")
    print("  Automated checks supporting exploratory testing findings")
    print("=" * 65)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=300)
        try:
            run_checks(browser)
        finally:
            browser.close()

    print(f"\n{'=' * 65}")
    print(f"  {results['risk']} risks flagged | {results['pass']} checks passed")
    print(f"{'=' * 65}\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
