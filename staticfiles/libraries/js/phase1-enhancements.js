/**
 * Bookworm Phase 1 - JavaScript Enhancements
 * ==========================================
 *
 * Features:
 * 1. Upload progress indicators (HTMX events)
 * 2. Client-side image validation
 * 3. Image preview before upload
 * 4. Address search with Nominatim
 * 5. Error handling with retry
 *
 * Dependencies:
 * - CONFIG object (defined in map.html)
 * - showToast() function (defined in map.html)
 * - setSubmitLocation() function (defined in map.html)
 * - submitLocationPicker variable (defined in map.html)
 * - Bootstrap 5
 * - HTMX
 */

// =============================================================================
// 0. HTMX CONFIGURATION - Allow swapping on specific error codes
// =============================================================================

document.body.addEventListener('htmx:beforeSwap', function(evt) {
    // Allow content swap on these status codes (they return valid HTML)
    const allowSwapCodes = [400, 422, 429];

    if (allowSwapCodes.includes(evt.detail.xhr.status)) {
        evt.detail.shouldSwap = true;
        evt.detail.isError = false;
    }
});


// =============================================================================
// 1. UPLOAD PROGRESS INDICATORS
// =============================================================================

let uploadStartTime = null;
const MIN_PROGRESS_DISPLAY_MS = 1500; // Show progress for at least 1.5 seconds

document.body.addEventListener('htmx:xhr:loadstart', function(evt) {
    const form = evt.detail.elt;
    if (form && form.querySelector && form.querySelector('input[type="file"]')) {
        uploadStartTime = Date.now();
        showUploadProgress(form, 0);
    }
});

document.body.addEventListener('htmx:xhr:progress', function(evt) {
    if (evt.detail.lengthComputable) {
        const form = evt.detail.elt;
        if (form && form.querySelector && form.querySelector('input[type="file"]')) {
            const percent = Math.round((evt.detail.loaded / evt.detail.total) * 100);
            showUploadProgress(form, percent);
        }
    }
});

document.body.addEventListener('htmx:xhr:loadend', function(evt) {
    const form = evt.detail.elt;
    if (form && form.querySelector && form.querySelector('input[type="file"]')) {
        // Show "Processing..." state
        showUploadProgress(form, 100);

        // Calculate how long to wait before hiding
        const elapsed = Date.now() - uploadStartTime;
        const remainingTime = Math.max(0, MIN_PROGRESS_DISPLAY_MS - elapsed);

        // Wait for minimum display time, then hide
        setTimeout(() => {
            hideUploadProgress();
        }, remainingTime);
    } else {
        hideUploadProgress();
    }
});

document.body.addEventListener('htmx:responseError', function(evt) {
    // Skip rate limit responses - they have their own UI
    if (evt.detail.xhr) {
        const status = evt.detail.xhr.status;
        if (status==429 || status==400 || status==422) {
            return;
        }
    }

    const form = evt.detail.elt;
    if (form && form.querySelector && form.querySelector('input[type="file"]')) {
        hideUploadProgress();
        showRetryOption(form, 'Upload failed. Please check your connection and try again.');
    }
});

document.body.addEventListener('htmx:sendError', function(evt) {
    const form = evt.detail.elt;
    if (form && form.querySelector && form.querySelector('input[type="file"]')) {
        hideUploadProgress();
        showRetryOption(form, 'Network error. Please check your connection and try again.');
    }
});

function showUploadProgress(form, percent) {
    let progressContainer = form.querySelector('.upload-progress-container');

    if (!progressContainer) {
        progressContainer = document.createElement('div');
        progressContainer.className = 'upload-progress-container mb-3';
        progressContainer.innerHTML = `
            <div class="upload-progress-bar-container" style="
                height: 6px;
                background: var(--color-neutral-200);
                border-radius: var(--radius-full);
                overflow: hidden;
                margin-bottom: 8px;
            ">
                <div class="upload-progress-bar" style="
                    height: 100%;
                    background: linear-gradient(90deg, var(--color-primary-500), var(--color-primary-600));
                    border-radius: var(--radius-full);
                    width: 0%;
                    transition: width 0.3s ease;
                "></div>
            </div>
            <div class="upload-status" style="
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 0.875rem;
                color: var(--color-neutral-600);
            ">
                <div class="spinner-border spinner-border-sm" role="status" style="
                    width: 1rem;
                    height: 1rem;
                    color: var(--color-primary-600);
                "></div>
                <span class="status-text">Uploading...</span>
            </div>
        `;

        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.parentNode.insertBefore(progressContainer, submitBtn);
            submitBtn.disabled = true;
        }
    }

    const bar = progressContainer.querySelector('.upload-progress-bar');
    const status = progressContainer.querySelector('.status-text');

    if (percent < 100) {
        bar.style.width = `${percent}%`;
        status.textContent = `Uploading... ${percent}%`;
    } else {
        bar.style.width = '100%';
        bar.style.background = 'linear-gradient(90deg, var(--color-fresh), #16a34a)';
        status.textContent = 'Optimizing image...';
    }
}

function hideUploadProgress() {
    document.querySelectorAll('.upload-progress-container').forEach(el => el.remove());
    document.querySelectorAll('button[type="submit"]').forEach(btn => {
        btn.disabled = false;
    });
}

function showRetryOption(form, message) {
    if (typeof showToast === 'function') {
        showToast(message, 'danger');
    }

    const submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="bi bi-arrow-clockwise me-2"></i>Retry Upload';
        submitBtn.classList.add('btn-warning');
        submitBtn.classList.remove('btn-primary');
    }
}


// =============================================================================
// 2. CLIENT-SIDE IMAGE VALIDATION
// =============================================================================

document.body.addEventListener('change', function(evt) {
    if (evt.target.type === 'file' && evt.target.accept && evt.target.accept.includes('image')) {
        validateAndPreviewImage(evt.target);
    }
});

function validateAndPreviewImage(input) {
    const file = input.files[0];
    if (!file) return true;

    const maxSizeMB = (typeof CONFIG !== 'undefined' && CONFIG.maxUploadSizeMB) || 10;
    const maxSize = maxSizeMB * 1024 * 1024;

    // Allowed types (include HEIC for iOS)
    const allowedTypes = [
        'image/jpeg', 'image/jpg', 'image/png', 'image/gif',
        'image/webp', 'image/heic', 'image/heif'
    ];
    const allowedExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif'];

    // Check file size
    if (file.size > maxSize) {
        if (typeof showToast === 'function') {
            showToast(`Image too large. Maximum size is ${maxSizeMB}MB. Your file is ${(file.size / (1024 * 1024)).toFixed(1)}MB.`, 'danger');
        }
        input.value = '';
        clearImagePreview(input);
        return false;
    }

    // Check file type (be lenient for iOS which may report different MIME types)
    const fileType = (file.type || '').toLowerCase();
    const fileName = (file.name || '').toLowerCase();
    const hasValidType = allowedTypes.some(t => fileType.includes(t.split('/')[1]));
    const hasValidExt = allowedExtensions.some(ext => fileName.endsWith(ext));

    if (!hasValidType && !hasValidExt) {
        if (typeof showToast === 'function') {
            showToast('Please select a valid image file (JPEG, PNG, GIF, or WebP).', 'danger');
        }
        input.value = '';
        clearImagePreview(input);
        return false;
    }

    // Show preview
    showImagePreview(input, file);
    return true;
}


// =============================================================================
// 3. IMAGE PREVIEW
// =============================================================================

function showImagePreview(input, file) {
    const form = input.closest('form');
    if (!form) return;

    // Find or create preview container
    let previewContainer = form.querySelector('.image-preview-container');

    if (!previewContainer) {
        previewContainer = document.createElement('div');
        previewContainer.className = 'image-preview-container mb-3';
        previewContainer.innerHTML = `
            <div style="position: relative; display: inline-block;">
                <img class="image-preview" alt="Preview" style="
                    max-width: 100%;
                    max-height: 200px;
                    object-fit: cover;
                    border-radius: var(--radius-md);
                    border: 2px solid var(--color-neutral-200);
                    display: none;
                ">
                <button type="button" class="btn-close-preview" aria-label="Remove image" style="
                    position: absolute;
                    top: 8px;
                    right: 8px;
                    width: 28px;
                    height: 28px;
                    border-radius: 50%;
                    background: rgba(0,0,0,0.6);
                    border: none;
                    color: white;
                    cursor: pointer;
                    display: none;
                    font-size: 14px;
                    line-height: 1;
                ">&times;</button>
            </div>
        `;
        input.parentNode.insertBefore(previewContainer, input.nextSibling);

        // Add click handler to remove preview
        previewContainer.querySelector('.btn-close-preview').addEventListener('click', function() {
            input.value = '';
            clearImagePreview(input);
        });
    }

    const preview = previewContainer.querySelector('.image-preview');
    const closeBtn = previewContainer.querySelector('.btn-close-preview');

    const reader = new FileReader();
    reader.onload = function(e) {
        preview.src = e.target.result;
        preview.style.display = 'block';
        closeBtn.style.display = 'block';
    };
    reader.readAsDataURL(file);
}

function clearImagePreview(input) {
    const form = input.closest('form');
    if (!form) return;

    const previewContainer = form.querySelector('.image-preview-container');
    if (previewContainer) {
        const preview = previewContainer.querySelector('.image-preview');
        const closeBtn = previewContainer.querySelector('.btn-close-preview');
        if (preview) {
            preview.src = '';
            preview.style.display = 'none';
        }
        if (closeBtn) {
            closeBtn.style.display = 'none';
        }
    }
}


// =============================================================================
// 4. ADDRESS SEARCH (Nominatim Integration)
// =============================================================================

let addressSearchTimeout = null;

function initAddressSearch() {
    const searchInput = document.getElementById('address-search-input');
    const searchResults = document.getElementById('address-search-results');

    if (!searchInput || !searchResults) return;

    searchInput.addEventListener('input', function(e) {
        const query = e.target.value.trim();

        // Clear previous timeout
        if (addressSearchTimeout) {
            clearTimeout(addressSearchTimeout);
        }

        // Hide results if query too short
        if (query.length < 3) {
            searchResults.style.display = 'none';
            return;
        }

        // Debounce search (500ms)
        addressSearchTimeout = setTimeout(function() {
            searchAddress(query);
        }, 500);
    });

    // Close results when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.address-search-container')) {
            searchResults.style.display = 'none';
        }
    });
}

async function searchAddress(query) {
    const searchResults = document.getElementById('address-search-results');
    const geocodeUrl = (typeof CONFIG !== 'undefined' && CONFIG.geocodeUrl) || '/api/geocode/';

    // Show loading state
    searchResults.innerHTML = '<div class="p-3 text-center"><span class="spinner-border spinner-border-sm me-2"></span>Searching...</div>';
    searchResults.style.display = 'block';

    try {
        const response = await fetch(`${geocodeUrl}?q=${encodeURIComponent(query)}`);
        const data = await response.json();

        if (data.error) {
            searchResults.innerHTML = `<div class="p-3 text-muted">${escapeHtml(data.error)}</div>`;
            return;
        }

        if (!data.results || data.results.length === 0) {
            searchResults.innerHTML = `<div class="p-3 text-muted">${data.message || 'No results found. Try placing a pin manually.'}</div>`;
            return;
        }

        // Render results
        searchResults.innerHTML = data.results.map(function(r) {
            return `
                <div class="address-result-item"
                     data-lat="${r.lat}"
                     data-lng="${r.lon}"
                     style="padding: 12px 16px; cursor: pointer; border-bottom: 1px solid var(--color-neutral-200); font-size: 0.9rem;">
                    ${escapeHtml(r.display_name)}
                </div>
            `;
        }).join('');

        // Add click handlers
        searchResults.querySelectorAll('.address-result-item').forEach(function(item) {
            item.addEventListener('click', function() {
                const lat = parseFloat(this.dataset.lat);
                const lng = parseFloat(this.dataset.lng);
                const address = this.textContent.trim();

                // Call the existing setSubmitLocation function from map.html
                if (typeof setSubmitLocation === 'function') {
                    setSubmitLocation(lat, lng);
                }

                // Update search input
                document.getElementById('address-search-input').value = address;

                // Hide results
                searchResults.style.display = 'none';

                // Pan map to location
                if (typeof submitLocationPicker !== 'undefined' && submitLocationPicker) {
                    submitLocationPicker.setView([lat, lng], 17);
                }
            });

            // Hover effect
            item.addEventListener('mouseenter', function() {
                this.style.background = 'var(--color-neutral-100)';
            });
            item.addEventListener('mouseleave', function() {
                this.style.background = 'white';
            });
        });

    } catch (error) {
        console.error('Address search error:', error);
        searchResults.innerHTML = '<div class="p-3 text-muted">Search unavailable. Please place a pin manually.</div>';
    }
}


// =============================================================================
// 5. INITIALIZATION
// =============================================================================

// Initialize address search when submit form loads via HTMX
document.body.addEventListener('htmx:afterSwap', function(event) {
    if (event.detail.target.id === 'submit-form-container') {
        setTimeout(initAddressSearch, 150);
    }
});

// Also initialize if form is already present on page load
document.addEventListener('DOMContentLoaded', function() {
    initAddressSearch();
});
