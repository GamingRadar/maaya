/**
 * MAAYA Mobile Chat Application Script
 * - Session-based conversation state
 * - Asynchronous communication with /chat and /health
 * - Safe DOM manipulation (textContent only, strictly no unsafe innerHTML)
 * - Auto-resizing textarea with mobile keyboard adjustments
 */

(function () {
  'use strict';

  // DOM Elements
  const chatArea = document.getElementById('chatArea');
  const messagesList = document.getElementById('messagesList');
  const emptyState = document.getElementById('emptyState');
  const typingIndicator = document.getElementById('typingIndicator');
  const composerForm = document.getElementById('composerForm');
  const messageInput = document.getElementById('messageInput');
  const sendButton = document.getElementById('sendButton');
  const statusDot = document.getElementById('statusDot');
  const statusText = document.getElementById('statusText');

  // Application State
  let isSending = false;
  let hasMessages = false;
  let lastUnsentMessage = '';

  /**
   * Check backend health using GET /health and update indicator accurately.
   */
  async function checkServerStatus() {
    try {
      const response = await fetch('/health', {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
      });
      if (response.ok) {
        const data = await response.json();
        if (data.status === 'healthy') {
          statusDot.className = 'status-dot online';
          statusText.textContent = 'Ready';
          return;
        }
      }
      statusDot.className = 'status-dot offline';
      statusText.textContent = 'Degraded';
    } catch (e) {
      statusDot.className = 'status-dot offline';
      statusText.textContent = 'Offline';
    }
  }

  /**
   * Scroll conversation to the latest message.
   */
  function scrollToBottom() {
    requestAnimationFrame(() => {
      chatArea.scrollTop = chatArea.scrollHeight;
    });
  }

  /**
   * Auto-resize composer textarea as user types (capped at 120px max height).
   */
  function adjustTextareaHeight() {
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
  }

  /**
   * Safely append a message bubble into the conversation using DOM elements.
   * NEVER uses innerHTML to avoid XSS vulnerabilities from model or user text.
   */
  function appendMessage(role, text, isError = false) {
    if (!hasMessages) {
      hasMessages = true;
      if (emptyState) {
        emptyState.style.display = 'none';
      }
    }

    const row = document.createElement('div');
    row.className = `message-row ${role}${isError ? ' error' : ''}`;

    const meta = document.createElement('div');
    meta.className = 'message-meta';
    meta.textContent = role === 'user' ? 'You' : (isError ? 'Notice' : 'MAAYA');

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = text; // Safe text insertion

    row.appendChild(meta);
    row.appendChild(bubble);

    if (isError && lastUnsentMessage) {
      const actions = document.createElement('div');
      actions.className = 'error-actions';

      const retryBtn = document.createElement('button');
      retryBtn.type = 'button';
      retryBtn.className = 'retry-btn';
      retryBtn.textContent = 'Retry message';
      retryBtn.addEventListener('click', () => {
        messageInput.value = lastUnsentMessage;
        adjustTextareaHeight();
        messageInput.focus();
        sendMessage(lastUnsentMessage);
      });

      actions.appendChild(retryBtn);
      row.appendChild(actions);
    }

    messagesList.appendChild(row);
    scrollToBottom();
  }

  /**
   * Set loading / typing indicator visibility and disable/enable input.
   */
  function setLoadingState(loading) {
    isSending = loading;
    sendButton.disabled = loading;
    messageInput.disabled = loading;

    if (loading) {
      typingIndicator.classList.add('active');
      typingIndicator.removeAttribute('aria-hidden');
    } else {
      typingIndicator.classList.remove('active');
      typingIndicator.setAttribute('aria-hidden', 'true');
    }
    scrollToBottom();
  }

  /**
   * Send user message to the Starlette backend API (POST /chat).
   */
  async function sendMessage(rawText) {
    const text = (rawText !== undefined ? rawText : messageInput.value).trim();
    if (!text || isSending) return;

    // Save in case we need to retry on failure
    lastUnsentMessage = text;

    // 1. Display user message immediately
    appendMessage('user', text);

    // 2. Clear and reset input field
    messageInput.value = '';
    adjustTextareaHeight();

    // 3. Set UI to generating state
    setLoadingState(true);

    try {
      const response = await fetch('/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({ message: text }),
      });

      let data = null;
      try {
        data = await response.json();
      } catch (jsonErr) {
        // Handle non-JSON server error response
      }

      if (response.ok && data && data.response) {
        // Success: clear saved retry draft and display assistant response
        lastUnsentMessage = '';
        appendMessage('assistant', data.response);
      } else {
        // Handled server error
        const errMsg = (data && data.error)
          ? data.error
          : 'Unable to get a response from MAAYA. Please verify the model is loaded.';
        appendMessage('assistant', errMsg, true);
      }
    } catch (netErr) {
      // Network or connection failure
      appendMessage(
        'assistant',
        'Could not reach the local MAAYA service. Please check that the server is running.',
        true
      );
    } finally {
      setLoadingState(false);
      messageInput.focus();
    }
  }

  // ==========================================================================
  // Event Listeners
  // ==========================================================================

  // Form submit
  composerForm.addEventListener('submit', function (e) {
    e.preventDefault();
    sendMessage();
  });

  // Enter to send, Shift+Enter for newline
  messageInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Auto-resize textarea on input
  messageInput.addEventListener('input', adjustTextareaHeight);

  // Handle empty state quick suggestion chips
  document.querySelectorAll('.hint-chip').forEach(function (chip) {
    chip.addEventListener('click', function () {
      const prompt = this.getAttribute('data-prompt');
      if (prompt) {
        messageInput.value = prompt;
        adjustTextareaHeight();
        sendMessage(prompt);
      }
    });
  });

  // Focus input on load
  window.addEventListener('load', function () {
    adjustTextareaHeight();
    messageInput.focus();
    checkServerStatus();
    // Periodically refresh status every 20 seconds
    setInterval(checkServerStatus, 20000);
  });

})();
