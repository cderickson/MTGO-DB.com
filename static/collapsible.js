/**
 * Collapsible Tab Functionality
 * Handles expanding/collapsing of tab content with smooth animations
 */

document.addEventListener('DOMContentLoaded', function() {
    initializeCollapsibleTabs();
});

function initializeCollapsibleTabs() {
    const collapsibleTabs = document.querySelectorAll('.collapsible-tab');
    
    collapsibleTabs.forEach(tab => {
        const header = tab.querySelector('.section-card-header');
        const content = tab.querySelector('.section-card-content');
        
        if (!header || !content) return;
        
        // Make header focusable for accessibility
        header.setAttribute('tabindex', '0');
        header.setAttribute('role', 'button');
        header.setAttribute('aria-expanded', 'false');
        
        // Set up ARIA labels
        const title = header.querySelector('.section-card-title');
        if (title) {
            const titleText = title.textContent.trim();
            header.setAttribute('aria-label', `Toggle ${titleText} section`);
        }
        
        // Add click event listener
        header.addEventListener('click', function(e) {
            e.preventDefault();
            toggleTab(tab);
        });
        
        // Add keyboard event listener for accessibility
        header.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                toggleTab(tab);
            }
        });
        
        // Initialize: expand if has 'expanded' class, otherwise collapse
        if (tab.classList.contains('expanded')) {
            expandTab(tab, false);
        } else {
            collapseTab(tab, false);
        }
    });
}

function toggleTab(tab) {
    if (tab.classList.contains('expanded')) {
        collapseTab(tab, true);
    } else {
        expandTab(tab, true);
    }
}

function expandTab(tab, animate = true) {
    const header = tab.querySelector('.section-card-header');
    const content = tab.querySelector('.section-card-content');
    
    if (!animate) {
        // Instant expand (for initialization)
        tab.classList.add('expanded');
        header.setAttribute('aria-expanded', 'true');
        content.style.maxHeight = 'none';
        content.style.opacity = '1';
        content.style.padding = '20px';
        return;
    }
    
    // Animated expand
    tab.classList.add('expanded');
    header.setAttribute('aria-expanded', 'true');
    
    // Calculate the full height of content
    const fullHeight = content.scrollHeight;
    
    // Set explicit height for smooth animation
    content.style.maxHeight = fullHeight + 'px';
    content.style.opacity = '1';
    content.style.padding = '20px';
    
    // Clean up after animation completes
    setTimeout(() => {
        if (tab.classList.contains('expanded')) {
            content.style.maxHeight = 'none';
        }
    }, 400);
}

function collapseTab(tab, animate = true) {
    const header = tab.querySelector('.section-card-header');
    const content = tab.querySelector('.section-card-content');
    
    if (!animate) {
        // Instant collapse (for initialization)
        tab.classList.remove('expanded');
        header.setAttribute('aria-expanded', 'false');
        content.style.maxHeight = '0';
        content.style.opacity = '0';
        content.style.padding = '0 20px';
        return;
    }
    
    // Get current height before starting animation
    const currentHeight = content.scrollHeight;
    content.style.maxHeight = currentHeight + 'px';
    
    // Force reflow to ensure the height is applied
    content.offsetHeight;
    
    // Start collapse animation
    tab.classList.remove('expanded');
    header.setAttribute('aria-expanded', 'false');
    content.style.maxHeight = '0';
    content.style.opacity = '0';
    content.style.padding = '0 20px';
}

// Utility function to expand all tabs (useful for testing or "expand all" feature)
function expandAllTabs() {
    const collapsibleTabs = document.querySelectorAll('.collapsible-tab');
    collapsibleTabs.forEach(tab => expandTab(tab, true));
}

// Utility function to collapse all tabs
function collapseAllTabs() {
    const collapsibleTabs = document.querySelectorAll('.collapsible-tab');
    collapsibleTabs.forEach(tab => collapseTab(tab, true));
}

// Export functions for potential external use
window.CollapsibleTabs = {
    expandTab,
    collapseTab,
    toggleTab,
    expandAllTabs,
    collapseAllTabs,
    initializeCollapsibleTabs
};