const API_URL = "http://127.0.0.1:8000/api";
let currentSessionId = "graph_demo_v1"; 
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

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    // 1. Restore History
    loadFromLocalStorage();
    
    // 2. Fetch Stats
    updateStats();
    
    // 3. Persist Fast Fill setting
    const savedFastFill = localStorage.getItem('fastItems');
    if (savedFastFill === 'true') fastFillToggle.checked = true;
    
    fastFillToggle.addEventListener('change', () => {
        localStorage.setItem('fastItems', fastFillToggle.checked);
    });
    
    // 4. Force Graph Refresh just in case
    setInterval(updateStats, 10000); // Auto-update stats every 10s
});

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
}

function startNewThread() {
    // For demo purposes, we keep same session ID to keep the graph, but clear UI
    if (confirm("Clear chat history? (Graph will remain)")) {
        clearHistory();
    }
}

function clearHistory() {
    chatFeed.innerHTML = '';
    localStorage.removeItem('chatHistory');
    
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
        
        const response = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                message: text, 
                session_id: currentSessionId,
                fast_fill: isFastFill
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
    chatWrapper.scrollTop = chatWrapper.scrollHeight;
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
    }
}

// --- Storage ---
function saveToLocalStorage() {
    localStorage.setItem('chatHistory', chatFeed.innerHTML);
    localStorage.setItem('sessionActive', !heroSection.classList.contains('hidden') ? 'false' : 'true');
}

function loadFromLocalStorage() {
    const history = localStorage.getItem('chatHistory');
    const isActive = localStorage.getItem('sessionActive');
    
    if (history && isActive === 'true') {
        chatFeed.innerHTML = history;
        switchToChatMode();
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

async function loadGraph() {
    try {
        const res = await fetch(`${API_URL}/graph?session_id=${currentSessionId}`);
        const data = await res.json();
        
        // Debug: Check data format
        console.log("Graph Data:", data);

        // 3d-force-graph expects simple objects. 
        // We MUST Ensure IDs match. 
        // Server sends: nodes [{id, name...}], links [{source, target...}]
        // The library creates internal objects, so we should map to clean objects
        const nodes = data.nodes.map(n => ({ id: n.id, name: n.name, group: n.label }));
        const links = data.links.map(l => ({ source: l.source, target: l.target, relationship: l.label }));

        const elem = document.getElementById('3d-graph');
        
        if (!Graph) {
            Graph = ForceGraph3D()
                (elem)
                .backgroundColor('rgba(0,0,0,0)')
                .nodeAutoColorBy('group')
                .nodeLabel(node => `${node.name} (${node.group})`)
                .linkLabel('relationship')
                .linkDirectionalParticles(2)
                .linkDirectionalParticleSpeed(0.005)
                .enableNodeDrag(true);
        }
        
        Graph.graphData({ nodes, links });
        
    } catch (e) {
        console.error("Graph Error:", e);
    }
}
