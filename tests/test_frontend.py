"""Tests for the frontend chat interface and static asset serving."""

from starlette.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_index_page_returns_html_and_status_200():
    """Verify GET / returns HTTP 200 with HTML content."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<!DOCTYPE html>" in response.text
    assert "MAAYA" in response.text


def test_index_page_references_required_assets():
    """Verify index HTML references the static stylesheet and script and contains Phase 5 elements."""
    response = client.get("/")
    assert response.status_code == 200
    assert 'href="/static/css/style.css"' in response.text
    assert 'src="/static/js/app.js"' in response.text
    assert 'id="chatArea"' in response.text
    assert 'id="messageInput"' in response.text
    assert 'id="sendButton"' in response.text
    assert 'id="typingIndicator"' in response.text
    assert 'id="statusDot"' in response.text
    assert 'id="conversationsDrawer"' in response.text
    assert 'id="newChatBtn"' in response.text
    assert 'id="historyToggleBtn"' in response.text


def test_static_css_served_successfully():
    """Verify GET /static/css/style.css returns HTTP 200 with CSS content."""
    response = client.get("/static/css/style.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert "--bg-app" in response.text
    assert "--accent-teal" in response.text


def test_static_js_served_successfully():
    """Verify GET /static/js/app.js returns HTTP 200 with JavaScript content."""
    response = client.get("/static/js/app.js")
    assert response.status_code == 200
    assert "application/javascript" in response.headers["content-type"] or "text/javascript" in response.headers["content-type"]
    assert "sendMessage" in response.text
    assert "checkServerStatus" in response.text
    # Verify timeout alignment & error classification logic is present in script
    assert "210000" in response.text  # 210s client timeout
    assert "504" in response.text
    assert "500" in response.text
    assert "AbortError" in response.text
    assert "Inference timed out" in response.text
    assert "Could not reach the local MAAYA service" in response.text
