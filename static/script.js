import ForceGraph3D from 'https://esm.sh/3d-force-graph';
import SpriteText from 'https://esm.sh/three-spritetext';

const API_URL = "http://127.0.0.1:8000/api";
let currentSessionId = localStorage.getItem('currentSessionId') || generateUUID();
let Graph = null;

// --- DOM Elements ---
const heroSection = document.getElementById('hero-section');
const chatFeed = document.getElementById('chat-feed');
const inputBarContainer = document.getElementById('input-bar-container');
const chatWrapper = document.getElementById('chat-wrapper');
const initialInput = document.getElementById('initial-input');
const chatInput = document.getElementById('chat-input');
const graphContainer = document.getElementById('graph-container');
const chatToolsHeader = document.getElementById('chat-tools-header');
const nodeCountVal = document.getElementById('node-count');
const edgeCountVal = document.getElementById('edge-count');
const fastFillToggle = document.getElementById('fast-fill-toggle');
const historyList = document.getElementById('history-list');

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    if (!localStorage.getItem('currentSessionId')) {
        localStorage.setItem('currentSessionId', currentSessionId);
        saveSessionMetadata(currentSessionId, "New Chat");
    }

    // 1. Restore History
    loadSessions();
    loadFromLocalStorage();
    
    // 2. Fetch Stats
    updateStats();
    
    // 3. Persist Fast Fill setting
    const savedFastFill = localStorage.getItem('fastItems');
    if (savedFastFill === 'true') {
        if(fastFillToggle) fastFillToggle.checked = true;
        // Update UI state for custom buttons if needed
        const btn = document.getElementById('fast-fill-btn');
        if(btn) btn.classList.add('active');
    }
    
    if(fastFillToggle) {
        fastFillToggle.addEventListener('change', () => {
            localStorage.setItem('fastItems', fastFillToggle.checked);
        });
    }
    
    // 4. Force Graph Refresh just in case
    setInterval(updateStats, 10000); // Auto-update stats every 10s
});

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
}

function startNewThread() {
    currentSessionId = generateUUID();
    localStorage.setItem('currentSessionId', currentSessionId);
    saveSessionMetadata(currentSessionId, "New Chat " + new Date().toLocaleTimeString());
    
    clearUIForNewChat();
    loadSessions();
}

function saveSessionMetadata(id, title) {
    let sessions = JSON.parse(localStorage.getItem('sessions') || "[]");
    if (!sessions.find(s => s.id === id)) {
        sessions.unshift({ id, title, timestamp: Date.now() });
        localStorage.setItem('sessions', JSON.stringify(sessions));
    }
}

function loadSessions() {
    const sessions = JSON.parse(localStorage.getItem('sessions') || "[]");
    historyList.innerHTML = '';
    sessions.forEach(s => {
        const div = document.createElement('div');
        div.className = `history-item ${s.id === currentSessionId ? 'active' : ''}`;
        div.onclick = () => loadSession(s.id);
        
        div.innerHTML = `
            <span class="history-title">${escapeHtml(s.title)}</span>
            <button class="delete-session-btn" onclick="deleteSession('${s.id}', event)" title="Delete Chat">
                <i class="fa-solid fa-trash"></i>
            </button>
        `;
        
        historyList.appendChild(div);
    });
}

function deleteSession(id, event) {
    event.stopPropagation(); // Prevent loading the session
    
    if (!confirm("Are you sure you want to delete this chat? This action cannot be undone.")) return;
    
    // 1. Remove from session list
    let sessions = JSON.parse(localStorage.getItem('sessions') || "[]");
    sessions = sessions.filter(s => s.id !== id);
    localStorage.setItem('sessions', JSON.stringify(sessions));
    
    // 2. Remove specific data
    localStorage.removeItem(`chatHistory_${id}`);
    localStorage.removeItem(`sessionActive_${id}`);
    
    // 3. Handle active session deletion
    if (id === currentSessionId) {
        startNewThread(); // Resets UI and creates a fresh session
    } else {
        loadSessions(); // Just refresh list
    }
}

function loadSession(id) {
    currentSessionId = id;
    localStorage.setItem('currentSessionId', id);
    loadFromLocalStorage();
    loadSessions(); // Re-render to update active state
    updateStats();
    if (!graphContainer.classList.contains('hidden')) loadGraph();
}

function clearUIForNewChat() {
    chatFeed.innerHTML = '';
    // Show Hero, Hide Feed
    heroSection.classList.remove('hidden');
    chatFeed.classList.add('hidden');
    inputBarContainer.classList.add('hidden');
    chatToolsHeader.classList.add('hidden');
    
    initialInput.value = '';
    chatInput.value = '';
}

function clearHistory() {
    // Only clears current session content
    chatFeed.innerHTML = '';
    localStorage.removeItem(`chatHistory_${currentSessionId}`);
    
    // Show Hero, Hide Feed
    heroSection.classList.remove('hidden');
    chatFeed.classList.add('hidden');
    inputBarContainer.classList.add('hidden');
    chatToolsHeader.classList.add('hidden');
}

function switchToChatMode() {
    heroSection.classList.add('hidden');
    chatFeed.classList.remove('hidden');
    inputBarContainer.classList.remove('hidden');
    chatToolsHeader.classList.remove('hidden');
    
    // Focus on the sticky input
    setTimeout(() => chatInput.focus(), 100);
}

// --- Chat Logic ---
async function submitInitialQuery() {
    const text = initialInput.value.trim();
    if (!text) return;
    
    // Update session title with first query
    let sessions = JSON.parse(localStorage.getItem('sessions') || "[]");
    const sIndex = sessions.findIndex(s => s.id === currentSessionId);
    if (sIndex >= 0) {
        sessions[sIndex].title = text.substring(0, 30) + (text.length > 30 ? "..." : "");
        localStorage.setItem('sessions', JSON.stringify(sessions));
        loadSessions();
    }
    
    switchToChatMode();
    await processMessage(text);
    
    // Sync inputs so user feels continuity (optional, or just clear)
    initialInput.value = ''; 
    chatInput.value = '';
}

async function submitChatQuery() {
    const text = chatInput.value.trim();
    if (!text) return;
    
    chatInput.value = '';
    chatInput.style.height = 'auto'; // Reset height
    await processMessage(text);
}

// Handle 'Enter' key to submit
[initialInput, chatInput].forEach(el => {
    el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (el === initialInput) submitInitialQuery();
            else submitChatQuery();
        }
    });
});

function appendUserMessage(text) {
    const div = document.createElement('div');
    div.className = 'message user-message';
    div.innerHTML = `
        <div class="msg-avatar user-avatar">U</div>
        <div class="msg-content">
            <div class="msg-header">You</div>
            <p>${escapeHtml(text)}</p>
        </div>
    `;
    chatFeed.appendChild(div);
    scrollToBottom();
    saveToLocalStorage();
}


function appendAIMessage(text, memories = []) {
    const div = document.createElement('div');
    div.className = 'message ai-message';
    
    // Simple formatting
    let formattedText = escapeHtml(text)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');

    // Sources Logic
    let predictionsHtml = '';
    if (memories && memories.length > 0) {
        // Create unique ID for toggle
        const toggleId = 'src-' + Date.now();
        
        const validMemories = memories.filter(m => m && m.trim() !== "");
        
        if (validMemories.length > 0) {
             predictionsHtml = `
                <div class="sources-section">
                    <button class="sources-btn" onclick="toggleSources('${toggleId}')">
                        <i class="fa-solid fa-layer-group"></i> Graph Context: ${validMemories.length} item(s) used
                    </button>
                    <div id="${toggleId}" class="sources-content">
                        ${validMemories.map(m => `
                            <div class="source-item">
                                <i class="fa-solid fa-circle-dot"></i>
                                <span>${escapeHtml(m)}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }
    }

    div.innerHTML = `
        <div class="msg-avatar ai-avatar">
            <img src="dolphin_logo.png" alt="AI">
        </div>
        <div class="msg-content">
            <div class="msg-header">Dolphin</div>
            <p>${formattedText}</p>
            ${predictionsHtml}
        </div>
    `;
    chatFeed.appendChild(div);
    scrollToBottom();
    saveToLocalStorage();
}

function toggleSources(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.toggle('show');
    }
}

async function processMessage(text) {
    appendUserMessage(text);
    
    // Show Loading
    const loadingId = 'loading-' + Date.now();
    const loadingDiv = document.createElement('div');
    loadingDiv.id = loadingId;
    loadingDiv.className = 'message ai-message';
    loadingDiv.innerHTML = `
        <div class="msg-avatar ai-avatar"><img src="dolphin_logo.png"></div>
        <div class="msg-content"><p><i class="fa-solid fa-circle-notch fa-spin"></i> Thinking...</p></div>
    `;
    chatFeed.appendChild(loadingDiv);
    scrollToBottom();

    try {
        const isFastFill = fastFillToggle.checked;
        const llmConfig = JSON.parse(localStorage.getItem('llm_settings') || '{}');
        
        const response = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                message: text, 
                session_id: currentSessionId,
                fast_fill: isFastFill,
                llm_config: llmConfig
            })
        });

        if (!response.ok) throw new Error("API Error");

        const data = await response.json();
        
        // Remove loading
        document.getElementById(loadingId).remove();
        
        appendAIMessage(data.response, data.memories);
        
        // Update Stats & Graph
        updateStats();
        if (!graphContainer.classList.contains('hidden')) {
            loadGraph();
        }

    } catch (error) {
        const loader = document.getElementById(loadingId);
        if(loader) loader.remove();
        console.error("Error:", error);
        appendAIMessage(`Sorry, I encountered an error: ${error.message}`);
    }
}

function scrollToBottom() {
    chatFeed.scrollTop = chatFeed.scrollHeight;
}

function escapeHtml(text) {
    if (!text) return "";
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// --- Features ---
async function updateStats() {
    try {
        const res = await fetch(`${API_URL}/stats?session_id=${currentSessionId}`);
        const data = await res.json();
        nodeCountVal.innerText = data.nodes || 0;
        edgeCountVal.innerText = data.edges || 0;
    } catch (e) {
        console.log("Stats error", e);
    }
}

async function triggerPruning() {
    if(!confirm("Consolidate memories? This will merge redundant nodes.")) return;
    
    const btn = document.getElementById('prune-btn');
    if(btn) btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';

    try {
        const res = await fetch(`${API_URL}/prune`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, limit: 15 })
        });
        const data = await res.json();
        alert(data.message);
        updateStats();
        // Refresh graph if open
        if (!graphContainer.classList.contains('hidden')) loadGraph();
    } catch (e) {
        alert("Pruning failed: " + e.message);
    } finally {
        if(btn) btn.innerHTML = '<i class="fa-solid fa-broom"></i>';
    }
}

function toggleFastFill() {
    const isChecked = !fastFillToggle.checked;
    fastFillToggle.checked = isChecked;
    localStorage.setItem('fastItems', isChecked);
    
    const btn = document.getElementById('fast-fill-btn');
    if (btn) {
        if (isChecked) btn.classList.add('active');
        else btn.classList.remove('active');
    }
}

// --- Storage ---
function saveToLocalStorage() {
    localStorage.setItem(`chatHistory_${currentSessionId}`, chatFeed.innerHTML);
    localStorage.setItem(`sessionActive_${currentSessionId}`, !heroSection.classList.contains('hidden') ? 'false' : 'true');
}

function loadFromLocalStorage() {
    const history = localStorage.getItem(`chatHistory_${currentSessionId}`);
    const isActive = localStorage.getItem(`sessionActive_${currentSessionId}`);
    
    if (history && isActive === 'true') {
        chatFeed.innerHTML = history;
        switchToChatMode();
    } else {
        clearUIForNewChat();
    }
}

// --- Graph Visualization ---
function toggleGraph() {
    graphContainer.classList.toggle('hidden');
    if (!graphContainer.classList.contains('hidden')) {
        loadGraph();
    }
}

function refreshGraph() {
    loadGraph();
}

// --- Settings Modal Logic ---
const settingsModal = document.getElementById('settings-modal');
const providerSelect = document.getElementById('llm-provider-select');
const apiKeyInput = document.getElementById('api-key-input');

function openSettings() {
    // Load current values
    const config = JSON.parse(localStorage.getItem('llm_settings') || '{}');
    if (config.provider) providerSelect.value = config.provider;
    if (config.api_key) apiKeyInput.value = config.api_key;
    
    settingsModal.classList.remove('hidden');
}

function closeSettings() {
    settingsModal.classList.add('hidden');
}

function saveSettings() {
    const provider = providerSelect.value;
    const key = apiKeyInput.value.trim();
    
    localStorage.setItem('llm_settings', JSON.stringify({
        provider: provider,
        api_key: key
    }));
    
    closeSettings();
    alert("Configuration saved!");
}

const highlightNodes = new Set();
const highlightLinks = new Set();
let hoverNode = null;

async function loadGraph() {
    try {
        const res = await fetch(`${API_URL}/graph?session_id=${currentSessionId}`);
        const data = await res.json();
        
        console.log("Graph Data:", data);

        const nodes = data.nodes.map(n => ({ id: n.id, name: n.name, group: n.label }));
        const links = data.links.map(l => ({ source: l.source, target: l.target, relationship: l.label }));

        const elem = document.getElementById('3d-graph');
        
        if (!elem.firstChild) { // Only init once
             Graph = ForceGraph3D()
                (elem)
                .backgroundColor('rgba(0,0,0,0)')
                .nodeAutoColorBy('group')
                .nodeThreeObject(node => {
                    const sprite = new SpriteText(node.name);
                    sprite.material.depthWrite = false; // Make text always visible on top
                    sprite.color = '#E8E8E8'; // Default Light color
                    sprite.textHeight = 8;
                    return sprite;
                })
                .linkWidth(link => highlightLinks.has(link) ? 2 : 1)
                .linkDirectionalParticles(link => highlightLinks.has(link) ? 4 : 0)
                .linkDirectionalParticleWidth(2)
                .onNodeHover(node => {
                    if ((!node && !highlightNodes.size) || (node && hoverNode === node)) return;

                    highlightNodes.clear();
                    highlightLinks.clear();
                    
                    if (node) {
                        highlightNodes.add(node);
                        // Find neighbors
                        Graph.graphData().links.forEach(link => {
                            if (link.source.id === node.id || link.target.id === node.id) {
                                highlightLinks.add(link);
                                highlightNodes.add(link.source);
                                highlightNodes.add(link.target);
                            }
                        });
                    }

                    hoverNode = node || null;

                    // Update Node Visuals (Directly modify ThreeJS objects for performance)
                    Graph.graphData().nodes.forEach(n => {
                        const sprite = n.__threeObj;
                        if (sprite) {
                            const isHigh = highlightNodes.has(n);
                            sprite.color = isHigh ? '#FFFF00' : '#E8E8E8'; // Yellow if highlighted
                            sprite.textHeight = isHigh ? 12 : 8; // Grow if highlighted
                        }
                    });

                    // Update Link Visuals (Trigger update)
                    Graph
                        .linkWidth(Graph.linkWidth())
                        .linkDirectionalParticles(Graph.linkDirectionalParticles());
                })
                .enableNodeDrag(true);
        }
        
        Graph.graphData({ nodes, links });
        
    } catch (e) {
        console.error("Graph Error:", e);
    }
}

// --- Expose functions to Global Scope for HTML onclick handlers ---
Object.assign(window, {
    startNewThread,
    saveSessionMetadata,
    loadSessions,
    loadSession,
    clearUIForNewChat,
    clearHistory,
    switchToChatMode,
    submitInitialQuery,
    submitChatQuery,
    appendUserMessage,
    appendAIMessage,
    toggleSources,
    processMessage,
    scrollToBottom,
    escapeHtml,
    updateStats,
    triggerPruning,
    toggleFastFill,
    saveToLocalStorage,
    loadFromLocalStorage,
    toggleGraph,
    refreshGraph,
    loadGraph,
    autoResize,
    autoResize,
    deleteSession,
    openSettings,
    closeSettings,
    saveSettings
});
