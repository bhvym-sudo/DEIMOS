import argparse
import asyncio
import json
import sys
from urllib.parse import quote

from playwright.async_api import async_playwright

from search_timeline import load_session_cookies


async def lookup(profile_dir: str, username: str, runtime_path: str = None):
    captured_profiles = []
    captured_timelines = []
    navigation_errors = []
    async with async_playwright() as playwright:
        browser = None
        if runtime_path:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1280, "height": 800}, locale="en-US")
            await context.add_cookies(load_session_cookies(runtime_path))
        else:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=profile_dir, channel="msedge", headless=True,
                viewport={"width": 1280, "height": 800}, locale="en-US",
                args=["--headless=new", "--disable-gpu", "--disable-extensions", "--disable-notifications", "--no-first-run", "--no-default-browser-check"],
            )
        page = context.pages[0] if context.pages else await context.new_page()

        async def inspect(response):
            if "/graphql/" not in response.url or response.status != 200:
                return
            try:
                payload = await response.json()
                if "UserByScreenName" in response.url:
                    captured_profiles.append(payload)
                elif "SearchTimeline" in response.url:
                    captured_timelines.append(payload)
            except Exception:
                pass

        page.on("response", inspect)
        try:
            await page.goto(f"https://x.com/{username}", wait_until="commit", timeout=60000)
        except Exception as error:
            navigation_errors.append(str(error))
        for _ in range(12):
            if captured_profiles:
                break
            await page.wait_for_timeout(500)

        if not captured_profiles:
            query = quote(f"from:{username}")
            try:
                await page.goto(
                    f"https://x.com/search?q={query}&src=typed_query&f=live",
                    wait_until="commit",
                    timeout=60000,
                )
            except Exception as error:
                navigation_errors.append(str(error))
            for _ in range(20):
                if captured_timelines:
                    break
                await page.wait_for_timeout(500)
        await context.close()
        if browser:
            await browser.close()

    if captured_profiles:
        return captured_profiles[-1]
    for payload in reversed(captured_timelines):
        user = find_user(payload, username)
        if user:
            return {"data": {"user": {"result": user}}}
    detail = navigation_errors[-1] if navigation_errors else "no matching GraphQL response"
    raise RuntimeError(f"authenticated browser did not return profile data: {detail}")


def find_user(value, username):
    if isinstance(value, dict):
        legacy = value.get("legacy")
        core = value.get("core")
        handles = []
        if isinstance(legacy, dict):
            handles.append(legacy.get("screen_name"))
        if isinstance(core, dict):
            handles.append(core.get("screen_name"))
        if value.get("rest_id") and any(
            str(handle or "").lower() == username.lower() for handle in handles
        ):
            return value
        for child in value.values():
            found = find_user(child, username)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_user(child, username)
            if found:
                return found
    return None


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile")
    parser.add_argument("--runtime")
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    username = args.username.strip().lstrip("@").split("/")[0]
    try:
        if not args.profile and not args.runtime:
            raise RuntimeError("either --profile or --runtime is required")
        profile = await lookup(args.profile, username, args.runtime)
        sys.stdout.write(json.dumps({"profile": profile}, separators=(",", ":")))
    except Exception as error:
        sys.stderr.write(str(error))
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
