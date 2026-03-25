import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


FIELD_QUERY = (
    "input, textarea, button, select, [role='button'], "
    "input[type='submit'], input[type='button']"
)

DISCOVERY_SCRIPT = """
element => {
  const clean = value => (value || '').replace(/\\s+/g, ' ').trim();
  const textFromNode = node => {
    if (!node) return '';
    return clean(node.innerText || node.textContent || '');
  };
  const labels = [];
  if (element.labels) {
    for (const label of element.labels) {
      const text = textFromNode(label);
      if (text) labels.push(text);
    }
  }
  if (element.id) {
    const explicitLabel = document.querySelector(`label[for="${element.id}"]`);
    const text = textFromNode(explicitLabel);
    if (text) labels.push(text);
  }

  const previousText = [];
  let sibling = element.previousElementSibling;
  let steps = 0;
  while (sibling && steps < 3) {
    const text = textFromNode(sibling);
    if (text) previousText.push(text);
    sibling = sibling.previousElementSibling;
    steps += 1;
  }

  const parentText = [];
  let parent = element.parentElement;
  steps = 0;
  while (parent && steps < 3) {
    const text = textFromNode(parent);
    if (text) parentText.push(text.slice(0, 300));
    parent = parent.parentElement;
    steps += 1;
  }

  const rect = element.getBoundingClientRect();
  const style = window.getComputedStyle(element);
  const inputType = clean(element.getAttribute('type'));
  const role = clean(element.getAttribute('role'));
  const text = clean(
    element.innerText || element.textContent || element.value || element.getAttribute('value')
  );

  return {
    tag: (element.tagName || '').toLowerCase(),
    type: inputType,
    role,
    name: clean(element.getAttribute('name')),
    id: clean(element.id),
    className: clean(element.className),
    placeholder: clean(element.getAttribute('placeholder')),
    ariaLabel: clean(element.getAttribute('aria-label')),
    title: clean(element.getAttribute('title')),
    autocomplete: clean(element.getAttribute('autocomplete')),
    value: clean(element.value),
    text,
    labels,
    previousText,
    parentText,
    visible: !!(
      rect.width > 0 &&
      rect.height > 0 &&
      style.visibility !== 'hidden' &&
      style.display !== 'none'
    ),
    disabled: !!(element.disabled || element.getAttribute('aria-disabled') === 'true'),
    rect: {
      x: rect.x,
      y: rect.y,
      width: rect.width,
      height: rect.height
    },
    outerHtmlSnippet: clean((element.outerHTML || '').slice(0, 500))
  };
}
"""


USERNAME_HINTS = [
    "username",
    "user name",
    "user",
    "member",
    "member id",
    "member number",
    "account",
    "account id",
    "account number",
    "customer",
    "customer id",
    "customer number",
    "subscriber",
    "subscriber id",
    "subscriber number",
    "policy",
    "policy number",
    "reference",
    "reference number",
    "application",
    "application number",
    "claim",
    "claim number",
    "number",
    "no.",
    "id no",
    "id number",
]

PASSWORD_HINTS = [
    "password",
    "passcode",
    "pin",
    "pwd",
]

LOGIN_BUTTON_HINTS = [
    "login",
    "log in",
    "sign in",
    "continue",
    "submit",
    "next",
]

APPLY_BUTTON_HINTS = [
    "apply",
    "search",
    "filter",
    "go",
    "submit",
    "continue",
    "save",
    "confirm",
]


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


def optional(config: dict, path: str) -> str | None:
    current = config
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    if current in ("", None):
        return None
    if not isinstance(current, str):
        raise SystemExit(f"Config alani string olmali: {path}")
    return current


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def text_matches(value: str, hints: list[str]) -> bool:
    return any(hint in value for hint in hints)


def maybe_click(page, selector: str | None, timeout_ms: int) -> None:
    if not selector:
        return
    locator = page.locator(selector)
    if locator.count() > 0:
        locator.first.click(timeout=timeout_ms)


def collect_candidates(page) -> list[dict]:
    candidates: list[dict] = []
    for frame in page.frames:
        try:
            handles = frame.query_selector_all(FIELD_QUERY)
        except Exception:
            continue

        for index, handle in enumerate(handles):
            try:
                meta = handle.evaluate(DISCOVERY_SCRIPT)
            except Exception:
                continue
            meta["frame_name"] = frame.name or ""
            meta["frame_url"] = frame.url
            meta["candidate_index"] = index
            meta["handle"] = handle
            candidates.append(meta)
    return candidates


def candidate_text_blob(candidate: dict) -> str:
    parts = [
        candidate.get("tag"),
        candidate.get("type"),
        candidate.get("role"),
        candidate.get("name"),
        candidate.get("id"),
        candidate.get("className"),
        candidate.get("placeholder"),
        candidate.get("ariaLabel"),
        candidate.get("title"),
        candidate.get("autocomplete"),
        candidate.get("text"),
        candidate.get("value"),
    ]
    parts.extend(candidate.get("labels", []))
    parts.extend(candidate.get("previousText", []))
    parts.extend(candidate.get("parentText", []))
    return normalize_text(" ".join(part for part in parts if part))


def score_candidate(candidate: dict, action: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    blob = candidate_text_blob(candidate)
    tag = candidate.get("tag", "")
    input_type = candidate.get("type", "")
    visible = bool(candidate.get("visible"))
    disabled = bool(candidate.get("disabled"))
    rect = candidate.get("rect", {})
    area = float(rect.get("width", 0)) * float(rect.get("height", 0))

    if visible:
        score += 30
        reasons.append("visible")
    else:
        score -= 120
        reasons.append("hidden")

    if disabled:
        score -= 80
        reasons.append("disabled")

    if area > 400:
        score += 10
        reasons.append("usable-size")

    if action in {"login_username", "home_username"}:
        if tag not in {"input", "textarea"}:
            score -= 120
            reasons.append("not-editable")
        if input_type in {"hidden", "submit", "button", "checkbox", "radio", "file"}:
            score -= 120
            reasons.append("wrong-input-type")
        if input_type in {"text", "search", ""}:
            score += 20
            reasons.append("text-like-input")
        if text_matches(blob, USERNAME_HINTS):
            score += 80
            reasons.append("username-hint")
        if any(token in blob for token in ["email", "e-mail", "mail"]):
            score -= 20
            reasons.append("email-leaning")
        if action == "login_username" and any(
            token in blob for token in ["email", "e-mail", "mail", "login", "sign in"]
        ):
            score += 30
            reasons.append("login-user-hint")
        if action == "home_username" and any(
            token in blob for token in ["search", "lookup", "find", "track", "check"]
        ):
            score += 20
            reasons.append("lookup-context")

    if action == "login_password":
        if tag != "input":
            score -= 120
            reasons.append("not-password-input")
        if input_type == "password":
            score += 140
            reasons.append("password-type")
        if text_matches(blob, PASSWORD_HINTS):
            score += 80
            reasons.append("password-hint")

    if action in {"login_submit", "apply_button"}:
        if tag not in {"button", "input"} and candidate.get("role") != "button":
            score -= 120
            reasons.append("not-button")
        if action == "login_submit" and text_matches(blob, LOGIN_BUTTON_HINTS):
            score += 100
            reasons.append("login-button-hint")
        if action == "apply_button" and text_matches(blob, APPLY_BUTTON_HINTS):
            score += 100
            reasons.append("apply-button-hint")
        if input_type in {"submit", "button"}:
            score += 30
            reasons.append("button-input-type")

    return score, reasons


def safe_candidate_dump(candidate: dict) -> dict:
    return {
        key: value
        for key, value in candidate.items()
        if key != "handle"
    }


def choose_candidate(page, action: str, dump_path: Path | None) -> dict:
    candidates = collect_candidates(page)
    scored: list[dict] = []
    for candidate in candidates:
        score, reasons = score_candidate(candidate, action)
        candidate["score"] = score
        candidate["score_reasons"] = reasons
        scored.append(candidate)

    scored.sort(key=lambda item: item["score"], reverse=True)
    top_candidates = [safe_candidate_dump(item) for item in scored[:15]]
    if dump_path:
        dump_payload = {
            "action": action,
            "page_url": page.url,
            "top_candidates": top_candidates,
        }
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        dump_path.write_text(
            json.dumps(dump_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    if not scored or scored[0]["score"] < 20:
        raise SystemExit(
            f"Discovery uygun eleman bulamadi: {action}. "
            f"Debug dump: {dump_path}" if dump_path else f"Discovery uygun eleman bulamadi: {action}"
        )
    return scored[0]


def resolve_element(page, selector: str | None, action: str, dump_path: Path | None):
    if selector:
        locator = page.locator(selector)
        if locator.count() > 0:
            handle = locator.first.element_handle()
            if handle is not None:
                return handle
    candidate = choose_candidate(page, action, dump_path)
    return candidate["handle"]


def fill_element(target, value: str, timeout_ms: int) -> None:
    target.wait_for_element_state("visible", timeout=timeout_ms)
    target.fill(value, timeout=timeout_ms)


def click_element(target, timeout_ms: int) -> None:
    target.wait_for_element_state("visible", timeout=timeout_ms)
    target.click(timeout=timeout_ms)


def login(page, config: dict, timeout_ms: int, dump_dir: Path | None) -> None:
    login_cfg = config.get("login", {})
    selectors_cfg = config.get("selectors", {})
    page.goto(require(config, "url"), wait_until="domcontentloaded", timeout=timeout_ms)

    maybe_click(page, login_cfg.get("pre_login_click_selector"), timeout_ms)

    username_dump = dump_dir / "login_username.json" if dump_dir else None
    password_dump = dump_dir / "login_password.json" if dump_dir else None
    submit_dump = dump_dir / "login_submit.json" if dump_dir else None

    username_target = resolve_element(
        page,
        optional({"selectors": selectors_cfg}, "selectors.login_username"),
        "login_username",
        username_dump,
    )
    password_target = resolve_element(
        page,
        optional({"selectors": selectors_cfg}, "selectors.login_password"),
        "login_password",
        password_dump,
    )
    submit_target = resolve_element(
        page,
        optional({"selectors": selectors_cfg}, "selectors.login_submit"),
        "login_submit",
        submit_dump,
    )

    fill_element(username_target, require(config, "login.username"), timeout_ms)
    fill_element(password_target, require(config, "login.password"), timeout_ms)
    click_element(submit_target, timeout_ms)

    wait_after_login = login_cfg.get("wait_for_selector_after_login")
    if wait_after_login:
        page.wait_for_selector(wait_after_login, timeout=timeout_ms)
    else:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)


def fill_home_form(page, config: dict, timeout_ms: int, dump_dir: Path | None) -> None:
    selectors_cfg = config.get("selectors", {})
    target_value = require(config, "target.value")
    username_dump = dump_dir / "home_username.json" if dump_dir else None
    apply_dump = dump_dir / "apply_button.json" if dump_dir else None

    username_target = resolve_element(
        page,
        optional({"selectors": selectors_cfg}, "selectors.home_username"),
        "home_username",
        username_dump,
    )
    apply_target = resolve_element(
        page,
        optional({"selectors": selectors_cfg}, "selectors.apply_button"),
        "apply_button",
        apply_dump,
    )

    fill_element(username_target, target_value, timeout_ms)
    click_element(apply_target, timeout_ms)

    success_selector = selectors_cfg.get("success_after_apply")
    if success_selector:
        page.wait_for_selector(success_selector, timeout=timeout_ms)


def run(config_path: Path, headed: bool) -> None:
    config = load_config(config_path)
    timeout_ms = int(config.get("timeout_ms", 30000))
    proxy_cfg = config.get("proxy")
    debug_cfg = config.get("debug", {})
    dump_dir = None
    if debug_cfg.get("dump_candidates_dir"):
        dump_dir = Path(debug_cfg["dump_candidates_dir"])

    launch_options = {
        "headless": not headed,
        "slow_mo": config.get("slow_mo_ms", 0),
    }

    if proxy_cfg and proxy_cfg.get("server"):
        launch_options["proxy"] = {
            "server": proxy_cfg["server"],
        }
        if proxy_cfg.get("username"):
            launch_options["proxy"]["username"] = proxy_cfg["username"]
        if proxy_cfg.get("password"):
            launch_options["proxy"]["password"] = proxy_cfg["password"]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page()

        try:
            login(page, config, timeout_ms, dump_dir)
            fill_home_form(page, config, timeout_ms, dump_dir)
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
