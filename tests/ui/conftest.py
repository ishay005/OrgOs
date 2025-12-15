"""
UI Test Configuration

Provides Playwright fixtures and test server setup for UI tests.
Uses the fake OpenAI client from the main conftest.
"""

import pytest
import os
import subprocess
import time
import socket

# Only import playwright if available
try:
    from playwright.sync_api import sync_playwright, Page, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = None
    Browser = None


def is_port_in_use(port: int) -> bool:
    """Check if a port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


@pytest.fixture(scope="session")
def test_server():
    """
    Start a test server for UI tests.
    Uses a test database and fake OpenAI client.
    """
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not installed")
    
    port = 8001  # Use different port than dev server
    
    # Check if server already running
    if is_port_in_use(port):
        yield f"http://localhost:{port}"
        return
    
    # Set test environment
    env = os.environ.copy()
    env["APP_ENV"] = "test"
    env["DATABASE_URL"] = env.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/orgos_test")
    
    # Start server
    process = subprocess.Popen(
        ["uvicorn", "app.main:app", "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to start
    max_wait = 30
    for _ in range(max_wait):
        if is_port_in_use(port):
            break
        time.sleep(1)
    else:
        process.terminate()
        pytest.fail(f"Server did not start within {max_wait} seconds")
    
    yield f"http://localhost:{port}"
    
    # Cleanup
    process.terminate()
    process.wait()


@pytest.fixture(scope="session")
def browser():
    """Provide a Playwright browser instance."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not installed")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser, test_server) -> Page:
    """Provide a fresh page for each test."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not installed")
    
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture
def logged_in_page(page, test_server, db_session, sample_users) -> Page:
    """Provide a page logged in as a test user."""
    user = sample_users["employee1"]
    
    # Navigate to app
    page.goto(test_server)
    
    # Log in (select user from dropdown)
    # This depends on the actual login mechanism
    try:
        # Wait for page to load
        page.wait_for_load_state("networkidle")
        
        # Select user from dropdown (adjust selector based on actual UI)
        user_select = page.locator("select#user-select, #user-dropdown, [data-testid='user-select']").first
        if user_select.is_visible():
            user_select.select_option(label=user.name)
        
        # Or click login button if needed
        login_btn = page.locator("button:has-text('Login'), button:has-text('Sign In')").first
        if login_btn.is_visible():
            login_btn.click()
        
        page.wait_for_load_state("networkidle")
    except:
        pass  # Login mechanism may vary
    
    return page

