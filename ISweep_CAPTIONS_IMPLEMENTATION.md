# ISweep Captions Feature Implementation

## Overview
ISweep Captions is a separate feature from filtering actions that displays cleaned captions in a movable overlay. The feature captures audio from any tab, processes it through the backend for transcription, and displays the cleaned results in a customizable overlay.

## Files Changed
1. **ISweep_extention/audio_chunk_processor.js**
   - Added comprehensive comments explaining:
     - Processor only captures audio chunks (no STT)
     - Workflow: PCM chunks → main thread → backend STT → overlay
     - Safe placeholder behavior if STT is not connected
     - Clarification that this is not a speech-to-text model

2. **ISweep_extention/youtube_captions.js**
   - Updated logging prefix from `[ISWEEP][CLEAN_CC]` to `[ISWEEP][CAPTIONS]`
   - All caption logging now uses consistent `[ISWEEP][CAPTIONS]` prefix

## Existing Implementation Details

### Storage Keys
- **isweepCleanCaptionSettings**: Stored object containing:
  - `cleanCaptionsEnabled` (boolean): Toggle for caption display (default: true)
  - `cleanCaptionStyle` (string): 'transparent_white' or 'white_black' (default: 'transparent_white')
  - `cleanCaptionTextSize` (string): 'small', 'medium', or 'large' (default: 'medium')
  - `cleanCaptionPosition` (object): {x: 0-1, y: 0-1} normalized position (default: {x: 0.5, y: 0.8})

### Popup Controls (popup.html/popup.js/popup.css)
1. **Caption Toggle [CC] Button**
   - Toggles `cleanCaptionsEnabled` on/off
   - Visual feedback: cyan background when enabled
   - Located in top of logged-in panel

2. **Settings Dropdown (•)**
   - Expands/collapses settings panel
   - Controls:
     - **Style**: Dropdown selecting 'transparent_white' vs 'white_black'
     - **Text Size**: Dropdown selecting 'small', 'medium', or 'large'
     - **Reset Position**: Button to restore default bottom-center position

### Caption Overlay (youtube_captions.js)
- **Element**: Fixed-position div (`#isweep-caption-overlay`)
- **Position**: Default bottom-center of page (normalized x=0.5, y=0.8)
- **Draggable**: Click and drag to reposition; position saved to storage
- **Z-Index**: 2147483647 (maximum to stay above all content)
- **Styling**:
  - **Transparent Mode**: White text on semi-transparent dark background (rgba(0,0,0,0.30))
  - **Solid Mode**: Black text on white background (rgba(255,255,255,0.96))
  - **Font Size**: Maps to CSS (small=14px, medium=18px, large=24px)
  - **Padding**: 10px horizontal, 14px vertical
  - **Border Radius**: 10px
  - **Shadow**: 0 2px 10px rgba(0,0,0,0.22)

### Caption Text Sources (Priority Order)
1. Pre-analyzed captions from backend
2. Marker text from backend
3. Pre-cached audio STT results
4. Live audio STT results
5. Live masked text (YouTube native captions with filters applied)
6. Placeholder: "ISweep captions listening..."

### Integration Flow
1. **Initialization**: 
   - Page loads → `youtube_captions.js` initializes
   - `loadCleanCaptionSettingsFromStorage()` loads settings
   - `ensureCleanCaptionOverlay()` creates overlay element
   - Initial text shows placeholder or YouTube caption text

2. **Real-time Updates**:
   - YouTube native captions change → `updateCleanOverlay()` called
   - Backend STT results arrive → overlay text updates
   - `updateCleanOverlay()` checks best available caption source

3. **Settings Changes**:
   - User changes popup controls → settings saved to storage
   - **Path A** (Fast): Popup sends `isweep_clean_caption_settings_changed` message
     - youtube_captions.js message listener receives message
     - `applyCleanCaptionOverlayStyles()` applies new styles immediately
   - **Path B** (Fallback): Storage change event listener
     - Detects `isweepCleanCaptionSettings` change
     - Updates `cleanCaptionSettings` and applies styles

4. **Drag Interaction**:
   - User drags overlay
   - Position converted to normalized coordinates (0-1 range)
   - Position saved to storage under `cleanCaptionPosition`
   - Next page load restores position

### Audio Capture Pipeline
1. **AudioWorklet Processor** (audio_chunk_processor.js)
   - Captures 128-sample PCM quantums from Web Audio API
   - Posts Float32 chunks to main thread
   - Does NOT perform transcription (audio capture only)

2. **Main Thread Accumulation** (youtube_captions.js)
   - Collects audio chunks into buffers
   - When buffer is ready (every ~2 seconds)

3. **Backend Processing**
   - Main thread POSTs buffer to `/audio/analyze` endpoint
   - Backend performs speech-to-text
   - Returns `cleaned_captions` array or `cleaned_text`

4. **Overlay Display**
   - Cleaned text rendered in overlay
   - Falls back to YouTube native captions if STT not available
   - Shows placeholder if no text available

### Default Behavior
- **On Enable**: Overlay appears with "ISweep captions listening..."
- **Native YouTube Captions Available**: Overlay shows cleaned/masked caption text
- **STT Processing**: Overlay updates with transcribed and cleaned text
- **On Disable**: Overlay hidden (stays in DOM, display: none)
- **Position Reset**: Click "Reset caption position" to return to bottom-center

## Testing Instructions

### 1. Setup
```bash
# Reload extension in chrome://extensions
# Ensure backend is running (http://127.0.0.1:5000 or configured URL)
```

### 2. Basic Overlay Test
1. Open YouTube video page (youtube.com/watch?v=...)
2. Open extension popup
3. Verify `[CC]` button exists in logged-in panel
4. Verify `•` settings button exists
5. Click `[CC]` button → Caption toggle should work
6. Confirm overlay appears at bottom-center of page
7. Default text should show: "ISweep captions listening..."

### 3. YouTube Caption Integration
1. Open YouTube video with available captions
2. Enable YouTube captions (CC button)
3. Extension overlay should display the same caption text as YouTube
4. Toggle extension `[CC]` off → Overlay should hide
5. Toggle `[CC]` on → Overlay should reappear

### 4. Style Changes
1. Click `•` button to expand settings
2. Change **Style** from "Transparent + White" to "White + Black"
3. Observe:
   - Background changes to white
   - Text changes to dark/black color
4. Change back to "Transparent + White"
5. Observe:
   - Background changes to dark semi-transparent
   - Text changes to white

### 5. Font Size Changes
1. With settings panel open, change **Text size**
2. Try "Small" (14px) → Text should be smaller
3. Try "Large" (24px) → Text should be larger
4. Try "Medium" (18px) → Return to default size
5. Observe smooth transitions and readable sizes

### 6. Dragging and Position
1. Click and drag the overlay to a new position
2. Refresh the page (F5)
3. Overlay should appear at the dragged position (not reset)
4. Click "Reset caption position" button
5. After refresh, overlay should return to bottom-center

### 7. Existing Filtering Not Affected
1. Ensure mute/skip/fast-forward buttons still work
2. Verify filtering decisions are applied
3. Captions should remain visible even when audio is muted
4. Muting video should NOT hide captions

### 8. Console Logging
Open DevTools Console (F12) and filter by `[ISWEEP][CAPTIONS]`:
```
[ISWEEP][CAPTIONS] overlay created        # When first loaded
[ISWEEP][CAPTIONS] overlay enabled        # When user enables captions
[ISWEEP][CAPTIONS] placeholder shown      # When waiting for real text
[ISWEEP][CAPTIONS] text updated           # When caption text changes
[ISWEEP][CAPTIONS] style applied          # When style changes
[ISWEEP][CAPTIONS] size applied           # When size changes
[ISWEEP][CAPTIONS] drag start             # When user starts dragging
[ISWEEP][CAPTIONS] drag saved             # When user releases overlay
[ISWEEP][CAPTIONS] stale clear            # When captions become stale
```

### 9. Audio STT Pipeline (Future)
When backend STT is fully configured:
1. Console should show:
   ```
   [ISWEEP][CAPTIONS] source audio_stt  # When STT text available
   ```
2. Overlay text should come from transcribed audio
3. Cleaned text should reflect content policies

### 10. Placeholder Behavior
If backend STT is NOT configured:
1. Overlay still appears
2. Shows "ISweep captions listening..."
3. No errors in console
4. Feature gracefully degrades
5. Console logs indicate STT not connected (in `[ISWEEP][AUDIO_AHEAD]`)

## Architecture Notes

### Why Minimal Diffs?
- Caption overlay was already substantially implemented
- Focused on:
  1. Clarifying AudioWorklet purpose (comments)
  2. Standardizing logging prefix
  3. Verifying complete integration
- Avoided refactoring existing working code

### Storage Strategy
- Settings stored locally in extension (not backend)
- Avoids extra API calls for UI preferences
- Position persists across page reloads
- All settings have sensible defaults

### Fallback Mechanisms
1. **Message Passing Fails** → Storage change listener applies styles
2. **Settings Not Found** → Use hardcoded defaults
3. **No STT Available** → Show placeholder text
4. **Video Element Missing** → Overlay still created, waits for video

### Performance Considerations
- Overlay hidden by `display: none` when disabled (not removed from DOM)
- Caption text updates use opacity fade (CSS transition)
- Drag interactions use `pointerEvents` for efficiency
- Audio chunks accumulated in background (doesn't block UI)

## Known Limitations
1. **Size Options**: Preset values (small/medium/large) not fully numeric
2. **Position**: Normalized coordinates (0-1) stored, not pixel coordinates
3. **Style Names**: Uses 'transparent_white'/'white_black' terminology
4. **YouTube Only**: Overlay hooks into YouTube caption system
5. **Audio STT**: Requires backend `/audio/analyze` endpoint

## Future Enhancements
1. Custom numeric font sizes (8-64px slider)
2. Position presets (top, center, bottom)
3. Opacity control
4. Support for other caption sources (non-YouTube)
5. Transcript export functionality
6. Caption history panel
7. Word-by-word timing visualization

## Troubleshooting

### Overlay Not Appearing
1. Check extension is enabled in chrome://extensions
2. Verify `isweepCaptionsEnabled` is true in storage
3. Open DevTools and check for `[ISWEEP][CAPTIONS]` logs
4. Ensure page has video element

### Overlay Shows Placeholder Only
1. Check backend STT is configured and running
2. Verify `/audio/analyze` endpoint is accessible
3. Check `[ISWEEP][AUDIO]` logs for STT failures
4. Ensure browser has permission to access microphone

### Settings Not Applying
1. Check popup message passed successfully
2. Verify storage listener is active (F12 → Application → Storage)
3. Try refreshing page to trigger storage listener
4. Check browser console for any JavaScript errors

### Overlay Stuck at Bad Position
1. Click "Reset caption position" button
2. Reload extension in chrome://extensions
3. Close and reopen browser tab

## References
- AudioWorklet API: https://developer.mozilla.org/en-US/docs/Web/API/AudioWorkletProcessor
- Chrome Storage API: https://developer.chrome.com/docs/extensions/reference/storage/
- Web Audio API: https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API
