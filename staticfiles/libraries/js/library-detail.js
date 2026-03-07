/* =================================================================
   Bookworm: Little Library Finder — Shared Library Detail JS
   =================================================================
   Provides: Shelfie lightbox, photo reporting, toast notifications,
   keyboard/swipe navigation, HTMX success handling.
   Imported by: map.html, library_detail_page.html
   ================================================================= */

// =================================================================
// Shelfie Lightbox
// =================================================================
let currentShelfieIndex = 0;
let shelfieCards = [];

function openShelfieViewer(card) {
    shelfieCards = Array.from(document.querySelectorAll('#shelfie-carousel .shelfie-card'));
    currentShelfieIndex = parseInt(card.dataset.shelfieIndex);

    updateLightboxContent();
    document.getElementById('shelfie-lightbox').classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeShelfieViewer() {
    const lightbox = document.getElementById('shelfie-lightbox');
    if (lightbox) {
        lightbox.classList.remove('active');
    }
    document.body.style.overflow = '';
}

function navigateShelfie(direction) {
    currentShelfieIndex += direction;

    // Wrap around
    if (currentShelfieIndex < 0) {
        currentShelfieIndex = shelfieCards.length - 1;
    } else if (currentShelfieIndex >= shelfieCards.length) {
        currentShelfieIndex = 0;
    }

    updateLightboxContent();
}

function updateLightboxContent() {
    const card = shelfieCards[currentShelfieIndex];
    if (!card) return;

    const lightbox = document.getElementById('shelfie-lightbox');
    if (!lightbox) return;

    // Update image
    const img = document.getElementById('lightbox-image');
    if (img) {
        img.src = card.dataset.shelfieUrl;
    }

    // Update counter
    const counter = document.getElementById('lightbox-counter');
    if (counter) {
        counter.textContent = `${currentShelfieIndex + 1} / ${shelfieCards.length}`;
    }

    // Update date
    const dateEl = document.getElementById('lightbox-date');
    if (dateEl) {
        dateEl.textContent = card.dataset.shelfieDate;
    }

    // Update highlights
    const highlightsEl = document.getElementById('lightbox-highlights');
    if (highlightsEl) {
        if (card.dataset.shelfieHighlights) {
            highlightsEl.textContent = card.dataset.shelfieHighlights;
            highlightsEl.style.display = 'block';
        } else {
            highlightsEl.style.display = 'none';
        }
    }

    // Update report button data attribute
    const reportBtn = document.getElementById('lightbox-report-btn');
    if (reportBtn) {
        reportBtn.dataset.shelfiePk = card.dataset.shelfiePk;
    }

    // Update nav button visibility
    const prevBtn = lightbox.querySelector('.shelfie-lightbox-prev');
    const nextBtn = lightbox.querySelector('.shelfie-lightbox-next');

    if (prevBtn && nextBtn) {
        if (shelfieCards.length <= 1) {
            prevBtn.style.display = 'none';
            nextBtn.style.display = 'none';
        } else {
            prevBtn.style.display = 'flex';
            nextBtn.style.display = 'flex';
        }
    }
}

// =================================================================
// Shelfie Photo Reporting
// =================================================================
function openShelfieReport(shelfiePk) {
    // Close lightbox if open
    closeShelfieViewer();

    // Use HTMX to load the report form
    const targetEl = document.getElementById('library-detail-content');
    if (targetEl) {
        htmx.ajax('GET', '/shelfie/' + shelfiePk + '/report/form/', {
            target: '#library-detail-content',
            swap: 'innerHTML'
        });
    }
}

// Report current shelfie from lightbox
function reportCurrentShelfie() {
    const reportBtn = document.getElementById('lightbox-report-btn');
    if (reportBtn && reportBtn.dataset.shelfiePk) {
        openShelfieReport(reportBtn.dataset.shelfiePk);
    }
}

// =================================================================
// Keyboard Navigation for Lightbox
// =================================================================
document.addEventListener('keydown', function(e) {
    const lightbox = document.getElementById('shelfie-lightbox');
    if (!lightbox || !lightbox.classList.contains('active')) return;

    if (e.key === 'Escape') {
        closeShelfieViewer();
    } else if (e.key === 'ArrowLeft') {
        navigateShelfie(-1);
    } else if (e.key === 'ArrowRight') {
        navigateShelfie(1);
    }
});

// =================================================================
// Touch/Swipe Support for Mobile Lightbox
// =================================================================
let touchStartX = 0;
let touchEndX = 0;

document.addEventListener('touchstart', function(e) {
    const lightbox = document.getElementById('shelfie-lightbox');
    if (!lightbox || !lightbox.classList.contains('active')) return;
    touchStartX = e.changedTouches[0].screenX;
}, { passive: true });

document.addEventListener('touchend', function(e) {
    const lightbox = document.getElementById('shelfie-lightbox');
    if (!lightbox || !lightbox.classList.contains('active')) return;

    touchEndX = e.changedTouches[0].screenX;
    const diff = touchStartX - touchEndX;

    if (Math.abs(diff) > 50) {
        if (diff > 0) {
            navigateShelfie(1);
        } else {
            navigateShelfie(-1);
        }
    }
}, { passive: true });

// =================================================================
// Toast Notification Utility
// =================================================================
function showToast(message, type = 'success') {
    const toast = document.getElementById('successToast');
    const toastMessage = document.getElementById('toast-message');

    const bgClasses = {
        'success': 'bg-success',
        'danger': 'bg-danger',
        'warning': 'bg-warning text-dark'
    };

    toast.className = `toast align-items-center text-white border-0 ${bgClasses[type] || bgClasses.success}`;
    toastMessage.textContent = message;

    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();
}

// =================================================================
// HTML Escape Utility
// =================================================================
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}