# Telegram Reels Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a Telegram bot with single-thread interactive menu that wraps the existing Facebook Reels scraper for admin-only usage, with Docker/Portainer-ready deployment files.

**Architecture:** Keep `facebook_reels_cli.py` as the scraping/session engine and add a Telegram orchestration layer that handles menu callbacks, message-state flow, and UX formatting. Store per-admin UI state in-memory and run blocking scraper operations in executor threads while updating loading states by editing one control message.

**Tech Stack:** Python 3.13, python-telegram-bot, requests, BeautifulSoup, Docker.

---

### Task 1: Create Failing Tests for Bot UI and Config

**Files:**
- Create: `tests/test_telegram_bot_ui.py`
- Create: `tests/test_telegram_bot_config.py`
- Create: `tests/test_telegram_bot_state.py`

- [ ] **Step 1: Write failing UI/config/state tests first**

```python
# tests expect these modules/functions/classes:
# telegram_bot_ui.build_main_menu_keyboard
# telegram_bot_ui.format_scan_results_text
# telegram_bot_ui.build_scan_result_keyboard
# telegram_bot_config.load_settings
# telegram_bot_state.UserFlowState
```

- [ ] **Step 2: Run tests to confirm RED state**

Run: `python -m unittest discover -s tests -p "test_telegram_bot_*.py" -v`
Expected: FAIL with `ModuleNotFoundError` for new bot modules.

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_telegram_bot_ui.py tests/test_telegram_bot_config.py tests/test_telegram_bot_state.py
git commit -m "test: add failing tests for telegram bot modules"
```

### Task 2: Implement Core Bot Modules to Pass Tests

**Files:**
- Create: `telegram_bot_config.py`
- Create: `telegram_bot_state.py`
- Create: `telegram_bot_ui.py`
- Modify: `tests/test_telegram_bot_ui.py`
- Modify: `tests/test_telegram_bot_config.py`
- Modify: `tests/test_telegram_bot_state.py`

- [ ] **Step 1: Implement minimal config loader**

```python
# load_settings(): reads TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_USER_ID,
# TELEGRAM_BANNER_URL, TELEGRAM_DEFAULT_WORKERS, TELEGRAM_DEFAULT_TARGET,
# FB_REELS_SESSION_FILE and returns dataclass settings.
```

- [ ] **Step 2: Implement user flow dataclass**

```python
# UserFlowState fields: awaiting, scan_draft, last_scan_results,
# control_chat_id, control_message_id, last_scan_target.
```

- [ ] **Step 3: Implement UI helpers**

```python
# keyboard builders and telegram-safe formatted text functions for:
# main menu, scan order, scan result number buttons, detail action buttons.
```

- [ ] **Step 4: Run tests to reach GREEN**

Run: `python -m unittest discover -s tests -p "test_telegram_bot_*.py" -v`
Expected: PASS for all new test files.

- [ ] **Step 5: Commit core modules**

```bash
git add telegram_bot_config.py telegram_bot_state.py telegram_bot_ui.py tests/test_telegram_bot_ui.py tests/test_telegram_bot_config.py tests/test_telegram_bot_state.py
git commit -m "feat: add telegram bot config, state, and ui helpers"
```

### Task 3: Build Telegram Bot Runtime and Scraper Integration

**Files:**
- Create: `telegram_reels_bot.py`
- Modify: `telegram_bot_ui.py`

- [ ] **Step 1: Add bot handlers and callback router**

```python
# /start command
# callback menu handlers
# text message handler for awaiting states
# admin guard for all update types
```

- [ ] **Step 2: Implement login/session actions**

```python
# paste cookie string flow, session status summary, clear session confirm
# call SessionStore + ReelsScraper from facebook_reels_cli.py
```

- [ ] **Step 3: Implement scan wizard and loading UX**

```python
# collect URL -> order -> limit -> confirm
# run scan_reels_page in executor
# while running, edit control message with spinner + elapsed time
```

- [ ] **Step 4: Implement numbered result selection and layer-2 detail view**

```python
# number button callbacks -> fetch_reel_detail
# send thumbnail media when available
# show detail text + back/home/exit actions
```

- [ ] **Step 5: Run tests and compile checks**

Run: `python -m unittest discover -s tests -p "test_telegram_bot_*.py" -v`
Expected: PASS.

Run: `python -m py_compile telegram_reels_bot.py telegram_bot_config.py telegram_bot_state.py telegram_bot_ui.py`
Expected: no syntax errors.

- [ ] **Step 6: Commit runtime bot code**

```bash
git add telegram_reels_bot.py telegram_bot_ui.py
git commit -m "feat: add telegram bot runtime with single-thread menu flow"
```

### Task 4: Docker/Portainer Packaging and Final Verification

**Files:**
- Create: `requirements.txt`
- Create: `Dockerfile`
- Create: `.dockerignore`
- Modify: `.gitignore`
- Modify: `main.py`

- [ ] **Step 1: Add runtime dependency and container files**

```dockerfile
# python slim base, install requirements, copy app, run telegram_reels_bot.py
```

- [ ] **Step 2: Keep CLI entrypoint intact and add optional bot entrypoint helper**

```python
# main.py remains CLI wrapper; docker runs telegram_reels_bot.py directly
```

- [ ] **Step 3: Run final verification commands**

Run: `python -m unittest discover -s tests -p "test_telegram_bot_*.py" -v`
Expected: PASS.

Run: `python -m py_compile facebook_reels_cli.py main.py telegram_reels_bot.py telegram_bot_config.py telegram_bot_state.py telegram_bot_ui.py`
Expected: PASS.

Run: `python telegram_reels_bot.py --help`
Expected: shows configuration/startup help text (without launching polling).

- [ ] **Step 4: Commit packaging changes**

```bash
git add requirements.txt Dockerfile .dockerignore .gitignore main.py
git commit -m "chore: add docker-ready telegram bot packaging"
```
