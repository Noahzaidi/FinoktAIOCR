# Document Viewer Navigation Fix - Debug Guide

## Changes Made

### 1. JavaScript Improvements (`static/canvas.js`)
- ✅ Added comprehensive console logging for button clicks and navigation
- ✅ Added error checking to ensure all buttons exist before attaching event listeners
- ✅ Added `preventDefault()` and `stopPropagation()` to prevent event conflicts
- ✅ Improved `scrollToPage()` function with detailed logging
- ✅ Enhanced `getCurrentPageIndex()` with error handling
- ✅ Improved keyboard navigation with extensive logging

### 2. CSS Improvements (`static/style.css`)
- ✅ Added `pointer-events: auto` to navigation buttons
- ✅ Added `z-index: 10` to ensure buttons are above other elements
- ✅ Added visual feedback (scale transform) when buttons are clicked
- ✅ Ensured `.viewer-controls` container allows pointer events

## How to Test

### Step 1: Clear Browser Cache
1. Open your browser's Developer Tools (F12)
2. Right-click the refresh button → "Empty Cache and Hard Reload"
3. This ensures you're using the updated JavaScript and CSS files

### Step 2: Open the Document Viewer
1. Navigate to a document review page (e.g., `/review/<document_id>`)
2. Wait for the document to fully load

### Step 3: Open Browser Console
1. Press F12 to open Developer Tools
2. Go to the "Console" tab
3. You should see initialization messages like:
   ```
   Loading document data...
   OCR data loaded: ...
   Initializing zoom and navigation controls...
   Button elements found: {zoomIn: true, zoomOut: true, prevPage: true, nextPage: true, ...}
   ```

### Step 4: Test Navigation Buttons
Click the navigation buttons (◀ and ▶ in the "Document Viewer" header) and watch the console for:
```
Previous page button clicked
Current page: 1
Navigating to page: 0
Attempting to scroll to page 0
Found page element and viewer, scrolling...
```

### Step 5: Test Keyboard Navigation
- Press **Arrow Left** or **Arrow Right** keys
- Press **Home** or **End** keys
- Watch console for keyboard navigation logs

## Common Issues and Solutions

### Issue 1: "Button not found" errors in console
**Problem:** The HTML template might not match the expected button IDs.
**Solution:** Check that the template has these exact IDs:
- `prev-page-btn`
- `next-page-btn`
- `pan-left-btn`
- `pan-right-btn`

### Issue 2: Buttons don't respond to clicks
**Problem:** Another element might be covering the buttons (z-index issue).
**Solution:** 
1. Right-click on a navigation button → "Inspect"
2. Check if the button has these CSS properties:
   - `pointer-events: auto`
   - `z-index: 10`
   - `position: relative`

### Issue 3: "OCR data not available" or "Already on first/last page"
**Problem:** The document data hasn't loaded yet, or you're on the first/last page.
**Solution:**
1. Wait for the document to fully load (spinner should disappear)
2. Verify you have multiple pages by checking the page indicator
3. Check console for "OCR data loaded" message

### Issue 4: Keyboard navigation doesn't work
**Problem:** Focus might be in an input field, or keyboard events aren't being captured.
**Solution:**
1. Click somewhere on the page (not in a text input)
2. Make sure you're not in the "Edit Selection" tab with focus in the text editor
3. Try clicking in the document viewer area first

## Troubleshooting Commands

Run these in the browser console to manually test:

```javascript
// Check if buttons exist
console.log('Prev button:', document.getElementById('prev-page-btn'));
console.log('Next button:', document.getElementById('next-page-btn'));

// Manually trigger navigation (replace 1 with desired page number)
const viewer = document.getElementById('document-viewer-container');
const page = document.getElementById('page-container-1');
if (page && viewer) {
    page.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Check OCR data
console.log('Pages loaded:', window.ocrData ? window.ocrData.pages.length : 'No data');
```

## Expected Console Output (Successful Navigation)

When clicking "Next Page" button:
```
Next page button clicked
Current page: 0 Total pages: 3
Navigating to page: 1
Attempting to scroll to page 1
Found page element and viewer, scrolling...
Scroll calculation: relativeTop=850, viewerScrollTop=0
Scroll command issued to position: 834
Current page determined: 1
```

## If Navigation Still Doesn't Work

If after all these steps the navigation still doesn't work, please:

1. **Take a screenshot of the console** showing any errors
2. **Copy the console output** when you click a navigation button
3. **Check the Network tab** (F12 → Network) to ensure canvas.js is loading properly
4. **Verify the document has multiple pages** by checking the page indicator

## Manual Workaround

If buttons still don't work, you can navigate using:
- **Scroll wheel** in the document viewer area
- **Pages tab** in the left panel - click on "Page 1", "Page 2", etc.
- **Page indicator** at the top of the document viewer

---

## Additional Notes

The navigation system works by:
1. Detecting which page is currently visible in the viewport
2. Calculating the scroll position of the target page
3. Smoothly scrolling the viewer container to that position
4. Highlighting the target page briefly for visual feedback

If the viewer doesn't scroll but the console shows "Scroll command issued", it might be a CSS issue with the `#document-viewer-container` element's overflow properties.

