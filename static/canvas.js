
document.addEventListener('DOMContentLoaded', () => {
    const docId = document.getElementById('doc-id').textContent;

    // UI Elements
    const selectionInfo = document.getElementById('selection-info');
    const editForm = document.getElementById('edit-form');
    const textEditor = document.getElementById('text-editor');
    const saveBtn = document.getElementById('save-btn');
    const saveStatus = document.getElementById('save-status');
    const originalTextSpan = document.getElementById('original-text');
    const wordPageSpan = document.getElementById('word-page');
    const wordPositionSpan = document.getElementById('word-position');
    const rawTextDisplay = document.getElementById('raw-text-display');
    const wordCountSpan = document.getElementById('word-count');
    const avgConfidenceSpan = document.getElementById('avg-confidence');
    const pageIndicator = document.getElementById('page-indicator');
    const zoomLevel = document.getElementById('zoom-level');
    const pagesContainer = document.getElementById('pages-container');

    // State variables
    let ocrData = null;
    let rawOcrData = null;
    let pages = [];
    let selectedWord = null;
    let hoveredWord = null;
    let tooltip = null;
    let currentZoom = 1.0;

    // --- History for Undo/Redo ---
    let history = [];
    let historyIndex = -1;

    // --- Initialize Application ---
    async function initializeApp() {
        try {
            console.log("Loading document data...");
            
            // Load OCR data and raw OCR data in parallel
            const [ocrResponse, rawOcrResponse] = await Promise.all([
                fetch(`/data/document/${docId}`),
                fetch(`/raw_ocr/${docId}`).catch(e => {
                    console.warn("Raw OCR data not available:", e);
                    return { ok: false };
                })
            ]);

            if (!ocrResponse.ok) {
                throw new Error(`Failed to load OCR data: ${ocrResponse.status}`);
            }

            const ocrResult = await ocrResponse.json();
            if (ocrResult.error) {
                throw new Error(ocrResult.error);
            }

            ocrData = ocrResult.ocrData;
            console.log("OCR data loaded:", ocrData);

            // Load raw OCR data if available
            if (rawOcrResponse.ok) {
                rawOcrData = await rawOcrResponse.json();
                console.log("Raw OCR data loaded:", rawOcrData);
            } else {
                console.warn("Raw OCR data not found, using fallback");
                rawOcrData = null;
            }

            // Initialize the multi-page viewer
            await initializeMultiPageViewer(ocrResult.imageUrl);
            
            // Initialize other components
            displayRawText();
            updateTextStats();
            initializeTooltip();
            initializeZoomControls();

        } catch (error) {
            console.error('Error initializing app:', error);
            pagesContainer.innerHTML = `<p style="color: red;">Failed to load document data: ${error.message}</p>`;
        }
    }

    // Start initialization
    initializeApp();

    // --- Multi-Page Viewer Functions ---
    async function initializeMultiPageViewer(baseImageUrl) {
        if (!ocrData || !ocrData.pages) {
            throw new Error("No OCR pages data available");
        }

        console.log(`Initializing ${ocrData.pages.length} pages...`);
        
        // Clear existing pages
        pagesContainer.innerHTML = '';
        pages = [];

        // Create pages
        for (let pageIndex = 0; pageIndex < ocrData.pages.length; pageIndex++) {
            await createPageViewer(pageIndex, baseImageUrl);
        }

        updatePageIndicator();
        console.log(`Multi-page viewer initialized with ${pages.length} pages`);
    }

    async function createPageViewer(pageIndex, baseImageUrl) {
        const pageData = ocrData.pages[pageIndex];
        
        // Create page container
        const pageContainer = document.createElement('div');
        pageContainer.className = 'page-container';
        pageContainer.dataset.page = pageIndex;

        // Create page header
        const pageHeader = document.createElement('div');
        pageHeader.className = 'page-header';
        pageHeader.textContent = `Page ${pageIndex + 1}`;

        // Create canvas container
        const canvasContainer = document.createElement('div');
        canvasContainer.className = 'page-canvas-container';

        // Create canvas
        const canvas = document.createElement('canvas');
        canvas.className = 'page-canvas';
        canvas.dataset.page = pageIndex;

        // Load page image - try specific page first, fallback to page 0
        const pageImage = new Image();
        const specificImageUrl = baseImageUrl.replace('_page_0.png', `_page_${pageIndex}.png`);
        const fallbackImageUrl = baseImageUrl; // Always _page_0.png
        
        return new Promise((resolve, reject) => {
            const tryLoadImage = (imageUrl, isFallback = false) => {
                pageImage.onload = () => {
                    try {
                        // Set canvas dimensions
                        const maxWidth = 800;
                        const scale = Math.min(maxWidth / pageImage.width, 1.0) * currentZoom;
                        canvas.width = pageImage.width * scale;
                        canvas.height = pageImage.height * scale;

                        // Draw image and bounding boxes
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(pageImage, 0, 0, canvas.width, canvas.height);
                        
                        // Extract and draw words for this page
                        const pageWords = extractWordsFromPage(pageData, pageIndex);
                        drawBoundingBoxes(ctx, pageWords, canvas.width, canvas.height);

                        // Add event listeners
                        addCanvasEventListeners(canvas, pageWords, pageIndex);

                        // Store page data
                        pages.push({
                            index: pageIndex,
                            canvas: canvas,
                            context: ctx,
                            image: pageImage,
                            words: pageWords,
                            scale: scale,
                            usingFallbackImage: isFallback
                        });

                        // Assemble page
                        canvasContainer.appendChild(canvas);
                        pageContainer.appendChild(pageHeader);
                        pageContainer.appendChild(canvasContainer);
                        pagesContainer.appendChild(pageContainer);

                        if (isFallback && pageIndex > 0) {
                            console.log(`Page ${pageIndex + 1} using fallback image (page 0) with ${pageWords.length} words`);
                            // Add visual indicator for fallback
                            pageHeader.innerHTML = `Page ${pageIndex + 1} <span class="fallback-indicator">(using page 1 image)</span>`;
                            pageHeader.classList.add('fallback-page');
                        } else {
                            console.log(`Page ${pageIndex + 1} loaded with ${pageWords.length} words`);
                        }
                        resolve();
                    } catch (error) {
                        console.error(`Error creating page ${pageIndex}:`, error);
                        reject(error);
                    }
                };

                pageImage.onerror = () => {
                    if (!isFallback && pageIndex > 0) {
                        // Try fallback to page 0 image
                        console.log(`Page ${pageIndex + 1} image not found, using fallback image`);
                        tryLoadImage(fallbackImageUrl, true);
                    } else {
                        console.error(`Failed to load image for page ${pageIndex}: ${imageUrl}`);
                        reject(new Error(`Failed to load page image: ${imageUrl}`));
                    }
                };

                pageImage.src = imageUrl;
            };

            // Start with specific page image
            tryLoadImage(specificImageUrl);
        });
    }

    function extractWordsFromPage(pageData, pageIndex) {
        const words = [];
        let wordCounter = 0;

        pageData.blocks.forEach(block => {
            block.lines.forEach(line => {
                line.words.forEach(word => {
                    words.push({
                        ...word,
                        id: `p${pageIndex}_w${wordCounter++}`,
                        pageIndex: pageIndex,
                        originalValue: word.value
                    });
                });
            });
        });

        return words;
    }

    function drawBoundingBoxes(ctx, words, canvasWidth, canvasHeight) {
        words.forEach(word => {
            if (!word.geometry || !word.geometry[0]) return;
            
            const [x1, y1, x2, y2] = word.geometry[0];
            const canvasX = x1 * canvasWidth;
            const canvasY = y1 * canvasHeight;
            const width = (x2 - x1) * canvasWidth;
            const height = (y2 - y1) * canvasHeight;

            // Skip invalid boxes
            if (width <= 0 || height <= 0) return;

            ctx.strokeStyle = 'rgba(255, 0, 0, 0.7)';
            ctx.lineWidth = 1;
            
            if (word === selectedWord) {
                ctx.strokeStyle = 'rgba(0, 255, 0, 1)';
                ctx.lineWidth = 2;
            }
            
            ctx.strokeRect(canvasX, canvasY, width, height);
        });
    }

    // --- Canvas Event Handlers ---
    function addCanvasEventListeners(canvas, pageWords, pageIndex) {
        // Click handler
        canvas.addEventListener('click', (e) => {
            const rect = canvas.getBoundingClientRect();
            const clickX = (e.clientX - rect.left) / canvas.width;  // Normalize to [0,1]
            const clickY = (e.clientY - rect.top) / canvas.height;   // Normalize to [0,1]

            console.log(`Click on page ${pageIndex + 1} at: (${clickX.toFixed(3)}, ${clickY.toFixed(3)})`);
            
            const clickedWord = findWordAt(clickX, clickY, pageWords);
            if (clickedWord) {
                selectWord(clickedWord, pageIndex);
                redrawPage(pageIndex);
            } else {
                console.log(`No word found at click position on page ${pageIndex + 1}`);
                console.log(`Available words on page ${pageIndex + 1}:`, pageWords.length);
                // Show nearby words for debugging
                showNearbyWords(clickX, clickY, pageWords, pageIndex);
            }
        });

        // Hover handlers
        canvas.addEventListener('mousemove', (e) => {
            const rect = canvas.getBoundingClientRect();
            const mouseX = (e.clientX - rect.left) / canvas.width;  // Normalize to [0,1]
            const mouseY = (e.clientY - rect.top) / canvas.height;   // Normalize to [0,1]
            
            const wordAtMouse = findWordAt(mouseX, mouseY, pageWords);
            
            if (wordAtMouse && wordAtMouse !== hoveredWord) {
                // New word hovered
                hoveredWord = wordAtMouse;
                showTooltip(e.clientX, e.clientY, wordAtMouse);
            } else if (!wordAtMouse && hoveredWord) {
                // No word under mouse, hide tooltip
                hoveredWord = null;
                hideTooltip();
            } else if (wordAtMouse === hoveredWord && tooltip) {
                // Same word, just update tooltip position
                updateTooltipPosition(e.clientX, e.clientY);
            }
        });

        canvas.addEventListener('mouseleave', () => {
            hoveredWord = null;
            hideTooltip();
        });
    }

    // --- Helper Functions ---
    function findWordAt(relX, relY, pageWords) {
        // Add tolerance for easier clicking
        const tolerance = 0.01; // 1% tolerance
        
        // Find the word at the click position (check from last to first for overlapping)
        for (let i = pageWords.length - 1; i >= 0; i--) {
            const word = pageWords[i];
            if (!word.geometry || !word.geometry[0]) continue;
            
            const [x1, y1, x2, y2] = word.geometry[0];
            
            // Expand hit area with tolerance
            const expandedX1 = x1 - tolerance;
            const expandedY1 = y1 - tolerance;
            const expandedX2 = x2 + tolerance;
            const expandedY2 = y2 + tolerance;
            
            if (relX >= expandedX1 && relX <= expandedX2 && relY >= expandedY1 && relY <= expandedY2) {
                return word;
            }
        }
        return null;
    }

    function selectWord(word, pageIndex) {
        console.log("Selected word:", word);
        selectedWord = word;
        selectionInfo.classList.add('hidden');
        editForm.classList.remove('hidden');
        
        // Update form fields
        textEditor.value = word.value;
        if (originalTextSpan) originalTextSpan.textContent = word.value;
        if (wordPageSpan) wordPageSpan.textContent = `Page ${pageIndex + 1}`;
        if (wordPositionSpan) {
            const bbox = word.geometry[0];
            wordPositionSpan.textContent = `(${bbox[0].toFixed(3)}, ${bbox[1].toFixed(3)}) to (${bbox[2].toFixed(3)}, ${bbox[3].toFixed(3)})`;
        }
        
        textEditor.focus();
    }

    function redrawPage(pageIndex) {
        const page = pages.find(p => p.index === pageIndex);
        if (!page) return;

        const ctx = page.context;
        const canvas = page.canvas;
        
        // Clear and redraw
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(page.image, 0, 0, canvas.width, canvas.height);
        drawBoundingBoxes(ctx, page.words, canvas.width, canvas.height);
    }

    function showNearbyWords(clickX, clickY, pageWords, pageIndex) {
        console.log(`Nearby words on page ${pageIndex + 1}:`);
        
        const nearbyWords = pageWords.filter(word => {
            if (!word.geometry || !word.geometry[0]) return false;
            
            const [x1, y1, x2, y2] = word.geometry[0];
            const centerX = (x1 + x2) / 2;
            const centerY = (y1 + y2) / 2;
            const distance = Math.sqrt(
                Math.pow(clickX - centerX, 2) + 
                Math.pow(clickY - centerY, 2)
            );
            return distance < 0.1; // Within 10% of document size
        });

        if (nearbyWords.length === 0) {
            console.log("  No words found nearby");
        } else {
            nearbyWords.forEach((word, index) => {
                const bbox = word.geometry[0];
                const distance = Math.sqrt(
                    Math.pow(clickX - (bbox[0] + bbox[2]) / 2, 2) + 
                    Math.pow(clickY - (bbox[1] + bbox[3]) / 2, 2)
                );
                console.log(`  ${index}: "${word.value}" at (${bbox[0].toFixed(3)}, ${bbox[1].toFixed(3)}) distance: ${distance.toFixed(3)}`);
            });
        }
    }

    // --- Save Correction Handler ---
    saveBtn.addEventListener('click', () => {
        if (!selectedWord) return;

        const newText = textEditor.value;
        if (newText === selectedWord.value) return; // No change

        const oldText = selectedWord.value;
        updateWord(selectedWord.id, { value: newText });
        addToHistory({ wordId: selectedWord.id, oldText, newText });

        // --- Send correction to backend ---
        const formData = new FormData();
        formData.append('doc_id', docId);
        formData.append('page', selectedWord.pageIndex || 0);
        formData.append('word_id', selectedWord.id);
        formData.append('corrected_text', newText);
        formData.append('corrected_bbox', JSON.stringify(selectedWord.geometry)); 

        saveStatus.textContent = 'Saving...';
        fetch('/save_correction', { method: 'POST', body: formData })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    saveStatus.textContent = 'Saved!';
                } else {
                    saveStatus.textContent = `Error: ${data.message}`;
                }
                setTimeout(() => saveStatus.textContent = '', 2000);
            })
            .catch(err => {
                saveStatus.textContent = 'Save failed.';
                console.error('Save error:', err);
            });
    });

    // --- Undo/Redo Logic ---
    function addToHistory(action) {
        // Clear redo history
        if (historyIndex < history.length - 1) {
            history = history.slice(0, historyIndex + 1);
        }
        history.push(action);
        historyIndex++;
    }

    function updateWord(wordId, updates) {
        // Find word across all pages
        for (const page of pages) {
            const word = page.words.find(w => w.id === wordId);
            if (word) {
                Object.assign(word, updates);
                if (word === selectedWord) {
                    textEditor.value = word.value;
                }
                redrawPage(page.index);
                break;
            }
        }
    }

    document.getElementById('undo-btn').addEventListener('click', () => {
        if (historyIndex < 0) return; // No history
        const lastAction = history[historyIndex];
        updateWord(lastAction.wordId, { value: lastAction.oldText });
        historyIndex--;
    });

    document.getElementById('redo-btn').addEventListener('click', () => {
        if (historyIndex >= history.length - 1) return; // At the end
        historyIndex++;
        const nextAction = history[historyIndex];
        updateWord(nextAction.wordId, { value: nextAction.newText });
    });

    // --- Tab System ---
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const targetTab = e.target.dataset.tab;
            switchTab(targetTab);
        });
    });

    function switchTab(tabName) {
        // Update tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

        // Update tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById(`${tabName}-tab`).classList.add('active');
    }

    // --- Raw Text Display ---
    function displayRawText() {
        if (!ocrData || !rawTextDisplay) return;
        
        let fullText = '';
        let lineNumber = 1;
        
        ocrData.pages.forEach((page, pageIndex) => {
            if (pageIndex > 0) fullText += `\n--- PAGE ${pageIndex + 1} ---\n`;
            
            page.blocks.forEach((block, blockIndex) => {
                block.lines.forEach((line, lineIndex) => {
                    const lineText = line.words.map(word => word.value).join(' ');
                    if (lineText.trim()) {
                        fullText += `${lineNumber.toString().padStart(3, ' ')}: ${lineText}\n`;
                        lineNumber++;
                    }
                });
                fullText += '\n'; // Add space between blocks
            });
        });
        
        rawTextDisplay.value = fullText.trim();
    }

    function updateTextStats() {
        if (!ocrData || !wordCountSpan || !avgConfidenceSpan) return;
        
        let totalWords = 0;
        let totalConfidence = 0;
        let wordCount = 0;
        
        ocrData.pages.forEach(page => {
            page.blocks.forEach(block => {
                block.lines.forEach(line => {
                    line.words.forEach(word => {
                        totalWords++;
                        if (word.confidence) {
                            totalConfidence += word.confidence;
                            wordCount++;
                        }
                    });
                });
            });
        });
        
        wordCountSpan.textContent = totalWords;
        avgConfidenceSpan.textContent = wordCount > 0 
            ? `${(totalConfidence / wordCount * 100).toFixed(1)}%` 
            : 'N/A';
    }

    // --- Debug Helpers ---
    function showClickDebug(clickX, clickY) {
        // Remove existing debug info
        const existingDebug = document.querySelector('.canvas-debug');
        if (existingDebug) existingDebug.remove();
        
        // Add debug info
        const debugDiv = document.createElement('div');
        debugDiv.className = 'canvas-debug';
        debugDiv.innerHTML = `Click: (${clickX.toFixed(3)}, ${clickY.toFixed(3)})`;
        
        const canvasContainer = document.getElementById('canvas-container');
        canvasContainer.style.position = 'relative';
        canvasContainer.appendChild(debugDiv);
        
        // Remove after 3 seconds
        setTimeout(() => {
            if (debugDiv.parentNode) debugDiv.remove();
        }, 3000);
        
        // Also log nearby words for debugging
        console.log('Nearby words:');
        words.forEach((word, index) => {
            const bbox = word.geometry[0];
            const distance = Math.sqrt(
                Math.pow(clickX - (bbox[0] + bbox[2]) / 2, 2) + 
                Math.pow(clickY - (bbox[1] + bbox[3]) / 2, 2)
            );
            if (distance < 0.1) { // Within 10% of document size
                console.log(`  ${index}: "${word.value}" at (${bbox[0].toFixed(3)}, ${bbox[1].toFixed(3)}) distance: ${distance.toFixed(3)}`);
            }
        });
    }

    // --- Tooltip Functions ---
    function initializeTooltip() {
        // Create tooltip element if it doesn't exist
        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.className = 'canvas-tooltip';
            document.body.appendChild(tooltip);
        }
    }

    function showTooltip(clientX, clientY, word) {
        if (!tooltip) return;
        
        // Get confidence level for styling
        const confidence = word.confidence || 0;
        let confidenceClass = 'confidence-low';
        let confidenceText = 'Low';
        
        if (confidence >= 0.8) {
            confidenceClass = 'confidence-high';
            confidenceText = 'High';
        } else if (confidence >= 0.5) {
            confidenceClass = 'confidence-medium';
            confidenceText = 'Medium';
        }
        
        // Format bounding box coordinates
        const bbox = word.geometry[0];
        const bboxText = `(${bbox[0].toFixed(3)}, ${bbox[1].toFixed(3)}) → (${bbox[2].toFixed(3)}, ${bbox[3].toFixed(3)})`;
        
        // Create tooltip content
        tooltip.innerHTML = `
            <div class="tooltip-text">"${word.value}"</div>
            <div class="tooltip-confidence ${confidenceClass}">
                Confidence: ${confidenceText} (${(confidence * 100).toFixed(1)}%)
            </div>
            <div class="tooltip-position">
                ${bboxText}
            </div>
        `;
        
        // Position tooltip
        updateTooltipPosition(clientX, clientY);
        
        // Show tooltip
        tooltip.classList.add('visible');
    }

    function hideTooltip() {
        if (tooltip) {
            tooltip.classList.remove('visible');
        }
    }

    function updateTooltipPosition(clientX, clientY) {
        if (!tooltip) return;
        
        const tooltipRect = tooltip.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        
        let left = clientX + 15; // Offset from cursor
        let top = clientY - 10;
        
        // Prevent tooltip from going off-screen horizontally
        if (left + tooltipRect.width > viewportWidth) {
            left = clientX - tooltipRect.width - 15;
        }
        
        // Prevent tooltip from going off-screen vertically
        if (top + tooltipRect.height > viewportHeight) {
            top = clientY - tooltipRect.height - 15;
        }
        
        // Ensure tooltip doesn't go above viewport
        if (top < 0) {
            top = clientY + 25;
        }
        
        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
    }

    // --- Zoom Controls ---
    function initializeZoomControls() {
        document.getElementById('zoom-in-btn').addEventListener('click', () => {
            currentZoom = Math.min(currentZoom * 1.2, 3.0);
            updateZoom();
        });

        document.getElementById('zoom-out-btn').addEventListener('click', () => {
            currentZoom = Math.max(currentZoom / 1.2, 0.3);
            updateZoom();
        });
    }

    function updateZoom() {
        zoomLevel.textContent = `${Math.round(currentZoom * 100)}%`;
        
        // Recreate all pages with new zoom
        if (ocrData) {
            const baseImageUrl = pages.length > 0 ? pages[0].image.src : null;
            if (baseImageUrl) {
                initializeMultiPageViewer(baseImageUrl);
            }
        }
    }

    function updatePageIndicator() {
        if (pages.length > 0) {
            pageIndicator.textContent = `${pages.length} page${pages.length > 1 ? 's' : ''}`;
        } else {
            pageIndicator.textContent = 'Loading...';
        }
    }
});
