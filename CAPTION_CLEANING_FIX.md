# ISweep Caption Cleaning Fix

## Problem
The caption overlay was displaying category metadata in cleaned captions:
- Example: "profanity___" (showing both the category name AND the placeholder)
- This revealed why words were being filtered, breaking the user's viewing experience

## Solution
Implemented a comprehensive caption cleaning strategy with three layers:

### 1. Backend Changes (content_analyzer.py)
**File**: `ISweep_backend/content_analyzer.py`

- **Function**: `_mask_clean_caption_text()`
- **Change**: Updated placeholder from `____` (4 underscores) to `___` (3 underscores)
- **Benefit**: Consistent placeholder format across all masked words
- **Rule**: All filtered words/phrases → `___` (simple, clean, no metadata)

**Code Change**:
```python
# Before
masked = pattern.sub('____', masked)  # 4 underscores
return '____' if profanity.contains_profanity(word) else word

# After
masked = pattern.sub('___', masked)   # 3 underscores
return '___' if profanity.contains_profanity(word) else word
```

### 2. Frontend Category Label Stripping (youtube_captions.js)
**File**: `ISweep_extention/youtube_captions.js`

- **New Function**: `stripCategoryLabelsFromCaption(text)`
- **Purpose**: Removes any category/metadata labels that might appear in caption text
- **Patterns Removed**:
  - profanity, language, sexual, violence, crude, custom, blocked
  - filter reason, matched_category, category_name, reason:
  - Handles variations: `[profanity]`, `(language)`, `sexual___`, etc.
  
**Implementation**:
- Searches for category label patterns with surrounding brackets/parentheses
- Replaces with simple `___` placeholder
- Consolidates multiple underscores to single `___`
- Cleans up orphaned underscores at sentence boundaries

**Examples**:
```javascript
stripCategoryLabelsFromCaption('This is [profanity]___')        // → 'This is ___'
stripCategoryLabelsFromCaption('bad (language) here')          // → 'bad ___ here'
stripCategoryLabelsFromCaption('content sexual___ material')   // → 'content ___ material'
stripCategoryLabelsFromCaption('___ ___ test')                 // → 'test'
```

### 3. Updated Display Text Pipeline
**Function**: `getCleanCaptionDisplayText(entry)`

- **Change**: All returned caption text is now sanitized through `stripCategoryLabelsFromCaption()`
- **Order**:
  1. Get clean_text from backend (already masked to `___`)
  2. Strip any category labels
  3. Return sanitized display text

```javascript
// Before: no cleanup of potential category labels
if (cleanMatch) return cleanMatch.trim();

// After: sanitize for display
if (cleanMatch) return stripCategoryLabelsFromCaption(cleanMatch.trim());
```

### 4. Local Caption Masking Consistency
**Function**: `toCleanCaptionText(text)`

- **Change**: Use simple `___` placeholder for all masked words
- **Before**: `maskCaptionWord(word)` returned variable-length underscores
- **After**: Direct `'___'` replacement for consistency

```javascript
// Before
return blocked ? maskCaptionWord(word) : word;

// After  
return blocked ? '___' : word;
```

## Results

### Correct Behavior Examples
```
Input: "That was profanity word"
Output: "That was ___ word"  ✓ (No category name shown)

Input: "This is sexual content here"
Output: "This is ___ ___ here"  ✓ (All words masked, no labels)

Input: "Violence is bad"
Output: "___ is bad"  ✓ (Category not revealed)

Input: "[profanity]___"
Output: "___"  ✓ (Metadata removed)
```

### Defense-in-Depth Approach
1. **Backend**: Already masks words, now with consistent `___`
2. **Frontend**: Strips any category labels that might slip through
3. **Display**: Double-checks all text before rendering

This ensures even if backend or extension data includes category information, it's never shown to the user.

## Testing

### Backend Tests Updated
**File**: `ISweep_backend/test_content_analyzer.py`

Updated test assertions:
1. Line 202: Changed from `count('____')` to `count('___')`
2. Line 283: Changed from `'What the ____'` to `'What the ___'`

### Test Cases Covered
```python
# Test 1: Multiple words masked
'What the heck and shit is going on?' → 'What the ___ and ___ is going on?'

# Test 2: Single word masked  
'What the heck' → 'What the ___'

# Test 3: Preserve non-matching text
'Original transcript line' → 'Original transcript line'  (if no filters)
```

### Manual Testing Steps
1. **Load extension**: chrome://extensions → reload ISweep
2. **Open YouTube video** with profanity/sensitive content
3. **Enable ISweep Captions** via popup
4. **Verify overlay text**:
   - ✓ Shows `___` for blocked words
   - ✓ No category names visible
   - ✓ No filter reasons shown
   - ✓ Readable sentence structure maintained
5. **Check console**: Filter for `[ISWEEP][CAPTIONS]` logs
6. **Test with backend STT**: Verify clean_text field masked correctly

## Files Changed
1. **ISweep_backend/content_analyzer.py**
   - `_mask_clean_caption_text()`: Updated placeholder format

2. **ISweep_extention/youtube_captions.js**
   - Added `stripCategoryLabelsFromCaption()` function
   - Updated `getCleanCaptionDisplayText()` to sanitize text
   - Updated `toCleanCaptionText()` to use consistent `___` placeholder

3. **ISweep_backend/test_content_analyzer.py**
   - Updated test assertions for new placeholder format

## Backwards Compatibility
- ✓ No API changes
- ✓ No schema changes
- ✓ Filtering decisions still work (mute/skip/fast_forward unaffected)
- ✓ Only display text is sanitized, internal data unchanged
- ✓ Existing preferences and markers still valid

## Console Logging
All caption overlay operations log with `[ISWEEP][CAPTIONS]` prefix for debugging:
```
[ISWEEP][CAPTIONS] overlay created
[ISWEEP][CAPTIONS] text updated
[ISWEEP][CAPTIONS] source audio_stt
```

The new `stripCategoryLabelsFromCaption()` function doesn't log category removals to avoid verbose output, but any actual category names in source data would be silently cleaned.

## Future Enhancements
- Consider sanitizing category labels at backend (prevent them entering system entirely)
- Add metrics logging for how often category labels were stripped (for monitoring)
- Extend to handle translation/localization of category names
