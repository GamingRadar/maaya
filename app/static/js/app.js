/**
 * MAAYA Mobile Chat Application Script - Phase 5 Persistent Conversations
 * - Full SQLite-backed multi-conversation lifecycle
 * - Dynamic drawer navigation for conversation history
 * - Safe DOM manipulation (textContent only, strictly no unsafe innerHTML)
 * - Auto-resizing textarea with mobile keyboard adjustments
 * - Resilient error handling and retry support
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
  const activeConvTitle = document.getElementById('activeConvTitle');

  // Drawer Elements
  const historyToggleBtn = document.getElementById('historyToggleBtn');
  const newChatBtn = document.getElementById('newChatBtn');
  const drawerNewChatBtn = document.getElementById('drawerNewChatBtn');
  const closeDrawerBtn = document.getElementById('closeDrawerBtn');
  const drawerBackdrop = document.getElementById('drawerBackdrop');
  const conversationsDrawer = document.getElementById('conversationsDrawer');
  const conversationsList = document.getElementById('conversationsList');

  // Application State
  let currentConversationId = null;
  let conversations = [];
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
   * Toggle the slide-out conversations drawer.
   */
  function setDrawerOpen(open) {
    if (open) {
      conversationsDrawer.classList.add('open');
      conversationsDrawer.setAttribute('aria-hidden', 'false');
      drawerBackdrop.classList.add('active');
      drawerBackdrop.setAttribute('aria-hidden', 'false');
    } else {
      conversationsDrawer.classList.remove('open');
      conversationsDrawer.setAttribute('aria-hidden', 'true');
      drawerBackdrop.classList.remove('active');
      drawerBackdrop.setAttribute('aria-hidden', 'true');
    }
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
   * Clear the active messages display.
   */
  function clearMessagesDisplay() {
    messagesList.replaceChildren();
    hasMessages = false;
    if (emptyState) {
      emptyState.style.display = 'flex';
    }
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
   * Render conversation list in the drawer.
   */
  function renderConversationsList() {
    conversationsList.replaceChildren();

    if (conversations.length === 0) {
      const emptyDiv = document.createElement('div');
      emptyDiv.style.padding = '16px';
      emptyDiv.style.color = 'var(--text-subtle)';
      emptyDiv.style.fontSize = '0.85rem';
      emptyDiv.style.textAlign = 'center';
      emptyDiv.textContent = 'No conversations yet';
      conversationsList.appendChild(emptyDiv);
      return;
    }

    conversations.forEach((conv) => {
      const item = document.createElement('div');
      item.className = `conv-item${conv.id === currentConversationId ? ' active' : ''}`;
      item.setAttribute('role', 'listitem');

      const info = document.createElement('div');
      info.className = 'conv-info';
      info.addEventListener('click', () => {
        if (conv.id !== currentConversationId) {
          loadConversation(conv.id);
        }
        setDrawerOpen(false);
      });

      const title = document.createElement('div');
      title.className = 'conv-title';
      title.textContent = conv.title || 'New Conversation';

      const meta = document.createElement('div');
      meta.className = 'conv-meta';
      const msgCount = conv.message_count || 0;
      meta.textContent = `${msgCount} message${msgCount === 1 ? '' : 's'}`;

      info.appendChild(title);
      info.appendChild(meta);

      const delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'conv-delete-btn';
      delBtn.setAttribute('aria-label', `Delete ${conv.title}`);
      delBtn.title = 'Delete conversation';
      delBtn.innerHTML = `
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polyline points="3 6 5 6 21 6"></polyline>
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
        </svg>
      `;
      delBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        confirmDeleteConversation(conv.id, conv.title);
      });

      item.appendChild(info);
      item.appendChild(delBtn);
      conversationsList.appendChild(item);
    });
  }

  /**
   * Fetch conversation list from backend API.
   */
  async function fetchConversations() {
    try {
      const resp = await fetch('/conversations', {
        headers: { 'Accept': 'application/json' },
      });
      if (resp.ok) {
        conversations = await resp.json();
        renderConversationsList();
      }
    } catch (err) {
      console.warn('Failed to load conversations:', err);
    }
  }

  /**
   * Create a new conversation via API and make it active.
   */
  async function createNewConversation() {
    try {
      const resp = await fetch('/conversations', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({ title: 'New Conversation' }),
      });
      if (resp.ok) {
        const conv = await resp.json();
        currentConversationId = conv.id;
        activeConvTitle.textContent = conv.title;
        clearMessagesDisplay();
        await fetchConversations();
        setDrawerOpen(false);
        messageInput.focus();
        return conv.id;
      }
    } catch (err) {
      console.error('Failed to create new conversation:', err);
    }
    return null;
  }

  /**
   * Load an existing conversation and its messages.
   */
  async function loadConversation(convId) {
    clearMessagesDisplay();
    currentConversationId = convId;

    try {
      const resp = await fetch(`/conversations/${convId}`, {
        headers: { 'Accept': 'application/json' },
      });
      if (resp.ok) {
        const data = await resp.json();
        activeConvTitle.textContent = data.title || 'New Conversation';

        if (Array.isArray(data.messages) && data.messages.length > 0) {
          data.messages.forEach((msg) => {
            appendMessage(msg.role, msg.content, msg.status === 'failed');
          });
        }
        renderConversationsList();
      } else {
        appendMessage('assistant', 'Could not load conversation. It may have been deleted.', true);
      }
    } catch (err) {
      appendMessage('assistant', 'Failed to retrieve conversation history.', true);
    }
  }

  /**
   * Confirm and delete a conversation.
   */
  async function confirmDeleteConversation(convId, title) {
    const confirmed = window.confirm(`Delete conversation "${title}"? This cannot be undone.`);
    if (!confirmed) return;

    try {
      const resp = await fetch(`/conversations/${convId}`, {
        method: 'DELETE',
        headers: { 'Accept': 'application/json' },
      });
      if (resp.ok) {
        await fetchConversations();
        if (currentConversationId === convId) {
          // If we deleted the active conversation, open the next available or create new
          if (conversations.length > 0) {
            await loadConversation(conversations[0].id);
          } else {
            await createNewConversation();
          }
        }
      } else {
        alert('Could not delete conversation.');
      }
    } catch (err) {
      alert('Error connecting to delete conversation.');
    }
  }

  /**
   * Send user message to the Starlette backend API (POST /chat).
   */
  async function sendMessage(rawText) {
    const text = (rawText !== undefined ? rawText : messageInput.value).trim();
    if (!text || isSending) return;

    // Ensure we have an active conversation ID
    if (!currentConversationId) {
      const newId = await createNewConversation();
      if (!newId) {
        appendMessage('assistant', 'Failed to initialize a conversation session.', true);
        return;
      }
    }

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
      // 210-second client timeout ensures browser does not drop connection
      // before backend's 180-second inference timeout
      const controller = new AbortController();
      const clientTimeoutId = setTimeout(() => controller.abort(), 210000);

      let response;
      try {
        response = await fetch('/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          },
          body: JSON.stringify({
            message: text,
            conversation_id: currentConversationId,
          }),
          signal: controller.signal,
        });
      } finally {
        clearTimeout(clientTimeoutId);
      }

      let data = null;
      try {
        data = await response.json();
      } catch (jsonErr) {
        // Non-JSON response
      }

      if (response.ok && data && data.response) {
        // Success: clear saved retry draft and display assistant response
        lastUnsentMessage = '';
        appendMessage('assistant', data.response);
        // Refresh conversation list to reflect updated title and timestamp
        await fetchConversations();
        const active = conversations.find((c) => c.id === currentConversationId);
        if (active) {
          activeConvTitle.textContent = active.title;
        }
      } else {
        let errMsg = '';
        if (data && data.error) {
          errMsg = data.error;
        } else if (response.status === 504) {
          errMsg = 'Inference timed out. The model took too long to generate a response.';
        } else if (response.status === 503) {
          errMsg = 'Service unavailable. The model file or executable was not found.';
        } else if (response.status >= 500) {
          errMsg = 'Internal server error while processing your message.';
        } else {
          errMsg = 'Request failed (' + response.status + '). Please try again.';
        }
        appendMessage('assistant', errMsg, true);
      }
    } catch (netErr) {
      if (netErr.name === 'AbortError') {
        appendMessage('assistant', 'Request timed out waiting for the local model. Please try again.', true);
      } else {
        appendMessage('assistant', 'Could not reach the local MAAYA service. Please check that the server is running.', true);
      }
    } finally {
      setLoadingState(false);
      messageInput.focus();
    }
  }

  // ==========================================================================
  // Event Listeners & Initialization
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

  // Drawer toggles
  historyToggleBtn.addEventListener('click', () => setDrawerOpen(true));
  closeDrawerBtn.addEventListener('click', () => setDrawerOpen(false));
  drawerBackdrop.addEventListener('click', () => setDrawerOpen(false));

  // New Chat buttons
  newChatBtn.addEventListener('click', () => createNewConversation());
  drawerNewChatBtn.addEventListener('click', () => createNewConversation());

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

  // Initial Page Load
  window.addEventListener('load', async function () {
    adjustTextareaHeight();
    messageInput.focus();
    checkServerStatus();
    setInterval(checkServerStatus, 20000);

    // Load conversation history on startup
    await fetchConversations();
    if (conversations.length > 0) {
      // Reopen the most recently updated conversation
      await loadConversation(conversations[0].id);
    } else {
      // If no conversations exist, create the initial one
      await createNewConversation();
    }
  });

})();
