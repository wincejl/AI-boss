import argparse
import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from DrissionPage import ChromiumOptions, ChromiumPage
    from jsonpath import jsonpath
except ImportError as exc:
    raise SystemExit(
        "Missing dependency. Install with: pip install DrissionPage jsonpath"
    ) from exc


def build_browser_options() -> ChromiumOptions:
    options = ChromiumOptions()
    options.set_argument("--start-maximized")
    return options


def wait_for_login(page: ChromiumPage, skip_login: bool) -> None:
    if skip_login:
        return
    page.get("https://www.zhipin.com/web/user/?ka=header-login")
    input("Log in to BOSS in the opened browser, then press Enter here...")


def trigger_search(page: ChromiumPage) -> None:
    page.run_js(
        """
        (function(){
            var input = document.querySelector('input[name="query"]') ||
                        document.querySelector('.ipt-search') ||
                        document.querySelector('input[placeholder*="search"], input[placeholder*="搜索"]') ||
                        document.querySelector('input[type="text"]');
            var btn = document.querySelector('.search-btn') ||
                      document.querySelector('.btn-search') ||
                      document.querySelector('button[type="submit"]') ||
                      document.querySelector('.search-form button') ||
                      document.querySelector('.icon-search') ||
                      document.querySelector('[class*="search"]');
            if (btn) { btn.click(); return; }
            if (input) {
                input.dispatchEvent(new KeyboardEvent('keydown', {
                    key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
                }));
            }
        })();
        """
    )


def parse_job_response(resp_body) -> list[list[str]]:
    job_list = (
        jsonpath(resp_body, "$..jobList")
        or jsonpath(resp_body, "$..joblist")
        or jsonpath(resp_body, "$.zpData.jobList")
    )
    if not job_list:
        return []

    job_names = jsonpath(job_list, "$..jobName")
    if not job_names:
        return []

    salary_desc = jsonpath(job_list, "$..salaryDesc") or []
    job_degrees = jsonpath(job_list, "$..jobDegree") or []
    job_experiences = jsonpath(job_list, "$..jobExperience") or []
    intern_days = jsonpath(job_list, "$..daysPerWeekDesc") or []
    intern_months = jsonpath(job_list, "$..leastMonthDesc") or []
    brand_names = jsonpath(job_list, "$..brandName") or []
    city_names = jsonpath(job_list, "$..cityName") or jsonpath(job_list, "$..cityname") or []
    districts = jsonpath(job_list, "$..areaDistrict") or []
    business_districts = jsonpath(job_list, "$..businessDistrict") or []
    encrypt_ids = jsonpath(job_list, "$..encryptJobId") or jsonpath(job_list, "$..jobId") or []

    rows = []
    for index, job_name in enumerate(job_names):
        requirement = "No explicit requirement"
        if index < len(job_experiences) and job_experiences[index]:
            requirement = f"Full-time, {job_experiences[index]}"
        elif (
            index < len(intern_days)
            and index < len(intern_months)
            and intern_days[index]
            and intern_months[index]
        ):
            requirement = f"Internship, {intern_days[index]}, {intern_months[index]}"

        city = city_names[index] if index < len(city_names) else ""
        district = districts[index] if index < len(districts) else ""
        business = business_districts[index] if index < len(business_districts) else ""
        rows.append(
            [
                job_name or "",
                salary_desc[index] if index < len(salary_desc) else "",
                job_degrees[index] if index < len(job_degrees) else "",
                requirement,
                brand_names[index] if index < len(brand_names) else "",
                "-".join(part for part in [city, district, business] if part),
                encrypt_ids[index] if index < len(encrypt_ids) else "",
            ]
        )
    return rows


def fetch_description(page: ChromiumPage, job_id: str, index: int) -> tuple[int, str]:
    tab = None
    try:
        tab = page.new_tab(f"https://www.zhipin.com/job_detail/{job_id}.html")
        tab.wait.ele_displayed("css:.job-sec-text", timeout=2.5)
        desc_ele = tab.ele("css:.job-sec-text", timeout=0.5) or tab.ele("css:.job-detail", timeout=0.5)
        return index, desc_ele.text.replace("\n", " ").strip() if desc_ele else ""
    except Exception:
        return index, ""
    finally:
        if tab:
            try:
                tab.close()
            except Exception:
                pass


def collect_jobs(city: str, pages: int, workers: int, skip_login: bool) -> list[list[str]]:
    page = ChromiumPage(build_browser_options())
    wait_for_login(page, skip_login)

    page.get(f"https://www.zhipin.com/web/geek/job?city={city}")
    time.sleep(1)
    trigger_search(page)
    try:
        page.wait.ele_displayed("css=.search-condition", timeout=3)
    except Exception:
        pass

    input("Set filters in the browser, then press Enter here to start export...")
    page.listen.start("joblist")
    trigger_search(page)

    first_response = None
    for data in page.listen.steps(timeout=8):
        resp_body = data.response.body
        code = jsonpath(resp_body, "$.code")
        if code and code[0] == 0 and (jsonpath(resp_body, "$..jobList") or jsonpath(resp_body, "$..joblist")):
            first_response = data
            break
    if first_response is None:
        print("No job list response captured.")
        return []

    jobs = parse_job_response(first_response.response.body)
    print(f"Page 1 done, total {len(jobs)} rows.")

    collected_pages = 1
    while collected_pages < pages:
        page.run_js("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        got_page = False
        try:
            for data in page.listen.steps(timeout=4):
                resp_body = data.response.body
                code = jsonpath(resp_body, "$.code")
                if not code or code[0] != 0:
                    continue
                page_jobs = parse_job_response(resp_body)
                if page_jobs:
                    jobs.extend(page_jobs)
                    collected_pages += 1
                    got_page = True
                    print(f"Page {collected_pages} done, total {len(jobs)} rows.")
                    break
        except Exception:
            pass
        if not got_page:
            print("No more pages captured.")
            break

    print(f"Collected {len(jobs)} list rows. Fetching descriptions...")
    results: list[list[str] | None] = [None] * len(jobs)
    # ponytail: shares one browser across tabs; lower --workers if BOSS tabs become unstable.
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(fetch_description, page, row[-1], index): index
            for index, row in enumerate(jobs)
            if row[-1]
        }
        for index, row in enumerate(jobs):
            if not row[-1]:
                results[index] = row[:6] + [""]
        for future in as_completed(futures):
            index, desc = future.result()
            results[index] = jobs[index][:6] + [desc]
    return [row for row in results if row is not None]


def save_csv(rows: list[list[str]], output: str) -> None:
    if not rows:
        print("No data to save.")
        return
    with open(output, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["job_name", "salary", "degree", "work_requirement", "company", "address", "description"])
        writer.writerows(rows)
    print(f"Saved {len(rows)} rows to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export BOSS job search results to CSV.")
    parser.add_argument("--pages", type=int, help="Number of result pages to collect.")
    parser.add_argument("--city", default="101200100", help="BOSS city code. Default: Wuhan.")
    parser.add_argument("--output", default="boss_jobs_fast.csv", help="Output CSV path.")
    parser.add_argument("--workers", type=int, default=6, help="Parallel detail tabs.")
    parser.add_argument("--skip-login", action="store_true", help="Skip login prompt when browser is already logged in.")
    args = parser.parse_args()

    pages = args.pages or int(input("Pages to collect: "))
    save_csv(collect_jobs(args.city, pages, args.workers, args.skip_login), args.output)


if __name__ == "__main__":
    main()
