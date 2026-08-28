/**
 * Chat Logic for Modular LLM + MCP Chat Application
 * Handles API communication, UI updates, error states, and history management.
 */

// Determine API base URL
const API_BASE_URL = window.location.origin.startsWith('http') && !window.location.origin.includes('5500') && !window.location.origin.includes('3000') && !window.location.origin.includes('8080')
    ? (window.location.port === '8000' ? '' : 'http://localhost:8000')
    : 'http://localhost:8000';

// State
let conversationHistory = [];
let isWaitingResponse = false;

// DOM Elements
const chatMessagesContainer = document.getElementById('chat-messages');
const chatForm = document.getElementById('chat-form');
const userInput = document.getElementById('user-input');
const sendButton = document.getElementById('send-btn');
const sendIcon = document.getElementById('send-icon');
const clearChatBtn = document.getElementById('clear-chat-btn');
const backendStatusPill = document.getElementById('backend-status');
const mcpStatusPill = document.getElementById('mcp-status');
const modelBadge = document.getElementById('model-badge');
const errorBanner = document.getElementById('error-banner');
const errorMessageText = document.getElementById('error-message');

/**
 * Initializes app on DOM load
 */
document.addEventListener('DOMContentLoaded', () => {
    checkHealth();
    // Periodically poll backend status
    setInterval(checkHealth, 15000);

    // Form submission
    chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        sendMessage();
    });

    // Handle Enter key (Shift+Enter for newline)
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-expand textarea
    userInput.addEventListener('input', () => {
        userInput.style.height = 'auto';
        userInput.style.height = Math.min(userInput.scrollHeight, 160) + 'px';
    });

    // Clear Chat
    clearChatBtn.addEventListener('click', clearChat);
});

/**
 * Polls /api/health to update connection status badges
 */
async function checkHealth() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/health`, {
            method: 'GET',
            headers: { 'Accept': 'application/json' },
        });

        if (response.ok) {
            const data = await response.json();
            
            // Update Backend Status
            backendStatusPill.className = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-950/60 text-emerald-300 border border-emerald-800/60';
            backendStatusPill.innerHTML = '<span class="w-2 h-2 rounded-full status-dot-active"></span> Backend Online';

            // Update MCP Status
            if (data.mcp_status === 'connected') {
                const toolCount = data.mcp_tools ? data.mcp_tools.length : 0;
                mcpStatusPill.className = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-indigo-950/60 text-indigo-300 border border-indigo-800/60';
                mcpStatusPill.innerHTML = `<span class="w-2 h-2 rounded-full status-dot-active"></span> MCP Active (${toolCount} tools)`;
            } else {
                mcpStatusPill.className = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-950/60 text-amber-300 border border-amber-800/60';
                mcpStatusPill.innerHTML = '<span class="w-2 h-2 rounded-full status-dot-warning"></span> MCP Standby';
            }

            // Update Model Badge
            if (data.gemini_configured) {
                modelBadge.textContent = data.gemini_model || 'Gemini 2.5 Flash';
                modelBadge.className = 'px-2.5 py-1 rounded-full text-xs font-medium bg-blue-950/60 text-blue-300 border border-blue-800/60';
            } else {
                modelBadge.textContent = 'Gemini (Key Pending)';
                modelBadge.className = 'px-2.5 py-1 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700';
            }

            hideError();
        } else {
            setOfflineStatus();
        }
    } catch (err) {
        setOfflineStatus();
    }
}

function setOfflineStatus() {
    backendStatusPill.className = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-rose-950/60 text-rose-300 border border-rose-800/60';
    backendStatusPill.innerHTML = '<span class="w-2 h-2 rounded-full status-dot-error"></span> Backend Offline';
    
    mcpStatusPill.className = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700';
    mcpStatusPill.innerHTML = '<span class="w-2 h-2 rounded-full bg-slate-500"></span> MCP Offline';
}

/**
 * Handles sending a message
 */
async function sendMessage() {
    if (isWaitingResponse) return;

    const messageText = userInput.value.trim();
    if (!messageText) return;

    // Reset input
    userInput.value = '';
    userInput.style.height = 'auto';
    hideError();

    // Append User Message to UI
    appendUserMessage(messageText);

    // Set Loading State
    isWaitingResponse = true;
    setSendButtonState(true);
    showTypingIndicator();

    try {
        const response = await fetch(`${API_BASE_URL}/api/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({
                message: messageText,
                history: conversationHistory
            })
        });

        removeTypingIndicator();

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            const errDetail = errorData.detail || `HTTP Error ${response.status}: ${response.statusText}`;
            throw new Error(errDetail);
        }

        const data = await response.json();
        
        // Append AI message with any MCP tool badges
        appendAIMessage(data.response, data.tools_used);

        // Update history
        conversationHistory.push({ role: 'user', content: messageText });
        conversationHistory.push({ role: 'model', content: data.response });

    } catch (error) {
        removeTypingIndicator();
        console.error('Chat error:', error);
        
        // Render Error Message in Chat
        appendErrorMessage(`Failed to get response: ${error.message}. Please check if the FastAPI backend is running at ${API_BASE_URL}.`);
        showError(`Backend connection failed: ${error.message}`);
    } finally {
        isWaitingResponse = false;
        setSendButtonState(false);
        userInput.focus();
    }
}

/**
 * Appends User message bubble to DOM
 */
function appendUserMessage(text) {
    // Remove welcome screen if present
    const welcomeScreen = document.getElementById('welcome-screen');
    if (welcomeScreen) {
        welcomeScreen.remove();
    }

    const msgWrapper = document.createElement('div');
    msgWrapper.className = 'flex justify-end mb-4 animate-message';
    
    msgWrapper.innerHTML = `
        <div class="max-w-[85%] md:max-w-[70%] bg-gradient-to-r from-indigo-600 to-indigo-500 text-white px-4 py-3 rounded-2xl rounded-tr-sm shadow-md shadow-indigo-950/20">
            <p class="text-sm md:text-base leading-relaxed whitespace-pre-wrap">${escapeHtml(text)}</p>
        </div>
    `;

    chatMessagesContainer.appendChild(msgWrapper);
    scrollToBottom();
}

/**
 * Appends AI message bubble with MCP tool metadata badges
 */
function appendAIMessage(markdownText, toolsUsed = []) {
    const msgWrapper = document.createElement('div');
    msgWrapper.className = 'flex justify-start mb-6 animate-message';

    let toolsHtml = '';
    if (toolsUsed && toolsUsed.length > 0) {
        toolsHtml = '<div class="flex flex-wrap gap-2 mb-2">';
        toolsUsed.forEach((t, idx) => {
            const toolName = t.tool || 'MCP Tool';
            const argsStr = JSON.stringify(t.arguments || {});
            toolsHtml += `
                <div class="mcp-tool-badge">
                    <svg class="w-3.5 h-3.5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path>
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                    </svg>
                    <span>MCP: <strong>${escapeHtml(toolName)}</strong></span>
                </div>
            `;
        });
        toolsHtml += '</div>';
    }

    const parsedHtml = renderMarkdown(markdownText);

    msgWrapper.innerHTML = `
        <div class="flex items-start gap-3 max-w-[90%] md:max-w-[78%]">
            <!-- Avatar -->
            <div class="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center text-white flex-shrink-0 shadow-sm shadow-indigo-500/20 font-bold text-xs">
                AI
            </div>
            <!-- Bubble -->
            <div class="glass-card text-slate-200 px-4 py-3.5 rounded-2xl rounded-tl-sm shadow-sm prose prose-invert prose-sm max-w-none">
                ${toolsHtml}
                <div class="leading-relaxed">${parsedHtml}</div>
            </div>
        </div>
    `;

    chatMessagesContainer.appendChild(msgWrapper);
    scrollToBottom();
}

/**
 * Appends Error Message bubble to DOM
 */
function appendErrorMessage(text) {
    const msgWrapper = document.createElement('div');
    msgWrapper.className = 'flex justify-start mb-4 animate-message';
    
    msgWrapper.innerHTML = `
        <div class="flex items-start gap-3 max-w-[85%]">
            <div class="w-8 h-8 rounded-lg bg-rose-900/80 border border-rose-700 flex items-center justify-center text-rose-300 flex-shrink-0 font-bold text-xs">
                !
            </div>
            <div class="bg-rose-950/50 border border-rose-800/60 text-rose-200 px-4 py-3 rounded-2xl rounded-tl-sm text-sm">
                <p class="font-semibold text-rose-300 mb-1">Execution Error</p>
                <p class="leading-relaxed">${escapeHtml(text)}</p>
            </div>
        </div>
    `;

    chatMessagesContainer.appendChild(msgWrapper);
    scrollToBottom();
}

/**
 * Shows Typing / Loading Indicator
 */
function showTypingIndicator() {
    const typingElem = document.createElement('div');
    typingElem.id = 'typing-indicator';
    typingElem.className = 'flex items-center gap-3 mb-4 animate-message';
    
    typingElem.innerHTML = `
        <div class="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-400 text-xs font-medium">
            AI
        </div>
        <div class="glass-card px-4 py-3 rounded-2xl rounded-tl-sm flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-indigo-400 typing-dot"></span>
            <span class="w-2 h-2 rounded-full bg-indigo-400 typing-dot"></span>
            <span class="w-2 h-2 rounded-full bg-indigo-400 typing-dot"></span>
            <span class="text-xs text-slate-400 ml-2 font-medium">Processing MCP tools & LLM...</span>
        </div>
    `;

    chatMessagesContainer.appendChild(typingElem);
    scrollToBottom();
}

function removeTypingIndicator() {
    const elem = document.getElementById('typing-indicator');
    if (elem) elem.remove();
}

/**
 * Clears chat history and re-renders welcome screen
 */
function clearChat() {
    conversationHistory = [];
    chatMessagesContainer.innerHTML = `
        <div id="welcome-screen" class="my-auto py-12 text-center max-w-lg mx-auto">
            <div class="w-16 h-16 rounded-2xl bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center text-white text-2xl mx-auto mb-4 shadow-lg shadow-indigo-500/25">
                ⚡
            </div>
            <h2 class="text-2xl font-bold text-slate-100 mb-2">Modular LLM + MCP Chat</h2>
            <p class="text-sm text-slate-400 mb-6">
                Directly connected to a Python Model Context Protocol (MCP) server for real-time tool execution.
            </p>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-left">
                <button onclick="usePromptChip('What is the current time in Tokyo, London, and New York?')" class="prompt-chip p-3 rounded-xl glass-card text-xs text-slate-300 hover:text-white transition">
                    🕒 <strong>World Time</strong><br><span class="text-slate-400">Time in Tokyo, London & NYC</span>
                </button>
                <button onclick="usePromptChip('Calculate (256 * 48) + sqrt(144)')" class="prompt-chip p-3 rounded-xl glass-card text-xs text-slate-300 hover:text-white transition">
                    🧮 <strong>Math Expression</strong><br><span class="text-slate-400">(256 * 48) + sqrt(144)</span>
                </button>
                <button onclick="usePromptChip('What day of the week is it in India right now?')" class="prompt-chip p-3 rounded-xl glass-card text-xs text-slate-300 hover:text-white transition">
                    📅 <strong>Local Date</strong><br><span class="text-slate-400">Current day in India</span>
                </button>
                <button onclick="usePromptChip('Calculate 2^16 - 1024')" class="prompt-chip p-3 rounded-xl glass-card text-xs text-slate-300 hover:text-white transition">
                    ⚡ <strong>Powers & Exponents</strong><br><span class="text-slate-400">Calculate 2^16 - 1024</span>
                </button>
            </div>
        </div>
    `;
    hideError();
}

/**
 * Fills input and triggers send from a chip button
 */
function usePromptChip(text) {
    userInput.value = text;
    sendMessage();
}

/**
 * UI State Helpers
 */
function setSendButtonState(loading) {
    sendButton.disabled = loading;
    if (loading) {
        sendButton.classList.add('opacity-50', 'cursor-not-allowed');
    } else {
        sendButton.classList.remove('opacity-50', 'cursor-not-allowed');
    }
}

function showError(message) {
    errorMessageText.textContent = message;
    errorBanner.classList.remove('hidden');
}

function hideError() {
    errorBanner.classList.add('hidden');
}

function scrollToBottom() {
    chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Lightweight Safe Markdown Parser
 */
function renderMarkdown(md) {
    if (!md) return '';
    
    let html = escapeHtml(md);
    
    // Code blocks: ```language\n code \n```
    html = html.replace(/```([\s\S]*?)```/g, (match, code) => {
        return `<pre class="my-2 text-xs"><code>${code.trim()}</code></pre>`;
    });

    // Inline code: `code`
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bold: **text**
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Italic: *text*
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // Blockquotes: > text
    html = html.replace(/^&gt;\s?(.*)$/gm, '<blockquote class="border-l-2 border-indigo-500 pl-3 my-2 text-slate-400 text-xs italic">$1</blockquote>');

    // Line breaks
    html = html.replace(/\n/g, '<br>');

    return html;
}
