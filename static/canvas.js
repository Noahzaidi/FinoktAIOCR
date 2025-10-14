
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
    const pagesList = document.getElementById('pages-list');
    const leftPanel = document.getElementById('left-panel');
    const rightPanel = document.getElementById('right-panel');
    const resizer = document.getElementById('panel-resizer');

    // State variables
    let ocrData = null;
    let rawOcrData = null;
    let pages = [];
    let selectedWord = null;
    let hoveredWord = null;
    let tooltip = null;
    let currentZoom = 1.0; // Global zoom for ALL pages
    let isResizing = false;
    let startX = 0;
    let startLeftWidth = 0;
    let currentPageIndex = 0;
    let pageScrollPositions = {}; // Store scroll positions for each page

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
            await initializeMultiPageViewer(ocrResult.imageUrl, 0);
            
            // Initialize other components
            displayRawText();
            updateTextStats();
            initializeTooltip();
            initializeZoomControls();
            loadDocumentClassification();
            initializeResizer();
            populatePagesList();

        } catch (error) {
            console.error('Error initializing app:', error);
            pagesContainer.innerHTML = `<p style="color: red;">Failed to load document data: ${error.message}</p>`;
        }
    }
    // --- Panel Resizer ---
    function initializeResizer() {
        if (!resizer || !leftPanel || !rightPanel) return;

        // Load saved width if exists
        const savedWidth = localStorage.getItem('leftPanelWidthPx');
        if (savedWidth) {
            applyLeftPanelWidth(parseInt(savedWidth, 10));
        }

        const minWidth = 320; // keep left panel usable
        const maxWidth = Math.min(window.innerWidth * 0.7, 900);

        const onMouseMove = (e) => {
            if (!isResizing) return;
            const delta = e.clientX - startX;
            let newWidth = Math.max(minWidth, Math.min(startLeftWidth + delta, maxWidth));
            applyLeftPanelWidth(newWidth);
        };

        const onMouseUp = () => {
            if (!isResizing) return;
            isResizing = false;
            document.body.classList.remove('resizing');
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
            // Persist
            const width = parseInt(getComputedStyle(leftPanel).width, 10);
            localStorage.setItem('leftPanelWidthPx', String(width));
        };

        const startResize = (clientX) => {
            isResizing = true;
            document.body.classList.add('resizing');
            startX = clientX;
            startLeftWidth = parseInt(getComputedStyle(leftPanel).width, 10);
            window.addEventListener('mousemove', onMouseMove);
            window.addEventListener('mouseup', onMouseUp);
        };

        resizer.addEventListener('mousedown', (e) => startResize(e.clientX));

        // Keyboard accessibility: arrow keys to resize when resizer focused
        resizer.addEventListener('keydown', (e) => {
            const step = e.shiftKey ? 40 : 10;
            if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
                e.preventDefault();
                const currentWidth = parseInt(getComputedStyle(leftPanel).width, 10);
                let newWidth = e.key === 'ArrowLeft' ? currentWidth - step : currentWidth + step;
                const clamped = Math.max(minWidth, Math.min(newWidth, maxWidth));
                applyLeftPanelWidth(clamped);
                localStorage.setItem('leftPanelWidthPx', String(clamped));
            }
        });

        // Touch support
        resizer.addEventListener('touchstart', (e) => {
            const touch = e.touches[0];
            startResize(touch.clientX);
        }, { passive: true });
        window.addEventListener('touchmove', (e) => {
            if (!isResizing) return;
            const touch = e.touches[0];
            const delta = touch.clientX - startX;
            let newWidth = Math.max(minWidth, Math.min(startLeftWidth + delta, maxWidth));
            applyLeftPanelWidth(newWidth);
        }, { passive: true });
        window.addEventListener('touchend', onMouseUp, { passive: true });
        window.addEventListener('touchcancel', onMouseUp, { passive: true });

        // Re-clamp on window resize
        window.addEventListener('resize', () => {
            const currentWidth = parseInt(getComputedStyle(leftPanel).width, 10);
            const clamped = Math.max(minWidth, Math.min(currentWidth, Math.min(window.innerWidth * 0.7, 900)));
            applyLeftPanelWidth(clamped);
        });
    }

    function applyLeftPanelWidth(px) {
        leftPanel.style.flex = `0 0 ${px}px`;
        leftPanel.style.minWidth = `${px}px`;
        leftPanel.style.maxWidth = `${px}px`;
    }

    // Start initialization
    initializeApp();
    
    // Initialize learning tab
    initializeLearningTab();

    // --- Multi-Page Viewer Functions ---
    async function initializeMultiPageViewer(baseImageUrl, targetPageIndex = null) {
        if (!ocrData || !ocrData.pages) {
            throw new Error("No OCR pages data available");
        }

        console.log(`Initializing ${ocrData.pages.length} pages...`);

        // Clear existing pages only if this is the initial load
        if (pages.length === 0) {
            pagesContainer.innerHTML = '';
            pages = [];

            // Create pages
            for (let pageIndex = 0; pageIndex < ocrData.pages.length; pageIndex++) {
                await createPageViewer(pageIndex, baseImageUrl);
            }
        }

        updatePageIndicator();

        // Scroll to target page after initialization if specified
        if (targetPageIndex !== null && targetPageIndex >= 0 && targetPageIndex < pages.length) {
            setTimeout(() => {
                scrollToPage(targetPageIndex);

                // Restore scroll position within the page if available
                const viewer = document.getElementById('document-viewer-container');
                const savedScrollTop = pageScrollPositions[targetPageIndex];
                if (savedScrollTop && viewer) {
                    setTimeout(() => {
                        viewer.scrollTop = savedScrollTop;
                    }, 200); // Additional delay for page rendering
                }
            }, 100); // Small delay to ensure pages are rendered
        }

        console.log(`Multi-page viewer initialized with ${pages.length} pages`);
    }

    async function createPageViewer(pageIndex, baseImageUrl) {
        const pageData = ocrData.pages[pageIndex];
        
        // Create page container
        const pageContainer = document.createElement('div');
        pageContainer.className = 'page-container';
        pageContainer.dataset.page = pageIndex;
        pageContainer.id = `page-container-${pageIndex}`;

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
                        // Set canvas dimensions using global zoom
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
                            // Add visual indicator for fallback
                            pageHeader.innerHTML = `Page ${pageIndex + 1} <span class="fallback-indicator">(using page 1 image)</span>`;
                            pageHeader.classList.add('fallback-page');
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
    // --- Pages list / navigation ---
    function populatePagesList() {
        if (!pagesList || !ocrData || !ocrData.pages) return;
        pagesList.innerHTML = '';
        for (let i = 0; i < ocrData.pages.length; i++) {
            const btn = document.createElement('button');
            btn.className = 'page-jump-btn';
            btn.type = 'button';
            btn.dataset.pageIndex = i;
            btn.textContent = `Page ${i + 1}`;
            btn.addEventListener('click', () => scrollToPage(i));
            pagesList.appendChild(btn);
        }
        
        // Set up scroll listener to highlight active page
        const viewer = document.getElementById('document-viewer-container');
        if (viewer) {
            let scrollTimeout;
            viewer.addEventListener('scroll', () => {
                clearTimeout(scrollTimeout);
                scrollTimeout = setTimeout(() => {
                    updateActivePageIndicator();
                }, 100);
            });
        }
    }
    
    function updateActivePageIndicator() {
        const viewer = document.getElementById('document-viewer-container');
        if (!viewer || !ocrData || !ocrData.pages) return;
        
        const viewerRect = viewer.getBoundingClientRect();
        const viewerMidpoint = viewerRect.top + (viewerRect.height / 3); // Use upper third
        
        let activePageIndex = 0;
        let closestDistance = Infinity;
        
        // Find which page is closest to the viewport midpoint
        for (let i = 0; i < ocrData.pages.length; i++) {
            const pageEl = document.getElementById(`page-container-${i}`);
            if (!pageEl) continue;
            
            const pageRect = pageEl.getBoundingClientRect();
            const pageTop = pageRect.top;
            const pageBottom = pageRect.bottom;
            
            // Check if page is in view
            if (pageTop <= viewerMidpoint && pageBottom >= viewerMidpoint) {
                activePageIndex = i;
                break;
            }
            
            // Otherwise find closest
            const distanceFromMidpoint = Math.abs(pageTop - viewerMidpoint);
            if (distanceFromMidpoint < closestDistance) {
                closestDistance = distanceFromMidpoint;
                activePageIndex = i;
            }
        }
        
        // Update button states
        const buttons = pagesList.querySelectorAll('.page-jump-btn');
        buttons.forEach((btn, idx) => {
            if (idx === activePageIndex) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }

    function scrollToPage(index) {
        const el = document.getElementById(`page-container-${index}`);
        const viewer = document.getElementById('document-viewer-container');
        if (!el || !viewer) return;
        
        // Calculate accurate scroll position relative to the viewer's scroll container
        const viewerRect = viewer.getBoundingClientRect();
        const elementRect = el.getBoundingClientRect();
        const relativeTop = elementRect.top - viewerRect.top + viewer.scrollTop;
        
        // Scroll with some padding at the top
        viewer.scrollTo({ 
            top: relativeTop - 16, 
            behavior: 'smooth' 
        });
        
        // Visual feedback: highlight the page briefly
        el.style.transition = 'box-shadow 0.3s ease';
        el.style.boxShadow = '0 0 0 3px rgba(37, 99, 235, 0.5)';
        setTimeout(() => {
            el.style.boxShadow = '';
        }, 1500);
    }

    function extractWordsFromPage(pageData, pageIndex) {
        const words = [];
        let wordCounter = 0;

        console.log(`Extracting words from page ${pageIndex}`);

        pageData.blocks.forEach((block, blockIndex) => {
            block.lines.forEach((line, lineIndex) => {
                line.words.forEach((word, wordIndex) => {
                    words.push({
                        ...word,
                        id: `p${pageIndex}_w${wordCounter++}`,
                        pageIndex: pageIndex,
                        originalValue: word.value
                    });
                });
            });
        });

        console.log(`Extracted ${words.length} words from page ${pageIndex}`);
        return words;
    }

    function drawBoundingBoxes(ctx, words, canvasWidth, canvasHeight) {
        console.log(`Drawing ${words.length} bounding boxes on ${canvasWidth}x${canvasHeight} canvas`);

        let drawnCount = 0;
        words.forEach((word, index) => {
            if (!word.geometry) {
                console.log(`Word ${index} missing geometry:`, word);
                return;
            }

            // Handle DocTR geometry format: [[x1, y1], [x2, y2]]
            let x1, y1, x2, y2;
            if (word.geometry.length === 2 && Array.isArray(word.geometry[0])) {
                // DocTR format: [[x1, y1], [x2, y2]]
                [x1, y1] = word.geometry[0];
                [x2, y2] = word.geometry[1];
            } else if (word.geometry[0] && word.geometry[0].length === 4) {
                // Our expected format: [[x1, y1, x2, y2]]
                [x1, y1, x2, y2] = word.geometry[0];
            } else {
                console.log(`Word ${index} has invalid geometry format:`, word.geometry);
                return;
            }

            const canvasX = x1 * canvasWidth;
            const canvasY = y1 * canvasHeight;
            const width = (x2 - x1) * canvasWidth;
            const height = (y2 - y1) * canvasHeight;

            // Debug first few boxes
            if (index < 3) {
                console.log(`Word ${index} "${word.value}": geometry=[${x1.toFixed(3)}, ${y1.toFixed(3)}, ${x2.toFixed(3)}, ${y2.toFixed(3)}] -> canvas=[${canvasX.toFixed(1)}, ${canvasY.toFixed(1)}, ${width.toFixed(1)}, ${height.toFixed(1)}]`);
            }

            // Skip invalid boxes
            if (width <= 0 || height <= 0) {
                console.log(`Skipping invalid box for word ${index}: ${width}x${height}`);
                return;
            }

            // Default red bounding box
            ctx.strokeStyle = 'rgba(255, 0, 0, 0.7)';
            ctx.lineWidth = 2;
            
            // Check correction status and apply appropriate styling
            if (word.auto_correction_overridden || word.manually_corrected) {
                // Manual correction (including overridden auto-corrections) - blue
                ctx.strokeStyle = 'rgba(0, 123, 255, 0.9)'; // Blue for manual corrections
                ctx.lineWidth = 3;
                ctx.fillStyle = 'rgba(0, 123, 255, 0.15)';
                ctx.fillRect(canvasX, canvasY, width, height);
            } else if (word.auto_corrected || word.corrected_by_lexicon) {
                // Auto-corrected words - green
                ctx.strokeStyle = 'rgba(40, 167, 69, 0.8)'; // Green for auto-corrected
                ctx.lineWidth = 2;
                ctx.fillStyle = 'rgba(40, 167, 69, 0.1)';
                ctx.fillRect(canvasX, canvasY, width, height);
            } else if (word.corrected) {
                // Other manual corrections - blue
                ctx.strokeStyle = 'rgba(0, 123, 255, 0.8)';
                ctx.lineWidth = 2;
                ctx.fillStyle = 'rgba(0, 123, 255, 0.1)';
                ctx.fillRect(canvasX, canvasY, width, height);
            }
            
            // Selected word gets priority styling
            if (word === selectedWord) {
                ctx.strokeStyle = 'rgba(0, 255, 0, 1)';
                ctx.lineWidth = 3;
            }
            
            ctx.strokeRect(canvasX, canvasY, width, height);
            drawnCount++;
        });
        
        console.log(`Drew ${drawnCount} bounding boxes out of ${words.length} words`);
    }

    // --- Canvas Event Handlers ---
    function addCanvasEventListeners(canvas, pageWords, pageIndex) {
        // Click handler
        canvas.addEventListener('click', (e) => {
            const rect = canvas.getBoundingClientRect();
            
            // Get actual canvas display size vs internal canvas size
            const scaleX = canvas.width / rect.width;
            const scaleY = canvas.height / rect.height;
            
            // Calculate click position in canvas coordinates
            const canvasX = (e.clientX - rect.left) * scaleX;
            const canvasY = (e.clientY - rect.top) * scaleY;
            
            // Normalize to [0,1] for comparison with DocTR coordinates
            const clickX = canvasX / canvas.width;
            const clickY = canvasY / canvas.height;

            console.log(`Click on page ${pageIndex + 1} at: (${clickX.toFixed(3)}, ${clickY.toFixed(3)}) canvas=(${canvasX.toFixed(1)}, ${canvasY.toFixed(1)}) display=(${rect.width.toFixed(1)}x${rect.height.toFixed(1)}) internal=(${canvas.width}x${canvas.height})`);
            
            const clickedWord = findWordAt(clickX, clickY, pageWords);
            if (clickedWord) {
                selectWord(clickedWord, pageIndex);
                // Immediately redraw to show selection highlight
                redrawAllPages();
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
            
            // Use same coordinate calculation as click handler
            const scaleX = canvas.width / rect.width;
            const scaleY = canvas.height / rect.height;
            const canvasX = (e.clientX - rect.left) * scaleX;
            const canvasY = (e.clientY - rect.top) * scaleY;
            const mouseX = canvasX / canvas.width;  // Normalize to [0,1]
            const mouseY = canvasY / canvas.height; // Normalize to [0,1]
            
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
        console.log(`Looking for word at (${relX.toFixed(3)}, ${relY.toFixed(3)})`);
        
        // Find all words that could contain the click point with different tolerance levels
        const candidates = [];
        const tolerances = [0.01, 0.03, 0.05, 0.08]; // Try multiple tolerance levels
        
        for (const tolerance of tolerances) {
            for (let i = 0; i < pageWords.length; i++) {
                const word = pageWords[i];
                if (!word.geometry) continue;
                
                // Handle DocTR geometry format: [[x1, y1], [x2, y2]]
                let x1, y1, x2, y2;
                if (word.geometry.length === 2 && Array.isArray(word.geometry[0])) {
                    // DocTR format: [[x1, y1], [x2, y2]]
                    [x1, y1] = word.geometry[0];
                    [x2, y2] = word.geometry[1];
                } else if (word.geometry[0] && word.geometry[0].length === 4) {
                    // Our expected format: [[x1, y1, x2, y2]]
                    [x1, y1, x2, y2] = word.geometry[0];
                } else {
                    continue; // Skip words with invalid geometry
                }
                
                // Expand hit area with tolerance
                const expandedX1 = x1 - tolerance;
                const expandedY1 = y1 - tolerance;
                const expandedX2 = x2 + tolerance;
                const expandedY2 = y2 + tolerance;
                
                if (relX >= expandedX1 && relX <= expandedX2 && relY >= expandedY1 && relY <= expandedY2) {
                    // Calculate distance to center for ranking
                    const centerX = (x1 + x2) / 2;
                    const centerY = (y1 + y2) / 2;
                    const distance = Math.sqrt(
                        Math.pow(relX - centerX, 2) + 
                        Math.pow(relY - centerY, 2)
                    );
                    
                    // Calculate area for ranking (smaller words are often more precise)
                    const area = (x2 - x1) * (y2 - y1);
                    
                    candidates.push({
                        word: word,
                        distance: distance,
                        area: area,
                        tolerance: tolerance,
                        confidence: word.confidence || 0,
                        bbox: [x1, y1, x2, y2]
                    });
                }
            }
            
            // If we found candidates with this tolerance, break (prefer tighter tolerance)
            if (candidates.length > 0) {
                console.log(`Found ${candidates.length} candidates with tolerance ${tolerance}`);
                break;
            }
        }
        
        if (candidates.length === 0) {
            console.log("No word found at click position");
            return null;
        }
        
        // Sort candidates by: 1) distance to center, 2) confidence, 3) smaller area
        candidates.sort((a, b) => {
            if (Math.abs(a.distance - b.distance) < 0.01) {
                // If distances are very close, prefer higher confidence
                if (Math.abs(a.confidence - b.confidence) > 0.1) {
                    return b.confidence - a.confidence;
                }
                // If confidence is similar, prefer smaller area (more precise)
                return a.area - b.area;
            }
            return a.distance - b.distance;
        });
        
        const bestMatch = candidates[0];
        console.log(`Selected best match: "${bestMatch.word.value}" (distance: ${bestMatch.distance.toFixed(3)}, confidence: ${bestMatch.confidence.toFixed(3)}, tolerance: ${bestMatch.tolerance})`);
        
        return bestMatch.word;
    }

    function selectWord(word, pageIndex) {
        console.log("Selected word:", word);
        selectedWord = word;
        selectionInfo.classList.add('hidden');
        editForm.classList.remove('hidden');
        
        // Update form fields
        textEditor.value = word.value;
        
        // Show original text vs current text for auto-corrected words
        if (originalTextSpan) {
            if (word.auto_corrected || word.corrected_by_lexicon) {
                originalTextSpan.innerHTML = `<span style="text-decoration: line-through; color: #999;">${word.original_value || word.originalValue || 'Unknown'}</span> → <strong>${word.value}</strong> <span style="color: #28a745; font-size: 0.8em;">(auto-corrected)</span>`;
            } else {
                originalTextSpan.textContent = word.value;
            }
        }
        
        if (wordPageSpan) wordPageSpan.textContent = `Page ${pageIndex + 1}`;
        if (wordPositionSpan) {
            // Handle DocTR geometry format: [[x1, y1], [x2, y2]]
            let x1, y1, x2, y2;
            if (word.geometry.length === 2 && Array.isArray(word.geometry[0])) {
                // DocTR format: [[x1, y1], [x2, y2]]
                [x1, y1] = word.geometry[0];
                [x2, y2] = word.geometry[1];
            } else if (word.geometry[0] && word.geometry[0].length === 4) {
                // Our expected format: [[x1, y1, x2, y2]]
                [x1, y1, x2, y2] = word.geometry[0];
            } else {
                x1 = y1 = x2 = y2 = 0;
            }
            wordPositionSpan.textContent = `(${x1.toFixed(3)}, ${y1.toFixed(3)}) to (${x2.toFixed(3)}, ${y2.toFixed(3)})`;
        }
        
        textEditor.focus();
    }


    function showNearbyWords(clickX, clickY, pageWords, pageIndex) {
        console.log(`Nearby words on page ${pageIndex + 1}:`);
        console.log(`Click position: (${clickX.toFixed(3)}, ${clickY.toFixed(3)})`);
        
        // Show all words with their positions for debugging
        const wordsWithDistance = pageWords.map(word => {
            if (!word.geometry) return null;
            
            // Handle DocTR geometry format: [[x1, y1], [x2, y2]]
            let x1, y1, x2, y2;
            if (word.geometry.length === 2 && Array.isArray(word.geometry[0])) {
                // DocTR format: [[x1, y1], [x2, y2]]
                [x1, y1] = word.geometry[0];
                [x2, y2] = word.geometry[1];
            } else if (word.geometry[0] && word.geometry[0].length === 4) {
                // Our expected format: [[x1, y1, x2, y2]]
                [x1, y1, x2, y2] = word.geometry[0];
            } else {
                return null; // Skip words with invalid geometry
            }
            
            const centerX = (x1 + x2) / 2;
            const centerY = (y1 + y2) / 2;
            const distance = Math.sqrt(
                Math.pow(clickX - centerX, 2) + 
                Math.pow(clickY - centerY, 2)
            );
            
            return {
                word: word,
                distance: distance,
                center: [centerX, centerY],
                bbox: [x1, y1, x2, y2]
            };
        }).filter(item => item !== null).sort((a, b) => a.distance - b.distance);

        // Show closest 5 words
        const closest = wordsWithDistance.slice(0, 5);
        console.log(`Showing ${closest.length} closest words:`);
        
        closest.forEach((item, index) => {
            console.log(`  ${index}: "${item.word.value}" center=(${item.center[0].toFixed(3)}, ${item.center[1].toFixed(3)}) bbox=[${item.bbox.map(v => v.toFixed(3)).join(', ')}] distance=${item.distance.toFixed(3)}`);
        });
        
        if (closest.length === 0) {
            console.log("  No words found nearby");
        }
    }

    // --- Save Correction Handler ---
    saveBtn.addEventListener('click', async () => {
        if (!selectedWord) return;

        const newText = textEditor.value;
        if (newText === selectedWord.value) return; // No change

        const oldText = selectedWord.value;
        
        // CRITICAL: Always use the current displayed text as "original" for this correction
        // This ensures we track the progression: OCR -> Auto-correction -> Manual correction -> Further corrections
        let originalTextForSaving = oldText; // Use what's currently displayed
        
        // But for lexicon learning, we need to track the true original OCR text
        let trueOriginalText = selectedWord.original_value || selectedWord.originalValue || oldText;
        
        console.log(`📝 Correction details:`);
        console.log(`   Current displayed: '${oldText}'`);
        console.log(`   New correction: '${newText}'`);
        console.log(`   True original OCR: '${trueOriginalText}'`);
        
        if (selectedWord.auto_corrected || selectedWord.corrected_by_lexicon) {
            console.log(`🔄 This is a correction of an auto-corrected word`);
        }
        
        // Update UI immediately for responsiveness
        updateWord(selectedWord.id, { value: newText });
        addToHistory({ wordId: selectedWord.id, oldText, newText });

        // --- Send correction to backend ---
        const formData = new FormData();
        formData.append('doc_id', docId);
        formData.append('page', selectedWord.pageIndex || 0);
        formData.append('word_id', selectedWord.id);
        formData.append('original_text', originalTextForSaving); // Current displayed text
        formData.append('corrected_text', newText);
        formData.append('true_original_text', trueOriginalText); // True original OCR text for lexicon
        formData.append('corrected_bbox', JSON.stringify(selectedWord.geometry)); 

        // Also prepare real-time OCR data update
        const ocrUpdateData = new FormData();
        ocrUpdateData.append('word_id', selectedWord.id);
        ocrUpdateData.append('corrected_text', newText);
        ocrUpdateData.append('page_index', selectedWord.pageIndex || 0);

        saveStatus.textContent = 'Saving...';
        try {
            // Send correction log first, then OCR update
            console.log(`Saving correction: '${oldText}' -> '${newText}' for word ${selectedWord.id}`);
            
            const correctionResponse = await fetch('/save_correction', { method: 'POST', body: formData });
            console.log(`Correction response status: ${correctionResponse.status}`);
            
            if (!correctionResponse.ok) {
                throw new Error(`Correction save failed: ${correctionResponse.status} ${correctionResponse.statusText}`);
            }
            
            const data = await correctionResponse.json();
            console.log('Correction save response:', data);
            
            // Then update OCR data
            const ocrUpdateResponse = await fetch(`/update_ocr_data/${docId}`, { method: 'POST', body: ocrUpdateData });
            console.log(`OCR update response status: ${ocrUpdateResponse.status}`);
            
            let ocrUpdateResult = null;
            if (ocrUpdateResponse.ok) {
                ocrUpdateResult = await ocrUpdateResponse.json();
                console.log('OCR update response:', ocrUpdateResult);
            } else {
                console.warn('OCR update failed but continuing...');
            }
            
            if (data.status === 'success') {
                let statusText = 'Saved!';
                
                // Special message for auto-corrected word corrections
                if (selectedWord.auto_corrected || selectedWord.corrected_by_lexicon) {
                    statusText = '🔄 Auto-correction overridden and saved!';
                }
                
                // Check if lexicon was updated
                if (data.lexicon_updated) {
                    statusText += ` Lexicon pattern updated! (${data.lexicon_size} total patterns)`;
                } else if (data.correction_frequency) {
                    const remaining = Math.max(0, 1 - data.correction_frequency); // Use threshold of 1
                    if (remaining > 0) {
                        statusText += ` (${remaining} more correction needed for auto-learning)`;
                    } else {
                        statusText += ` (Pattern learned - will auto-correct in future uploads)`;
                    }
                }
                
                // Show training sample creation
                if (data.training_data_prepared) {
                    statusText += ' 🎓 Training sample created!';
                }
                
                saveStatus.textContent = statusText;
                
                // Update raw text panel immediately
                updateRawTextPanel(selectedWord, oldText, newText);
                
                // Highlight the raw text corresponding to this correction
                highlightCorrectedWordInRawText(selectedWord, oldText, newText);
                
                // Update learning statistics
                updateLearningStats();
                
            } else {
                saveStatus.textContent = `Error: ${data.message}`;
            }
            
            setTimeout(() => saveStatus.textContent = '', 3000);
        } catch (err) {
            saveStatus.textContent = 'Save failed.';
            console.error('Save error:', err);
            setTimeout(() => saveStatus.textContent = '', 3000);
        }
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
                // Store original value if not already stored
                if (!word.original_value && updates.value && word.value !== updates.value) {
                    word.original_value = word.value;
                }
                
                // Mark as corrected if text is being updated
                if (updates.value && word.value !== updates.value) {
                    updates.corrected = true;
                    updates.manually_corrected = true;
                    updates.corrected_at = new Date().toISOString();
                    
                    // If this was auto-corrected, mark as overridden
                    if (word.auto_corrected || word.corrected_by_lexicon) {
                        updates.auto_correction_overridden = true;
                        console.log(`🔄 Auto-correction overridden: ${word.id}`);
                    }
                }
                
                Object.assign(word, updates);
                
                if (word === selectedWord) {
                    textEditor.value = word.value;
                }
                
                // Update canvas display for the page
                redrawAllPages();
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
        
        // Get confidence level for styling - handle undefined/null confidence
        const confidence = word.confidence;
        let confidenceClass = 'confidence-low';
        let confidenceText = 'N/A';
        let confidencePercent = 'N/A';
        
        if (confidence !== null && confidence !== undefined && !isNaN(confidence)) {
            confidencePercent = `${(confidence * 100).toFixed(1)}%`;
            if (confidence >= 0.8) {
                confidenceClass = 'confidence-high';
                confidenceText = 'High';
            } else if (confidence >= 0.5) {
                confidenceClass = 'confidence-medium';
                confidenceText = 'Medium';
            } else {
                confidenceClass = 'confidence-low';
                confidenceText = 'Low';
            }
        }
        
        // Format bounding box coordinates - handle different geometry formats
        let bboxText = 'N/A';
        if (word.geometry) {
            try {
                let x1, y1, x2, y2;
                if (word.geometry.length === 2 && Array.isArray(word.geometry[0])) {
                    // DocTR format: [[x1, y1], [x2, y2]]
                    [x1, y1] = word.geometry[0];
                    [x2, y2] = word.geometry[1];
                } else if (word.geometry[0] && word.geometry[0].length === 4) {
                    // Our expected format: [[x1, y1, x2, y2]]
                    [x1, y1, x2, y2] = word.geometry[0];
                } else {
                    bboxText = 'Invalid geometry format';
                }
                
                if (x1 !== undefined && y1 !== undefined && x2 !== undefined && y2 !== undefined) {
                    bboxText = `(${x1.toFixed(3)}, ${y1.toFixed(3)}) → (${x2.toFixed(3)}, ${y2.toFixed(3)})`;
                }
            } catch (error) {
                console.warn('Error parsing geometry for tooltip:', error);
                bboxText = 'Error parsing coordinates';
            }
        }
        
        // Create tooltip content
        let tooltipContent = `
            <div class="tooltip-text">"${word.value || 'N/A'}"</div>
            <div class="tooltip-confidence ${confidenceClass}">
                Confidence: ${confidenceText} (${confidencePercent})
            </div>`;
        
        // Add correction info if applicable
        if (word.auto_corrected || word.corrected_by_lexicon) {
            tooltipContent += `
            <div class="tooltip-autocorrected">
                🤖 Auto-corrected from: "${word.original_value || 'Unknown'}"
            </div>`;
        } else if (word.corrected) {
            tooltipContent += `
            <div class="tooltip-manual-corrected">
                ✏️ Manually corrected from: "${word.original_value || 'Unknown'}"
            </div>`;
        }
        
        tooltipContent += `
            <div class="tooltip-position">
                ${bboxText}
            </div>
        `;
        
        tooltip.innerHTML = tooltipContent;
        
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

    // --- Zoom and Navigation Controls ---
    function initializeZoomControls() {
        // Zoom controls
        document.getElementById('zoom-in-btn').addEventListener('click', () => {
            currentZoom = Math.min(currentZoom * 1.2, 3.0);
            updateZoom();
        });

        document.getElementById('zoom-out-btn').addEventListener('click', () => {
            currentZoom = Math.max(currentZoom / 1.2, 0.3);
            updateZoom();
        });

        // Page navigation controls
        document.getElementById('prev-page-btn').addEventListener('click', () => {
            const currentPage = getCurrentPageIndex();
            if (currentPage > 0) {
                scrollToPage(currentPage - 1);
            }
        });

        document.getElementById('next-page-btn').addEventListener('click', () => {
            const currentPage = getCurrentPageIndex();
            if (currentPage < ocrData.pages.length - 1) {
                scrollToPage(currentPage + 1);
            }
        });

        // Panning controls (for horizontal navigation within zoomed pages)
        document.getElementById('pan-left-btn').addEventListener('click', () => {
            panHorizontally(-200); // Pan left by 200px
        });

        document.getElementById('pan-right-btn').addEventListener('click', () => {
            panHorizontally(200); // Pan right by 200px
        });

        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            // Only handle navigation when not in input fields
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                return;
            }

            const currentPage = getCurrentPageIndex();
            switch (e.key) {
                case 'ArrowLeft':
                    if (currentPage > 0) {
                        scrollToPage(currentPage - 1);
                        e.preventDefault();
                    }
                    break;
                case 'ArrowRight':
                    if (currentPage < ocrData.pages.length - 1) {
                        scrollToPage(currentPage + 1);
                        e.preventDefault();
                    }
                    break;
                case 'Home':
                    scrollToPage(0);
                    e.preventDefault();
                    break;
                case 'End':
                    scrollToPage(ocrData.pages.length - 1);
                    e.preventDefault();
                    break;
                case 'h':
                case 'H':
                    panHorizontally(-200); // Pan left
                    e.preventDefault();
                    break;
                case 'l':
                case 'L':
                    panHorizontally(200); // Pan right
                    e.preventDefault();
                    break;
            }
        });
    }

    function updateZoom() {
        // Update zoom level display
        zoomLevel.textContent = `${Math.round(currentZoom * 100)}%`;

        const viewer = document.getElementById('document-viewer-container');
        if (!viewer) return;

        const viewerRect = viewer.getBoundingClientRect();
        
        // Store reference point for centering
        let centerTarget = null;
        
        if (selectedWord) {
            // Zoom will center on selected BB
            centerTarget = { type: 'bb', word: selectedWord };
        } else {
            // Zoom will maintain current viewport center
            const currentPage = getCurrentPageIndex();
            const pageElement = document.getElementById(`page-container-${currentPage}`);
            if (pageElement) {
                const pageRect = pageElement.getBoundingClientRect();
                const relativeScrollY = viewer.scrollTop - pageElement.offsetTop + (viewerRect.height / 2);
                centerTarget = { 
                    type: 'viewport', 
                    pageIndex: currentPage,
                    relativeY: relativeScrollY / pageRect.height  // Store as ratio
                };
            }
        }

        // Apply zoom to ALL pages
        applyZoomToAllPages();

        // After zoom, restore centering
        requestAnimationFrame(() => {
            if (centerTarget && centerTarget.type === 'bb') {
                centerOnBoundingBox(centerTarget.word);
            } else if (centerTarget && centerTarget.type === 'viewport') {
                const pageElement = document.getElementById(`page-container-${centerTarget.pageIndex}`);
                if (pageElement) {
                    const pageRect = pageElement.getBoundingClientRect();
                    const targetY = pageElement.offsetTop + (centerTarget.relativeY * pageRect.height) - (viewerRect.height / 2);
                    viewer.scrollTop = Math.max(0, targetY);
                }
            }
        });
    }

    function applyZoomToAllPages() {
        // Apply global zoom to ALL pages
        pages.forEach(page => {
            const canvas = page.canvas;
            const ctx = page.context;
            const image = page.image;

            if (!canvas || !ctx || !image) return;

            // Calculate new dimensions based on global zoom
            const maxWidth = 800;
            const scale = Math.min(maxWidth / image.width, 1.0) * currentZoom;
            const newWidth = image.width * scale;
            const newHeight = image.height * scale;

            // Resize canvas if dimensions changed
            if (canvas.width !== newWidth || canvas.height !== newHeight) {
                canvas.width = newWidth;
                canvas.height = newHeight;
            }

            // Clear and redraw
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(image, 0, 0, newWidth, newHeight);

            // Redraw bounding boxes at new scale
            const pageWords = page.words;
            drawBoundingBoxes(ctx, pageWords, newWidth, newHeight);

            // Update page scale for future reference
            page.scale = scale;
        });
    }

    function redrawAllPages() {
        // Redraw all pages at current global zoom level
        applyZoomToAllPages();
    }


    function centerOnBoundingBox(word) {
        if (!word || !word.geometry) return;

        const viewer = document.getElementById('document-viewer-container');
        if (!viewer) return;

        // Find the page containing this word
        const pageIndex = word.pageIndex || 0;
        const pageElement = document.getElementById(`page-container-${pageIndex}`);
        if (!pageElement) return;

        // Get the current page data
        const page = pages.find(p => p.index === pageIndex);
        if (!page) return;

        // Get canvas for this page
        const canvas = page.canvas;
        if (!canvas) return;

        // Get bounding box coordinates (handle DocTR format - normalized 0-1)
        let x1, y1, x2, y2;
        if (word.geometry.length === 2 && Array.isArray(word.geometry[0])) {
            [x1, y1] = word.geometry[0];
            [x2, y2] = word.geometry[1];
        } else if (word.geometry[0] && word.geometry[0].length === 4) {
            [x1, y1, x2, y2] = word.geometry[0];
        } else {
            return;
        }

        // Calculate BB center in normalized coordinates (0-1)
        const normalizedCenterX = (x1 + x2) / 2;
        const normalizedCenterY = (y1 + y2) / 2;

        // Convert to canvas pixel coordinates
        const canvasCenterX = normalizedCenterX * canvas.width;
        const canvasCenterY = normalizedCenterY * canvas.height;

        // Get the canvas container to account for any padding/centering
        const canvasContainer = canvas.parentElement;
        const canvasRect = canvas.getBoundingClientRect();
        const viewerRect = viewer.getBoundingClientRect();

        // Calculate BB center position relative to viewer's top-left
        const bbScreenX = canvasRect.left - viewerRect.left + canvasCenterX;
        const bbScreenY = canvasRect.top - viewerRect.top + canvasCenterY;

        // Calculate how much to scroll to center the BB
        const targetScrollX = viewer.scrollLeft + bbScreenX - (viewerRect.width / 2);
        const targetScrollY = viewer.scrollTop + bbScreenY - (viewerRect.height / 2);

        // Apply scroll with smooth scrolling
        viewer.scrollTo({
            left: Math.max(0, targetScrollX),
            top: Math.max(0, targetScrollY),
            behavior: 'smooth'
        });
    }


    function updatePageIndicator() {
        if (pages.length > 0) {
            pageIndicator.textContent = `${pages.length} page${pages.length > 1 ? 's' : ''}`;
        } else {
            pageIndicator.textContent = 'Loading...';
        }
    }

    function getCurrentPageIndex() {
        const viewer = document.getElementById('document-viewer-container');
        if (!viewer || !ocrData || !ocrData.pages) return 0;

        const viewerRect = viewer.getBoundingClientRect();
        const viewerMidpoint = viewerRect.top + (viewerRect.height / 3);

        let currentPageIndex = 0;
        let closestDistance = Infinity;

        // Find which page is closest to the viewport midpoint
        for (let i = 0; i < ocrData.pages.length; i++) {
            const pageEl = document.getElementById(`page-container-${i}`);
            if (!pageEl) continue;

            const pageRect = pageEl.getBoundingClientRect();
            const pageTop = pageRect.top;

            // Check if page is in view
            if (pageTop <= viewerMidpoint && pageTop + pageRect.height >= viewerMidpoint) {
                currentPageIndex = i;
                break;
            }

            // Otherwise find closest
            const distanceFromMidpoint = Math.abs(pageTop - viewerMidpoint);
            if (distanceFromMidpoint < closestDistance) {
                closestDistance = distanceFromMidpoint;
                currentPageIndex = i;
            }
        }

        return currentPageIndex;
    }

    function panHorizontally(deltaX) {
        const viewer = document.getElementById('document-viewer-container');
        if (!viewer) return;

        // Pan horizontally by the specified amount
        viewer.scrollLeft += deltaX;
    }

    // --- Text Panel Linking Functions ---
    function updateRawTextPanel(word, oldText, newText) {
        if (!rawTextDisplay) return;
        
        try {
            console.log(`Updating raw text panel: '${oldText}' → '${newText}'`);
            
            // Get current raw text
            let rawText = rawTextDisplay.value;
            console.log(`Raw text length: ${rawText.length}`);
            
            // Try multiple replacement strategies
            let updated = false;
            
            // Strategy 1: Exact match replacement
            if (rawText.includes(oldText)) {
                rawText = rawText.replace(oldText, newText);
                updated = true;
                console.log(`Strategy 1 success: exact match replacement`);
            }
            
            // Strategy 2: Case-insensitive replacement
            if (!updated) {
                const regex = new RegExp(escapeRegExp(oldText), 'gi');
                if (regex.test(rawText)) {
                    rawText = rawText.replace(regex, newText);
                    updated = true;
                    console.log(`Strategy 2 success: case-insensitive replacement`);
                }
            }
            
            // Strategy 3: Handle special characters (like < > - etc.)
            if (!updated) {
                // For text with special characters, use indexOf and substring replacement
                const startIndex = rawText.indexOf(oldText);
                if (startIndex !== -1) {
                    const beforeText = rawText.substring(0, startIndex);
                    const afterText = rawText.substring(startIndex + oldText.length);
                    rawText = beforeText + newText + afterText;
                    updated = true;
                    console.log(`Strategy 3 success: indexOf replacement at position ${startIndex}`);
                }
            }
            
            // Strategy 4: Line-by-line search and replace
            if (!updated) {
                const lines = rawText.split('\n');
                for (let i = 0; i < lines.length; i++) {
                    if (lines[i].includes(oldText)) {
                        lines[i] = lines[i].replace(oldText, newText);
                        rawText = lines.join('\n');
                        updated = true;
                        console.log(`Strategy 4 success: line ${i} replacement`);
                        break;
                    }
                }
            }
            
            if (updated) {
                rawTextDisplay.value = rawText;
                console.log(`✅ Raw text panel updated successfully`);
                
                // Scroll to the updated text
                scrollToWordInRawText(newText);
            } else {
                console.warn(`❌ Failed to update raw text panel - '${oldText}' not found in raw text`);
                console.log(`Raw text preview: "${rawText.substring(0, 200)}..."`);
            }
            
        } catch (error) {
            console.error('Error updating raw text panel:', error);
        }
    }

    function highlightCorrectedWordInRawText(word, oldText, newText) {
        if (!rawTextDisplay) return;
        
        try {
            // Find the word in the raw text and highlight it temporarily
            const rawText = rawTextDisplay.value;
            const wordRegex = new RegExp(`\\b${escapeRegExp(newText)}\\b`, 'gi'); // Use new text now
            
            // Replace first occurrence with highlighted version
            const highlightedText = rawText.replace(wordRegex, `[CORRECTED: ${oldText} → ${newText}]`);
            
            // Update the raw text display temporarily
            const originalText = rawText;
            rawTextDisplay.value = highlightedText;
            
            // Scroll to the corrected word
            scrollToWordInRawText(newText);
            
            // Revert back to corrected text after 3 seconds
            setTimeout(() => {
                rawTextDisplay.value = originalText;
            }, 3000);
            
        } catch (error) {
            console.error('Error highlighting corrected word:', error);
        }
    }

    function scrollToWordInRawText(wordText) {
        if (!rawTextDisplay) return;
        
        try {
            const text = rawTextDisplay.value;
            const wordIndex = text.toLowerCase().indexOf(wordText.toLowerCase());
            
            if (wordIndex !== -1) {
                // Calculate approximate line number
                const beforeText = text.substring(0, wordIndex);
                const lineNumber = beforeText.split('\n').length;
                
                // Scroll to approximate position
                const lineHeight = 20; // Approximate line height in pixels
                const scrollPosition = Math.max(0, (lineNumber - 5) * lineHeight);
                rawTextDisplay.scrollTop = scrollPosition;
                
                // Focus the textarea briefly to show the scroll position
                rawTextDisplay.focus();
                setTimeout(() => rawTextDisplay.blur(), 500);
            }
        } catch (error) {
            console.error('Error scrolling to word:', error);
        }
    }

    function escapeRegExp(string) {
        return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    // --- Enhanced Bounding Box Selection ---
    function selectWordAndHighlightInText(word, pageIndex) {
        // Select the word in the canvas
        selectWord(word, pageIndex);
        
        // Switch to raw text tab and highlight the word
        switchTab('raw-text');
        setTimeout(() => {
            scrollToWordInRawText(word.value);
        }, 300);
    }

    // --- Document Type Detection ---
    function detectDocumentType() {
        if (!ocrData) return 'unknown';
        
        // Extract all text for analysis
        const fullText = ocrData.pages
            .flatMap(page => page.blocks)
            .flatMap(block => block.lines)
            .flatMap(line => line.words)
            .map(word => word.value)
            .join(' ')
            .toLowerCase();
        
        // Simple document type detection based on keywords
        if (fullText.includes('invoice') || fullText.includes('bill') || fullText.includes('amount due')) {
            return 'invoice';
        } else if (fullText.includes('receipt') || fullText.includes('total paid')) {
            return 'receipt';
        } else if (fullText.includes('id') || fullText.includes('identification') || fullText.includes('passport')) {
            return 'identity_document';
        } else if (fullText.includes('contract') || fullText.includes('agreement')) {
            return 'contract';
        } else {
            return 'document';
        }
    }

    // --- Learning Tab Functions ---
    async function initializeLearningTab() {
        try {
            // Load initial learning data
            await loadLearningData();
            
            // Set up retraining buttons
            const retrainRealBtn = document.getElementById('retrain-real-btn');
            if (retrainRealBtn) {
                retrainRealBtn.addEventListener('click', () => triggerRetraining(true));
            }
            
            const retrainStubBtn = document.getElementById('retrain-stub-btn');
            if (retrainStubBtn) {
                retrainStubBtn.addEventListener('click', () => triggerRetraining(false));
            }
            
            // Set up configuration controls
            const updateThresholdBtn = document.getElementById('update-threshold-btn');
            if (updateThresholdBtn) {
                updateThresholdBtn.addEventListener('click', updateLearningThreshold);
            }
            
            // Set up deployment controls
            const refreshModelsBtn = document.getElementById('refresh-models-btn');
            if (refreshModelsBtn) {
                refreshModelsBtn.addEventListener('click', loadAvailableModels);
            }
            
            const rollbackBtn = document.getElementById('rollback-model-btn');
            if (rollbackBtn) {
                rollbackBtn.addEventListener('click', rollbackModel);
            }
            
            // Refresh learning data when tab is selected
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    if (e.target.dataset.tab === 'learning') {
                        await loadLearningData();
                        await loadAvailableModels();
                        await loadDeploymentHistory();
                    }
                });
            });
            
            // Load deployment info on initial load
            await loadAvailableModels();
            await loadDeploymentHistory();
            
        } catch (error) {
            console.error('Error initializing learning tab:', error);
        }
    }

    async function loadLearningData() {
        try {
            // Load lexicon, training data, document-specific corrections, and config in parallel
            const [lexiconResponse, trainingResponse, documentCorrectionsResponse, configResponse] = await Promise.all([
                fetch('/api/lexicon'),
                fetch('/api/training_data/stats'),
                fetch(`/api/document_corrections/${docId}`),
                fetch('/api/config')
            ]);

            if (lexiconResponse.ok) {
                const lexiconData = await lexiconResponse.json();
                updateLexiconDisplay(lexiconData);
            } else {
                console.warn('Failed to load lexicon data');
            }

            if (trainingResponse.ok) {
                const trainingData = await trainingResponse.json();
                updateTrainingDisplay(trainingData);
            } else {
                console.warn('Failed to load training data');
            }

            if (documentCorrectionsResponse.ok) {
                const documentData = await documentCorrectionsResponse.json();
                updateDocumentCorrectionsDisplay(documentData);
            } else {
                console.warn('Failed to load document corrections');
            }

            if (configResponse.ok) {
                const configData = await configResponse.json();
                updateConfigDisplay(configData);
            } else {
                console.warn('Failed to load configuration');
            }

        } catch (error) {
            console.error('Error loading learning data:', error);
        }
    }

    async function updateLearningStats() {
        // Quick update of learning statistics after a correction
        try {
            await loadLearningData();
        } catch (error) {
            console.error('Error updating learning stats:', error);
        }
    }

    function updateLexiconDisplay(data) {
        const lexiconSizeSpan = document.getElementById('lexicon-size');
        const lexiconList = document.getElementById('lexicon-list');

        if (lexiconSizeSpan) {
            lexiconSizeSpan.textContent = data.lexicon_size || 0;
        }

        if (lexiconList && data.lexicon) {
            const lexiconEntries = Object.entries(data.lexicon);
            
            if (lexiconEntries.length === 0) {
                lexiconList.innerHTML = '<li class="no-data">No patterns learned yet - make some corrections to see them here!</li>';
            } else {
                lexiconList.innerHTML = '';
                
                // Show up to 5 most recent entries
                lexiconEntries.slice(0, 5).forEach(([original, corrected]) => {
                    const li = document.createElement('li');
                    li.className = 'lexicon-pattern-item';
                    
                    // Create expandable display for long patterns
                    const isLong = original.length > 30 || corrected.length > 30;
                    
                    if (isLong) {
                        li.innerHTML = `
                            <div class="pattern-display">
                                <div class="pattern-short" onclick="this.style.display='none'; this.nextElementSibling.style.display='block';">
                                    <span class="correction-item">'${original.substring(0, 20)}...' → '${corrected.substring(0, 20)}...'</span>
                                    <small class="expand-hint">(click to expand)</small>
                                </div>
                                <div class="pattern-full" style="display: none;" onclick="this.style.display='none'; this.previousElementSibling.style.display='block';">
                                    <span class="correction-item-full">'${original}' → '${corrected}'</span>
                                    <small class="collapse-hint">(click to collapse)</small>
                                </div>
                            </div>
                        `;
                    } else {
                        li.innerHTML = `<span class="correction-item">'${original}' → '${corrected}'</span>`;
                    }
                    
                    lexiconList.appendChild(li);
                });
                
                if (lexiconEntries.length > 5) {
                    const li = document.createElement('li');
                    li.className = 'more-items';
                    li.textContent = `... and ${lexiconEntries.length - 5} more patterns`;
                    lexiconList.appendChild(li);
                }
            }
        }
    }

    function updateTrainingDisplay(data) {
        const trainingSamplesSpan = document.getElementById('training-samples');
        const trainingSamplesForRetrain = document.getElementById('training-samples-for-retrain');

        if (trainingSamplesSpan) {
            trainingSamplesSpan.textContent = data.total_samples || 0;
        }

        if (trainingSamplesForRetrain) {
            trainingSamplesForRetrain.textContent = data.total_samples || 0;
        }
    }

    function updateDocumentCorrectionsDisplay(data) {
        // Update document-specific correction counters
        const docCorrectionsSpan = document.getElementById('doc-corrections-count');
        const autoCorrectionsSpan = document.getElementById('auto-corrections-count');
        
        if (docCorrectionsSpan) {
            docCorrectionsSpan.textContent = data.total_corrections || 0;
        }
        
        if (autoCorrectionsSpan) {
            autoCorrectionsSpan.textContent = data.auto_corrections_applied || 0;
        }
        
        // Show auto-corrections applied to this document
        const autoCorrectionsContainer = document.getElementById('auto-corrections-list');
        if (autoCorrectionsContainer && data.lexicon_patterns_used) {
            if (data.lexicon_patterns_used.length === 0) {
                autoCorrectionsContainer.innerHTML = '<div class="no-data">No auto-corrections yet - upload documents with similar errors to see learning in action!</div>';
            } else {
                autoCorrectionsContainer.innerHTML = '';
                data.lexicon_patterns_used.slice(0, 5).forEach(pattern => {
                    const item = document.createElement('div');
                    item.className = 'correction-item-display';
                    item.innerHTML = `<span class="auto-correction-item">✅ ${pattern}</span>`;
                    autoCorrectionsContainer.appendChild(item);
                });
                
                if (data.lexicon_patterns_used.length > 5) {
                    const moreItem = document.createElement('div');
                    moreItem.className = 'more-items';
                    moreItem.textContent = `... and ${data.lexicon_patterns_used.length - 5} more`;
                    autoCorrectionsContainer.appendChild(moreItem);
                }
            }
        }
        
        // Update the training samples count for retraining section
        const trainingSamplesForRetrain = document.getElementById('training-samples-for-retrain');
        if (trainingSamplesForRetrain) {
            // This will be updated when training data loads
        }
    }

    async function triggerRetraining(isReal = false) {
        const retrainBtn = isReal ? document.getElementById('retrain-real-btn') : document.getElementById('retrain-stub-btn');
        const retrainStatus = document.getElementById('retrain-status');

        if (!retrainBtn || !retrainStatus) return;

        try {
            retrainBtn.disabled = true;
            
            const endpoint = isReal ? '/api/retrain_real' : '/api/retrain_stub';
            retrainStatus.textContent = isReal ? '🔥 Starting real PyTorch training...' : '🔄 Starting simulation...';
            retrainStatus.className = 'loading';

            const response = await fetch(endpoint, { method: 'POST' });
            const data = await response.json();

            if (response.ok) {
                let statusHTML;
                
                if (isReal) {
                    // Real training completed
                    statusHTML = `
                        <div style="padding: 1rem; background: #d4edda; border: 2px solid #28a745; border-radius: 6px; margin-top: 0.5rem;">
                            <strong style="color: #155724;">✅ TRAINING COMPLETED!</strong>
                            <p style="margin: 0.5rem 0; color: #155724; font-size: 0.9rem;">
                                ${data.message}
                            </p>
                            <p style="margin: 0.5rem 0; color: #155724; font-size: 0.85rem;">
                                <strong>Samples used:</strong> ${data.samples_used} (${data.train_samples} train, ${data.val_samples} val)<br>
                                <strong>Epochs:</strong> ${data.epochs_completed}<br>
                                <strong>Final train loss:</strong> ${data.final_train_loss.toFixed(4)}<br>
                                ${data.final_val_accuracy ? `<strong>Validation accuracy:</strong> ${(data.final_val_accuracy * 100).toFixed(1)}%<br>` : ''}
                                <strong>Device:</strong> ${data.device.toUpperCase()}<br>
                                <strong>Model saved:</strong> ✅
                            </p>
                            <div style="margin-top: 0.75rem; padding: 0.5rem; background: white; border-radius: 4px;">
                                <p style="margin: 0.25rem 0; font-size: 0.85rem; color: #155724;"><strong>Next step:</strong> Deploy this model to use it in production!</p>
                                <button onclick="loadAvailableModels()" style="margin-top: 0.5rem; padding: 0.5rem 1rem; background: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer;">
                                    View Models & Deploy
                                </button>
                            </div>
                        </div>
                    `;
                } else {
                    // Stub simulation
                    statusHTML = `
                        <div style="padding: 1rem; background: #fff3cd; border: 2px solid #ffc107; border-radius: 6px; margin-top: 0.5rem;">
                            <strong style="color: #856404;">⚠️ STUB IMPLEMENTATION</strong>
                            <p style="margin: 0.5rem 0; color: #856404; font-size: 0.9rem;">
                                ${data.message}
                            </p>
                            <p style="margin: 0.5rem 0; color: #856404; font-size: 0.85rem;">
                                <strong>Samples used:</strong> ${data.samples_used}<br>
                                <strong>Status:</strong> Training data collected ✅<br>
                                <strong>Model updated:</strong> No ❌ (stub only)
                            </p>
                            <details style="margin-top: 0.5rem;">
                                <summary style="cursor: pointer; color: #856404; font-size: 0.85rem; font-weight: bold;">
                                    What does this mean? ▼
                                </summary>
                                <div style="margin-top: 0.5rem; padding: 0.5rem; background: white; border-radius: 4px; font-size: 0.85rem; color: #333;">
                                    <p><strong>This is just a simulation.</strong> Use the "🔥 Train Real Model" button for actual training.</p>
                                </div>
                            </details>
                        </div>
                    `;
                }
                
                retrainStatus.innerHTML = statusHTML;
                retrainStatus.className = 'success';
                
                // Log to console for visibility
                console.log(isReal ? '🔥 REAL TRAINING COMPLETED' : '🔄 RETRAINING STUB COMPLETED');
                console.log('Samples used:', data.samples_used);
                if (isReal) {
                    console.log('Final loss:', data.final_train_loss);
                    console.log('Validation accuracy:', data.final_val_accuracy);
                    console.log('Model path:', data.model_path);
                    
                    // Refresh models list
                    await loadAvailableModels();
                }
            } else {
                retrainStatus.innerHTML = `
                    <div style="padding: 0.5rem; background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; color: #721c24;">
                        <strong>Error:</strong> ${data.error || 'Retraining failed'}
                        ${data.samples_available !== undefined ? `<br><small>Available samples: ${data.samples_available}/10</small>` : ''}
                    </div>
                `;
                retrainStatus.className = 'error';
            }

        } catch (error) {
            console.error('Retraining error:', error);
            retrainStatus.innerHTML = `
                <div style="padding: 0.5rem; background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; color: #721c24;">
                    <strong>Error:</strong> Retraining failed - network error
                </div>
            `;
            retrainStatus.className = 'error';
        } finally {
            retrainBtn.disabled = false;
            // Don't auto-hide this important message
            // setTimeout(() => {
            //     retrainStatus.textContent = '';
            //     retrainStatus.className = '';
            // }, 5000);
        }
    }

    // --- Configuration Functions ---
    function updateConfigDisplay(configData) {
        const currentThresholdSpan = document.getElementById('current-threshold');
        const autoCorrectStatusSpan = document.getElementById('auto-correction-status');
        const learningThresholdInput = document.getElementById('learning-threshold');

        if (currentThresholdSpan) {
            currentThresholdSpan.textContent = configData.lexicon_learning_threshold || 3;
        }

        if (autoCorrectStatusSpan) {
            const enabled = configData.auto_correction_enabled;
            autoCorrectStatusSpan.textContent = enabled ? 'Enabled' : 'Disabled';
            autoCorrectStatusSpan.style.color = enabled ? '#28a745' : '#dc3545';
        }

        if (learningThresholdInput) {
            learningThresholdInput.value = configData.lexicon_learning_threshold || 3;
        }
    }

    async function updateLearningThreshold() {
        const thresholdInput = document.getElementById('learning-threshold');
        const updateBtn = document.getElementById('update-threshold-btn');

        if (!thresholdInput || !updateBtn) return;

        const newThreshold = parseInt(thresholdInput.value);
        if (isNaN(newThreshold) || newThreshold < 1) {
            alert('Please enter a valid threshold (1 or higher)');
            return;
        }

        try {
            updateBtn.disabled = true;
            updateBtn.textContent = 'Updating...';

            const formData = new FormData();
            formData.append('key', 'lexicon_learning_threshold');
            formData.append('value', newThreshold.toString());

            const response = await fetch('/api/config/update', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (response.ok) {
                // Update the display
                const currentThresholdSpan = document.getElementById('current-threshold');
                if (currentThresholdSpan) {
                    currentThresholdSpan.textContent = newThreshold;
                }
                
                // Show success message
                updateBtn.textContent = 'Updated!';
                updateBtn.style.backgroundColor = '#28a745';
                
                setTimeout(() => {
                    updateBtn.textContent = 'Update';
                    updateBtn.style.backgroundColor = '';
                }, 2000);
            } else {
                alert(`Failed to update threshold: ${result.error}`);
                updateBtn.textContent = 'Update';
            }

        } catch (error) {
            console.error('Error updating threshold:', error);
            alert('Failed to update threshold');
            updateBtn.textContent = 'Update';
        } finally {
            updateBtn.disabled = false;
        }
    }

    // --- Model Deployment Functions ---
    async function loadAvailableModels() {
        try {
            const response = await fetch('/api/models/available');
            if (!response.ok) {
                console.warn('Failed to load available models');
                return;
            }
            
            const data = await response.json();
            displayAvailableModels(data.available_models, data.active_model);
        } catch (error) {
            console.error('Error loading available models:', error);
        }
    }
    
    function displayAvailableModels(models, activeModel) {
        const container = document.getElementById('models-list-container');
        const activeDetails = document.getElementById('active-model-details');
        
        // Display active model
        if (activeDetails) {
            if (activeModel) {
                activeDetails.innerHTML = `
                    <p style="margin: 0.25rem 0;"><strong>Model:</strong> Active (deployed)</p>
                    <p style="margin: 0.25rem 0;"><strong>Epoch:</strong> ${activeModel.epoch}</p>
                    <p style="margin: 0.25rem 0;"><strong>Accuracy:</strong> ${(activeModel.accuracy * 100).toFixed(1)}%</p>
                    <p style="margin: 0.25rem 0;"><strong>Deployed:</strong> ${new Date(activeModel.deployed_at).toLocaleString()}</p>
                `;
            } else {
                activeDetails.innerHTML = '<p style="margin: 0;">No model deployed yet</p>';
            }
        }
        
        // Display available models
        if (container) {
            if (!models || models.length === 0) {
                container.innerHTML = '<p style="color: #666; font-style: italic; font-size: 0.85rem;">No trained models yet. Train a model first!</p>';
                return;
            }
            
            container.innerHTML = '';
            models.forEach(model => {
                const modelDiv = document.createElement('div');
                modelDiv.className = 'model-item';
                modelDiv.style.cssText = 'padding: 0.75rem; background: white; border: 1px solid #ddd; border-radius: 6px; margin-bottom: 0.5rem;';
                
                const badge = model.is_best ? '<span style="background: #28a745; color: white; padding: 0.2rem 0.4rem; border-radius: 3px; font-size: 0.75rem; margin-left: 0.5rem;">BEST</span>' : 
                             model.is_latest ? '<span style="background: #0077b6; color: white; padding: 0.2rem 0.4rem; border-radius: 3px; font-size: 0.75rem; margin-left: 0.5rem;">LATEST</span>' : '';
                
                modelDiv.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="flex: 1;">
                            <p style="margin: 0; font-weight: bold; font-size: 0.9rem;">${model.filename}${badge}</p>
                            <p style="margin: 0.25rem 0; font-size: 0.8rem; color: #666;">
                                Epoch ${model.epoch} | Loss: ${model.loss.toFixed(4)} | Acc: ${(model.accuracy * 100).toFixed(1)}%
                            </p>
                            <p style="margin: 0.25rem 0; font-size: 0.75rem; color: #999;">${model.size_mb.toFixed(2)} MB</p>
                        </div>
                        <button 
                            class="deploy-model-btn btn-small" 
                            data-filename="${model.filename}"
                            style="white-space: nowrap;">
                            🚀 Deploy
                        </button>
                    </div>
                `;
                
                container.appendChild(modelDiv);
            });
            
            // Add click handlers to deploy buttons
            container.querySelectorAll('.deploy-model-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const filename = e.target.dataset.filename;
                    await deployModel(filename);
                });
            });
        }
    }
    
    async function deployModel(filename) {
        const deploymentStatus = document.getElementById('deployment-status');
        
        if (!confirm(`Deploy model "${filename}" to production?\n\nThis will make it the active OCR model.`)) {
            return;
        }
        
        try {
            deploymentStatus.textContent = '🚀 Deploying model...';
            deploymentStatus.className = 'loading';
            
            const formData = new FormData();
            formData.append('model_filename', filename);
            formData.append('deployed_by', 'user');
            formData.append('notes', `Deployed via UI at ${new Date().toLocaleString()}`);
            
            const response = await fetch('/api/models/deploy', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (response.ok) {
                deploymentStatus.innerHTML = `
                    <div style="padding: 0.75rem; background: #d4edda; border: 1px solid #c3e6cb; border-radius: 4px; margin-top: 0.5rem; color: #155724;">
                        <strong>✅ Deployment Successful!</strong><br>
                        <small>Model "${filename}" is now active</small>
                    </div>
                `;
                deploymentStatus.className = 'success';
                
                // Refresh displays
                await loadAvailableModels();
                await loadDeploymentHistory();
                
                setTimeout(() => {
                    deploymentStatus.innerHTML = '';
                }, 5000);
            } else {
                deploymentStatus.innerHTML = `
                    <div style="padding: 0.5rem; background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; color: #721c24;">
                        <strong>Error:</strong> ${data.error}
                    </div>
                `;
                deploymentStatus.className = 'error';
            }
        } catch (error) {
            console.error('Deployment error:', error);
            deploymentStatus.innerHTML = `
                <div style="padding: 0.5rem; background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; color: #721c24;">
                    <strong>Error:</strong> Deployment failed
                </div>
            `;
            deploymentStatus.className = 'error';
        }
    }
    
    async function rollbackModel() {
        if (!confirm('Rollback to the previous deployed model?\n\nThis will restore the last active model.')) {
            return;
        }
        
        const deploymentStatus = document.getElementById('deployment-status');
        
        try {
            deploymentStatus.textContent = '↩️ Rolling back...';
            deploymentStatus.className = 'loading';
            
            const response = await fetch('/api/models/rollback', { method: 'POST' });
            const data = await response.json();
            
            if (response.ok) {
                deploymentStatus.innerHTML = `
                    <div style="padding: 0.75rem; background: #d4edda; border: 1px solid #c3e6cb; border-radius: 4px; margin-top: 0.5rem; color: #155724;">
                        <strong>✅ Rollback Successful!</strong><br>
                        <small>Restored previous model</small>
                    </div>
                `;
                
                await loadAvailableModels();
                await loadDeploymentHistory();
                
                setTimeout(() => {
                    deploymentStatus.innerHTML = '';
                }, 5000);
            } else {
                deploymentStatus.innerHTML = `
                    <div style="padding: 0.5rem; background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; color: #721c24;">
                        <strong>Error:</strong> ${data.error}
                    </div>
                `;
            }
        } catch (error) {
            console.error('Rollback error:', error);
            deploymentStatus.innerHTML = `
                <div style="padding: 0.5rem; background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; color: #721c24;">
                    <strong>Error:</strong> Rollback failed
                </div>
            `;
        }
    }
    
    async function loadDeploymentHistory() {
        try {
            const response = await fetch('/api/models/deployment-history');
            if (!response.ok) return;
            
            const data = await response.json();
            displayDeploymentHistory(data.history);
        } catch (error) {
            console.error('Error loading deployment history:', error);
        }
    }
    
    function displayDeploymentHistory(history) {
        const container = document.getElementById('deployment-history-list');
        if (!container) return;
        
        if (!history || history.length === 0) {
            container.innerHTML = '<p style="color: #666; font-style: italic;">No deployments yet</p>';
            return;
        }
        
        container.innerHTML = '';
        history.slice(0, 5).forEach(record => {
            const item = document.createElement('div');
            item.style.cssText = 'padding: 0.5rem; background: #f8f9fa; border-left: 3px solid #0077b6; border-radius: 3px; margin-bottom: 0.5rem;';
            
            const action = record.action === 'rollback' ? '↩️ Rollback' : '🚀 Deploy';
            const modelName = record.source_model || 'Unknown';
            const timestamp = new Date(record.deployed_at).toLocaleString();
            
            item.innerHTML = `
                <p style="margin: 0; font-size: 0.85rem;"><strong>${action}</strong> ${modelName}</p>
                <p style="margin: 0.25rem 0 0 0; font-size: 0.75rem; color: #666;">${timestamp}</p>
            `;
            
            container.appendChild(item);
        });
    }

    // --- Document Classification Functions ---
    async function loadDocumentClassification() {
        try {
            const response = await fetch(`/api/document_classification/${docId}`);
            if (response.ok) {
                const classificationData = await response.json();
                updateClassificationDisplay(classificationData);
            } else {
                console.warn('Failed to load document classification');
                updateClassificationDisplay({
                    document_type: 'unknown',
                    classification_confidence: 0.0,
                    type_description: 'Document type could not be determined'
                });
            }
        } catch (error) {
            console.error('Error loading document classification:', error);
        }
    }

    function updateClassificationDisplay(data) {
        const docTypeSpan = document.getElementById('doc-type');
        const docConfidenceSpan = document.getElementById('doc-confidence');
        const docDescriptionP = document.getElementById('doc-description');

        if (docTypeSpan) {
            docTypeSpan.textContent = data.document_type.replace('_', ' ');
            docTypeSpan.className = data.document_type; // Add type-specific CSS class
        }

        if (docConfidenceSpan) {
            const confidence = data.classification_confidence || 0;
            docConfidenceSpan.textContent = `(${(confidence * 100).toFixed(1)}% confidence)`;
        }

        if (docDescriptionP) {
            docDescriptionP.textContent = data.type_description || 'No description available';
        }
    }
});
