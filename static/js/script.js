// BPMN Generator JavaScript

// ─────────────────────────────────────────────
// SIDEBAR NAVIGATION
// ─────────────────────────────────────────────

function navigateTo(pageId) {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.page === pageId);
    });
    document.querySelectorAll('.page').forEach(page => {
        page.classList.toggle('active', page.id === 'page-' + pageId);
    });
}

function unlockNavItem(pageId) {
    const navItem = document.querySelector(`.nav-item[data-page="${pageId}"]`);
    if (!navItem) return;
    navItem.classList.remove('locked');
    const lock = navItem.querySelector('.nav-lock');
    if (lock) lock.style.display = 'none';
}

document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
        if (!item.classList.contains('locked')) {
            navigateTo(item.dataset.page);
        }
    });
});

// ─────────────────────────────────────────────
// DOM Elements
const generateBtn = document.getElementById('generate-btn');
const clearBtn = document.getElementById('clear-btn');
const copyBtn = document.getElementById('copy-btn');
const formatBtn = document.getElementById('format-btn');
const downloadBtn = document.getElementById('download-btn');
const singleView = document.getElementById('single-view');
const xmlOutput = document.getElementById('xml-output');
const xmlEditor = document.getElementById('xml-editor');
const diagramContainer = document.getElementById('diagram-container');
const canvas = document.getElementById('canvas');
const loading = document.getElementById('loading');
const errorMessage = document.getElementById('error-message');
const successMessage = document.getElementById('success-message');
const processDescription = document.getElementById('process-description');
const appName = document.getElementById('app-name');
const appIndustry = document.getElementById('app-industry');
const appPurpose = document.getElementById('app-purpose');
const zoomInBtn = document.getElementById('zoom-in-btn');
const zoomOutBtn = document.getElementById('zoom-out-btn');
const zoomResetBtn = document.getElementById('zoom-reset-btn');
const xmlViewBtn = document.getElementById('xml-view-btn');
const diagramViewBtn = document.getElementById('diagram-view-btn');
const viewTitle = document.getElementById('view-title');
const syncStatus = document.getElementById('sync-status');

// Initialize BPMN Modeler
let bpmnModeler = null;
let currentXML = '';
let isUpdatingFromXML = false; // Flag to prevent circular updates
let diagramChangeTimeout = null; // Debounce timer for diagram changes

function initializeBPMNModeler() {
    if (!bpmnModeler) {
        console.log('Creating new BPMN modeler...');
        bpmnModeler = new BpmnJS({
            container: '#canvas',
            keyboard: {
                bindTo: document
            }
        });
        console.log('BPMN modeler created');
    }
    return Promise.resolve();
}

async function importXMLToDiagram(xml) {
    if (!xml || xml.trim() === '') {
        showError('No XML content to display');
        return false;
    }

    try {
        console.log('Initializing modeler...');
        // Initialize modeler if needed
        await initializeBPMNModeler();
        console.log('Modeler initialized, clearing...');

        // Clear any existing diagram
        await bpmnModeler.clear();
        console.log('Modeler cleared, importing XML...');

        // Import the new XML
        await bpmnModeler.importXML(xml);
        console.log('XML imported successfully');

        // Add event listeners for diagram changes
        addDiagramChangeListeners();

        // Fit diagram to viewport
        const canvas = bpmnModeler.get('canvas');
        if (canvas) {
            canvas.zoom('fit-viewport');
            console.log('Canvas zoomed to fit viewport');
        } else {
            console.log('Canvas not available');
        }

        return true;
    } catch (err) {
        console.error('Could not import BPMN diagram:', err);

        // Show detailed error information
        let errorMessage = 'Could not display BPMN diagram. ';
        if (err.message) {
            errorMessage += `Error: ${err.message}`;
        }
        if (err.warnings && err.warnings.length > 0) {
            errorMessage += ` Warnings: ${err.warnings.join(', ')}`;
        }

        // Try to provide helpful feedback based on common issues
        if (err.message && err.message.includes('no diagram to display')) {
            errorMessage += ' The XML may be missing required BPMN elements like startEvent, tasks, or endEvent.';
        } else if (err.message && err.message.includes('unresolved reference')) {
            errorMessage += ' There are unresolved references in BPMN elements.';
        } else if (err.message && err.message.includes('missing')) {
            errorMessage += ' Required BPMN elements are missing from the XML.';
        } else if (err.message && err.message.includes('Cannot read properties')) {
            errorMessage += ' BPMN modeler initialization issue. Please try again.';
        }

        showError(errorMessage);
        return false;
    }
}

function setExample(text) {
    processDescription.value = text;
}

function showError(message) {
    errorMessage.innerHTML = `<div class="error">${message}</div>`;
    successMessage.innerHTML = '';
}

function showSuccess(message) {
    successMessage.innerHTML = `<div class="success">${message}</div>`;
    errorMessage.innerHTML = '';
}

function clearMessages() {
    errorMessage.innerHTML = '';
    successMessage.innerHTML = '';
}

function formatXML(xml) {
    try {
        // Basic XML formatting
        let formatted = xml;
        // Add proper indentation
        formatted = formatted.replace(/></g, '>\n<');
        formatted = formatted.replace(/(\s+)(<)/g, '\n$2');

        const lines = formatted.split('\n');
        let indentLevel = 0;
        const formattedLines = [];

        for (let line of lines) {
            line = line.trim();
            if (!line) continue;

            // Decrease indent for closing tags
            if (line.startsWith('</')) {
                indentLevel = Math.max(0, indentLevel - 1);
            }

            formattedLines.push('  '.repeat(indentLevel) + line);

            // Increase indent for opening tags (but not self-closing)
            if (line.startsWith('<') && !line.startsWith('</') && !line.endsWith('/>')) {
                indentLevel++;
            }
        }

        return formattedLines.join('\n');
    } catch (e) {
        return xml; // Return original if formatting fails
    }
}

function downloadXML(content, filename = 'process.bpmn') {
    const blob = new Blob([content], { type: 'application/xml' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

// Function to show/hide sync status
function showSyncStatus(show = true) {
    if (syncStatus) {
        syncStatus.style.display = show ? 'flex' : 'none';
    }
}

// Function to update sync status text
function updateSyncStatus(text) {
    const syncText = syncStatus?.querySelector('.sync-text');
    if (syncText) {
        syncText.textContent = text;
    }
}

async function updateDiagram(xml) {
    console.log('updateDiagram called with XML length:', xml.length);
    isUpdatingFromXML = true; // Set flag to prevent circular updates
    showSyncStatus(true);
    updateSyncStatus('Updating diagram...');

    const result = await importXMLToDiagram(xml);

    isUpdatingFromXML = false; // Reset flag
    showSyncStatus(false);
    return result;
}

// Function to add event listeners for diagram changes
function addDiagramChangeListeners() {
    if (!bpmnModeler) return;

    // Listen to any changes in the diagram
    const eventBus = bpmnModeler.get('eventBus');

    // Remove existing listeners to prevent duplicates
    eventBus.off('element.changed', handleDiagramChange);
    eventBus.off('shape.added', handleDiagramChange);
    eventBus.off('shape.remove', handleDiagramChange);
    eventBus.off('connection.added', handleDiagramChange);
    eventBus.off('connection.remove', handleDiagramChange);
    eventBus.off('element.layoutChanged', handleDiagramChange);

    // Add new listeners
    eventBus.on('element.changed', handleDiagramChange);
    eventBus.on('shape.added', handleDiagramChange);
    eventBus.on('shape.remove', handleDiagramChange);
    eventBus.on('connection.added', handleDiagramChange);
    eventBus.on('connection.remove', handleDiagramChange);
    eventBus.on('element.layoutChanged', handleDiagramChange);

    console.log('Diagram change listeners added');
}

// Function to handle diagram changes
function handleDiagramChange(event) {
    // Don't update if we're currently updating from XML (prevents circular updates)
    if (isUpdatingFromXML) {
        console.log('Skipping diagram change - updating from XML');
        return;
    }

    // Clear existing timeout
    if (diagramChangeTimeout) {
        clearTimeout(diagramChangeTimeout);
    }

    // Debounce the update to avoid too frequent updates
    diagramChangeTimeout = setTimeout(async () => {
        console.log('Diagram changed, updating XML...');
        await updateXMLFromDiagram();
    }, 500); // Wait 500ms after changes stop
}

// Function to update XML from diagram
async function updateXMLFromDiagram() {
    if (!bpmnModeler || isUpdatingFromXML) return;

    try {
        showSyncStatus(true);
        updateSyncStatus('Syncing to XML...');

        // Get the current XML from the diagram
        const { xml } = await bpmnModeler.saveXML({ format: true });

        if (xml && xml !== currentXML) {
            console.log('Updating XML from diagram...');
            currentXML = xml;

            // Update the XML editor
            const formattedXML = formatXML(xml);
            xmlEditor.value = formattedXML;

            // Save to localStorage
            localStorage.setItem('bpmn_xml_content', formattedXML);

            console.log('XML updated from diagram');
        }

        showSyncStatus(false);
    } catch (err) {
        console.error('Error updating XML from diagram:', err);
        showError('Failed to update XML from diagram changes');
        showSyncStatus(false);
    }
}

// View toggle functions
function showDiagramView() {
    xmlOutput.style.display = 'none';
    diagramContainer.style.display = 'block';
    xmlViewBtn.classList.remove('active');
    diagramViewBtn.classList.add('active');
    viewTitle.textContent = '🎯 BPMN Diagram';
}

function showXMLView() {
    xmlOutput.style.display = 'block';
    diagramContainer.style.display = 'none';
    xmlViewBtn.classList.add('active');
    diagramViewBtn.classList.remove('active');
    viewTitle.textContent = '📝 XML Editor';
}

// Event Listeners
generateBtn.addEventListener('click', async () => {
    const description = processDescription.value.trim();

    if (!description) {
        showError('Please enter a process description');
        return;
    }

    clearMessages();
    loading.classList.add('show');
    generateBtn.disabled = true;
    xmlEditor.value = '';
    xmlOutput.style.display = 'none';
    diagramContainer.style.display = 'none';

    try {
        console.log('Sending request to generate BPMN...');
        const response = await fetch('/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                description,
                app_name: appName.value.trim(),
                app_industry: appIndustry.value.trim(),
                app_purpose: appPurpose.value.trim(),
            })
        });

        console.log('Response received:', response.status);
        const result = await response.json();
        console.log('Result:', result);

        if (result.success) {
            console.log('Success - processing XML...');
            currentXML = result.xml;
            const formattedXML = formatXML(result.xml);
            xmlEditor.value = formattedXML;

            // Show diagram by default
            singleView.style.display = 'flex';
            showDiagramView();
            console.log('Diagram view shown by default');

            // Initialize BPMN modeler and import XML
            console.log('Updating diagram...');
            await updateDiagram(currentXML);
            console.log('Diagram updated');

            showSuccess('BPMN XML generated successfully! You can now edit the XML and see changes in the diagram.');
            // Reset test section state
            testCases = [];
            testTbody.innerHTML = '';
            testTableWrapper.style.display = 'none';
            exportExcelBtn.style.display = 'none';
            testBadge.style.display = 'none';
            // Reset Spring Boot section state
            sbPromptOutput.value = '';
            sbPromptWrapper.style.display = 'none';
            copySbBtn.style.display = 'none';
            // Unlock sidebar nav items and show ready status
            unlockNavItem('tests');
            unlockNavItem('springboot');
            unlockNavItem('react');
            document.getElementById('bpmn-ready-status').style.display = 'flex';
        } else {
            showError(`Error: ${result.error}${result.details ? '<br><small>' + result.details + '</small>' : ''}`);
        }
    } catch (error) {
        console.error('Generation error:', error);
        showError('Failed to generate BPMN. Please try again.');
    } finally {
        console.log('Finally - hiding loading');
        loading.classList.remove('show');
        generateBtn.disabled = false;
    }
});

clearBtn.addEventListener('click', () => {
    processDescription.value = '';
    appName.value = '';
    appIndustry.value = '';
    appPurpose.value = '';
    xmlEditor.value = '';
    currentXML = '';
    singleView.style.display = 'none';
    xmlOutput.style.display = 'none';
    diagramContainer.style.display = 'none';
    clearMessages();

    if (bpmnModeler) {
        try {
            bpmnModeler.clear();
        } catch (e) {
            console.log('Modeler already cleared or not initialized');
        }
    }

    // Reset React section state
    if (document.getElementById('react-prompt-wrapper'))
        document.getElementById('react-prompt-wrapper').style.display = 'none';
    if (document.getElementById('copy-react-btn'))
        document.getElementById('copy-react-btn').style.display = 'none';

    // Re-lock nav items and navigate back to BPMN Generator
    ['tests', 'springboot', 'react'].forEach(pageId => {
        const navItem = document.querySelector(`.nav-item[data-page="${pageId}"]`);
        if (navItem) {
            navItem.classList.add('locked');
            const lock = navItem.querySelector('.nav-lock');
            if (lock) lock.style.display = '';
        }
    });
    document.getElementById('bpmn-ready-status').style.display = 'none';
    navigateTo('bpmn');
});

copyBtn.addEventListener('click', () => {
    const xmlText = xmlEditor.value;

    if (xmlText) {
        navigator.clipboard.writeText(xmlText).then(() => {
            copyBtn.textContent = '✅ Copied!';
            copyBtn.classList.add('success');

            setTimeout(() => {
                copyBtn.textContent = '📋 Copy';
                copyBtn.classList.remove('success');
            }, 2000);
        }).catch(() => {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = xmlText;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);

            copyBtn.textContent = '✅ Copied!';
            copyBtn.classList.add('success');

            setTimeout(() => {
                copyBtn.textContent = '📋 Copy';
                copyBtn.classList.remove('success');
            }, 2000);
        });
    }
});

formatBtn.addEventListener('click', async () => {
    const xmlText = xmlEditor.value;
    if (xmlText) {
        const formatted = formatXML(xmlText);
        xmlEditor.value = formatted;
        currentXML = formatted;

        // Update diagram with formatted XML
        await updateDiagram(currentXML);

        formatBtn.textContent = '✅ Formatted!';
        formatBtn.classList.add('success');

        setTimeout(() => {
            formatBtn.textContent = '🎨 Format';
            formatBtn.classList.remove('success');
        }, 1500);
    }
});

downloadBtn.addEventListener('click', () => {
    const xmlText = xmlEditor.value;
    if (xmlText) {
        const name = appName.value.trim();
        const safeName = name
            ? name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
            : 'bpmn_process';
        const filename = `${safeName}.bpmn`;
        downloadXML(xmlText, filename);

        downloadBtn.textContent = '✅ Downloaded!';
        downloadBtn.classList.add('success');

        setTimeout(() => {
            downloadBtn.textContent = '💾 Download';
            downloadBtn.classList.remove('success');
        }, 1500);
    }
});

// Zoom controls
zoomInBtn.addEventListener('click', () => {
    if (bpmnModeler) {
        const canvas = bpmnModeler.get('canvas');
        if (canvas) {
            canvas.zoom(canvas.zoom() + 0.1);
        }
    }
});

zoomOutBtn.addEventListener('click', () => {
    if (bpmnModeler) {
        const canvas = bpmnModeler.get('canvas');
        if (canvas) {
            canvas.zoom(canvas.zoom() - 0.1);
        }
    }
});

zoomResetBtn.addEventListener('click', () => {
    if (bpmnModeler) {
        const canvas = bpmnModeler.get('canvas');
        if (canvas) {
            canvas.zoom('fit-viewport');
        }
    }
});

// Update diagram when XML is edited
let updateTimeout;
xmlEditor.addEventListener('input', () => {
    clearTimeout(updateTimeout);
    updateTimeout = setTimeout(async () => {
        const newXML = xmlEditor.value;

        // Only update if XML has actually changed and we're not already updating from diagram
        if (newXML !== currentXML && !isUpdatingFromXML) {
            console.log('XML editor changed, updating diagram...');
            currentXML = newXML;
            showSyncStatus(true);
            updateSyncStatus('Updating diagram...');
            await updateDiagram(currentXML);
        }

        localStorage.setItem('bpmn_xml_content', newXML);
    }, 1000); // Wait 1 second after typing stops
});

// Allow Enter key to generate (with Shift+Enter for new line)
processDescription.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        generateBtn.click();
    }
});

// View toggle event listeners
xmlViewBtn.addEventListener('click', showXMLView);
diagramViewBtn.addEventListener('click', showDiagramView);

// Clear saved state on page load so refresh always starts fresh
window.addEventListener('load', () => {
    localStorage.removeItem('bpmn_xml_content');
});


// ─────────────────────────────────────────────
// TEST CASES
// ─────────────────────────────────────────────

const testSection        = document.getElementById('test-section');
const generateTestsBtn   = document.getElementById('generate-tests-btn');
const exportExcelBtn     = document.getElementById('export-excel-btn');
const testLoading        = document.getElementById('test-loading');
const testTableWrapper   = document.getElementById('test-table-wrapper');
const testTbody          = document.getElementById('test-tbody');
const testBadge          = document.getElementById('test-badge');
const testStatsEl        = document.getElementById('test-stats');

let testCases = [];

const SUITE_COLORS = {
    'Happy Path':          '#d4edda',
    'Gateway Branches':    '#cce5ff',
    'Boundary Events':     '#fff3cd',
    'Exception Handling':  '#f8d7da',
    'Negative Tests':      '#e2e3e5',
};

function showTestSection() {
    testSection.style.display = 'block';
    testSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function updateTestStats() {
    const counts = { Pass: 0, Fail: 0, 'Not Run': 0, Blocked: 0 };
    testCases.forEach(tc => {
        const s = tc.status || 'Not Run';
        counts[s] = (counts[s] || 0) + 1;
    });
    testStatsEl.innerHTML = `
        <div class="stat-item stat-total">Total: <strong>${testCases.length}</strong></div>
        <div class="stat-item stat-pass">Pass: <strong>${counts.Pass}</strong></div>
        <div class="stat-item stat-fail">Fail: <strong>${counts.Fail}</strong></div>
        <div class="stat-item stat-notrun">Not Run: <strong>${counts['Not Run']}</strong></div>
        ${counts.Blocked ? `<div class="stat-item stat-blocked">Blocked: <strong>${counts.Blocked}</strong></div>` : ''}
    `;
}

function renderTestTable(cases) {
    testTbody.innerHTML = '';
    cases.forEach((tc, idx) => {
        const tr = document.createElement('tr');
        tr.dataset.idx = idx;
        const suiteColor = SUITE_COLORS[tc.suite] || '#f8f9fa';
        const path = Array.isArray(tc.path) ? tc.path.join(' → ') : (tc.path || '');
        const steps = (tc.steps || '').replace(/\n/g, '<br>');
        const isPos = tc.test_type === 'Positive';
        const status = tc.status || 'Not Run';

        tr.innerHTML = `
            <td class="tc-id">${tc.id || ''}</td>
            <td><span class="suite-badge" style="background:${suiteColor}">${tc.suite || ''}</span></td>
            <td class="tc-name">${tc.name || ''}</td>
            <td><span class="type-badge ${isPos ? 'type-pos' : 'type-neg'}">${tc.test_type || ''}</span></td>
            <td class="tc-wrap">${tc.description || ''}</td>
            <td class="tc-path">${path}</td>
            <td class="tc-wrap">${tc.preconditions || ''}</td>
            <td class="tc-steps">${steps}</td>
            <td class="tc-wrap">${tc.expected_result || ''}</td>
            <td>
                <select class="status-select status-${status.replace(' ','-')}"
                        onchange="updateStatus(${idx}, this.value, this)">
                    <option value="Not Run" ${status === 'Not Run' ? 'selected' : ''}>Not Run</option>
                    <option value="Pass"    ${status === 'Pass'    ? 'selected' : ''}>Pass</option>
                    <option value="Fail"    ${status === 'Fail'    ? 'selected' : ''}>Fail</option>
                    <option value="Blocked" ${status === 'Blocked' ? 'selected' : ''}>Blocked</option>
                </select>
            </td>
            <td><input type="text" class="notes-input" placeholder="Add notes..."
                       value="${(tc.notes || '').replace(/"/g, '&quot;')}"
                       oninput="updateNotes(${idx}, this.value)"></td>
        `;
        testTbody.appendChild(tr);
    });
    updateTestStats();
}

function updateStatus(idx, value, selectEl) {
    testCases[idx].status = value;
    // Re-apply class on the select for colour
    selectEl.className = `status-select status-${value.replace(' ', '-')}`;
    updateTestStats();
}

function updateNotes(idx, value) {
    testCases[idx].notes = value;
}

generateTestsBtn.addEventListener('click', async () => {
    if (!currentXML) {
        showError('Please generate a BPMN diagram first');
        return;
    }

    generateTestsBtn.disabled = true;
    testLoading.style.display = 'block';
    testTableWrapper.style.display = 'none';
    exportExcelBtn.style.display = 'none';
    testBadge.style.display = 'none';

    try {
        const response = await fetch('/generate-tests', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ xml: currentXML }),
        });
        const result = await response.json();

        if (result.success) {
            testCases = result.test_cases.map(tc => ({ ...tc, status: 'Not Run', notes: '' }));
            renderTestTable(testCases);
            testBadge.textContent = testCases.length;
            testBadge.style.display = 'inline-block';
            testTableWrapper.style.display = 'block';
            exportExcelBtn.style.display = 'inline-flex';
            // Update sidebar badge count
            const navTestBadge = document.getElementById('nav-test-badge');
            if (navTestBadge) {
                navTestBadge.textContent = testCases.length;
                navTestBadge.style.display = 'inline-block';
            }
        } else {
            showError(`Test generation failed: ${result.error}`);
        }
    } catch (err) {
        showError('Failed to generate test cases. Please try again.');
    } finally {
        testLoading.style.display = 'none';
        generateTestsBtn.disabled = false;
    }
});

// ─────────────────────────────────────────────
// SPRING BOOT PROMPT GENERATOR
// ─────────────────────────────────────────────

const springbootSection  = document.getElementById('springboot-section');
const generateSbBtn      = document.getElementById('generate-sb-btn');
const copySbBtn          = document.getElementById('copy-sb-btn');
const sbLoading          = document.getElementById('sb-loading');
const sbPromptWrapper    = document.getElementById('sb-prompt-wrapper');
const sbPromptOutput     = document.getElementById('sb-prompt-output');
const sbPromptRaw        = document.getElementById('sb-prompt-raw');
const sbCharCount        = document.getElementById('sb-char-count');

generateSbBtn.addEventListener('click', async () => {
    if (!currentXML) {
        showError('Please generate a BPMN diagram first');
        return;
    }

    generateSbBtn.disabled = true;
    sbLoading.style.display = 'block';
    sbPromptWrapper.style.display = 'none';
    copySbBtn.style.display = 'none';

    try {
        const response = await fetch('/generate-springboot-prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ xml: currentXML }),
        });
        const result = await response.json();

        if (result.success) {
            sbPromptRaw.value = result.prompt;
            sbPromptOutput.innerHTML = marked.parse(result.prompt);
            sbCharCount.textContent = `${result.prompt.length.toLocaleString()} characters`;
            sbPromptWrapper.style.display = 'block';
            copySbBtn.style.display = 'inline-flex';
            sbPromptWrapper.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else {
            showError(`Prompt generation failed: ${result.error}`);
        }
    } catch (err) {
        showError('Failed to generate Spring Boot prompt. Please try again.');
    } finally {
        sbLoading.style.display = 'none';
        generateSbBtn.disabled = false;
    }
});

copySbBtn.addEventListener('click', () => {
    const text = sbPromptRaw.value;
    if (!text) return;

    navigator.clipboard.writeText(text).then(() => {
        copySbBtn.innerHTML = '<span>✅</span> Copied!';
        setTimeout(() => {
            copySbBtn.innerHTML = '<span>📋</span> Copy Prompt';
        }, 2000);
    }).catch(() => {
        // fallback
        sbPromptRaw.select();
        document.execCommand('copy');
        copySbBtn.innerHTML = '<span>✅</span> Copied!';
        setTimeout(() => {
            copySbBtn.innerHTML = '<span>📋</span> Copy Prompt';
        }, 2000);
    });
});

exportExcelBtn.addEventListener('click', async () => {
    if (!testCases.length) return;

    exportExcelBtn.disabled = true;
    exportExcelBtn.innerHTML = '<span>⏳</span> Exporting...';

    try {
        const response = await fetch('/export-tests', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                test_cases: testCases,
                process_name: processDescription.value.trim().slice(0, 100) || 'BPMN Process',
            }),
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({ error: 'Export failed' }));
            showError(err.error || 'Export failed');
            return;
        }

        const blob = await response.blob();
        const url  = window.URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href     = url;
        a.download = `test_cases_${new Date().toISOString().slice(0, 10)}.xlsx`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        exportExcelBtn.innerHTML = '<span>✅</span> Exported!';
        setTimeout(() => {
            exportExcelBtn.innerHTML = '<span>📊</span> Export to Excel';
            exportExcelBtn.disabled = false;
        }, 2000);
    } catch (err) {
        showError('Export failed. Please try again.');
        exportExcelBtn.innerHTML = '<span>📊</span> Export to Excel';
        exportExcelBtn.disabled = false;
    }
});

// ─────────────────────────────────────────────
// REACT FRONTEND PROMPT GENERATOR
// ─────────────────────────────────────────────

const generateReactBtn   = document.getElementById('generate-react-btn');
const copyReactBtn       = document.getElementById('copy-react-btn');
const reactLoading       = document.getElementById('react-loading');
const reactPromptWrapper = document.getElementById('react-prompt-wrapper');
const reactPromptOutput  = document.getElementById('react-prompt-output');
const reactPromptRaw     = document.getElementById('react-prompt-raw');
const reactCharCount     = document.getElementById('react-char-count');

generateReactBtn.addEventListener('click', async () => {
    if (!currentXML) {
        showError('Please generate a BPMN diagram first');
        return;
    }

    generateReactBtn.disabled = true;
    reactLoading.style.display = 'block';
    reactPromptWrapper.style.display = 'none';
    copyReactBtn.style.display = 'none';

    try {
        const response = await fetch('/generate-react-prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ xml: currentXML }),
        });
        const result = await response.json();

        if (result.success) {
            reactPromptRaw.value = result.prompt;
            reactPromptOutput.innerHTML = marked.parse(result.prompt);
            reactCharCount.textContent = `${result.prompt.length.toLocaleString()} characters`;
            reactPromptWrapper.style.display = 'block';
            copyReactBtn.style.display = 'inline-flex';
            reactPromptWrapper.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else {
            showError(`React prompt generation failed: ${result.error}`);
        }
    } catch (err) {
        showError('Failed to generate React prompt. Please try again.');
    } finally {
        reactLoading.style.display = 'none';
        generateReactBtn.disabled = false;
    }
});

copyReactBtn.addEventListener('click', () => {
    const text = reactPromptRaw.value;
    if (!text) return;

    navigator.clipboard.writeText(text).then(() => {
        copyReactBtn.innerHTML = '<span>✅</span> Copied!';
        setTimeout(() => {
            copyReactBtn.innerHTML = '<span>📋</span> Copy Prompt';
        }, 2000);
    }).catch(() => {
        reactPromptRaw.select();
        document.execCommand('copy');
        copyReactBtn.innerHTML = '<span>✅</span> Copied!';
        setTimeout(() => {
            copyReactBtn.innerHTML = '<span>📋</span> Copy Prompt';
        }, 2000);
    });
});
