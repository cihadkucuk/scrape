import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def load_config(config_path: Path) -> dict:
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise SystemExit(f"Config dosyasi bulunamadi: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Config JSON hatali: {exc}") from exc


def require(config: dict, path: str) -> str:
    current = config
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current or current[part] in ("", None):
            raise SystemExit(f"Eksik config alani: {path}")
        current = current[part]
    if not isinstance(current, str):
        raise SystemExit(f"Config alani string olmali: {path}")
    return current


def maybe_click(page, selector: str | None, timeout_ms: int) -> None:
    if not selector:
        return
    locator = page.locator(selector)
    if locator.count() > 0:
        locator.first.click(timeout=timeout_ms)


def login(page, config: dict, timeout_ms: int) -> None:
    login_cfg = config.get("login", {})
    page.goto(require(config, "url"), wait_until="domcontentloaded", timeout=timeout_ms)

    maybe_click(page, login_cfg.get("pre_login_click_selector"), timeout_ms)

    page.locator(require(config, "selectors.login_username")).fill(
        require(config, "login.username"), timeout=timeout_ms
    )
    page.locator(require(config, "selectors.login_password")).fill(
        require(config, "login.password"), timeout=timeout_ms
    )
    page.locator(require(config, "selectors.login_submit")).click(timeout=timeout_ms)

    wait_after_login = login_cfg.get("wait_for_selector_after_login")
    if wait_after_login:
        page.wait_for_selector(wait_after_login, timeout=timeout_ms)
    else:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)


def fill_home_form(page, config: dict, timeout_ms: int) -> None:
    target_value = require(config, "target.value")
    username_selector = require(config, "selectors.home_username")
    apply_selector = require(config, "selectors.apply_button")

    page.locator(username_selector).fill(target_value, timeout=timeout_ms)
    page.locator(apply_selector).click(timeout=timeout_ms)

    success_selector = config.get("selectors", {}).get("success_after_apply")
    if success_selector:
        page.wait_for_selector(success_selector, timeout=timeout_ms)


def run(config_path: Path, headed: bool) -> None:
    config = load_config(config_path)
    timeout_ms = int(config.get("timeout_ms", 30000))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed, slow_mo=config.get("slow_mo_ms", 0))
        page = browser.new_page()

        try:
            login(page, config, timeout_ms)
            fill_home_form(page, config, timeout_ms)
            print("Islem tamamlandi.")
        except PlaywrightTimeoutError as exc:
            raise SystemExit(f"Zaman asimi: {exc}") from exc
        finally:
            if config.get("keep_browser_open"):
                input("Tarayiciyi kapatmak icin Enter'a basin...")
            browser.close()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Login olup anasayfada username alanina deger yazip apply butonuna basar."
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="JSON config dosya yolu. Varsayilan: config.json",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Tarayiciyi gorunur modda acar.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    run(Path(args.config), headed=args.headed)
