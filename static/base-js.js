// MTGO-DB Base JavaScript - Professional Sidebar Layout

// Sidebar Management
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const mainContent = document.getElementById('main-content');
  
  if (sidebar && overlay) {
    const isCurrentlyOpen = sidebar.classList.contains('show');
    
    if (isCurrentlyOpen) {
      // Close sidebar
      sidebar.classList.remove('show');
      overlay.classList.remove('show');
      document.body.style.overflow = '';
    } else {
      // Open sidebar
      sidebar.classList.add('show');
      overlay.classList.add('show');
      
      // Only prevent body scroll on mobile
      if (window.innerWidth <= 768) {
        document.body.style.overflow = 'hidden';
      }
    }
  }
}

function closeSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  
  if (sidebar && overlay) {
    sidebar.classList.remove('show');
    overlay.classList.remove('show');
    document.body.style.overflow = '';
  }
}

// User Dropdown Management
function toggleUserDropdown() {
  const userInfo = document.querySelector('.user-info');
  const userDropdown = document.getElementById('user-dropdown');
  const userChevron = document.querySelector('.user-chevron');
  
  if (userInfo && userDropdown) {
    const isActive = userInfo.classList.contains('active');
    
    userInfo.classList.toggle('active');
    userDropdown.classList.toggle('show');
    
    if (userChevron) {
      userChevron.style.transform = isActive ? 'rotate(0deg)' : 'rotate(180deg)';
    }
  }
}

// Close user dropdown when clicking outside
document.addEventListener('click', function(event) {
  const userMenu = document.querySelector('.user-menu');
  const userDropdown = document.getElementById('user-dropdown');
  const userInfo = document.querySelector('.user-info');
  
  if (userMenu && !userMenu.contains(event.target)) {
    if (userDropdown && userInfo) {
      userDropdown.classList.remove('show');
      userInfo.classList.remove('active');
      
      const userChevron = document.querySelector('.user-chevron');
      if (userChevron) {
        userChevron.style.transform = 'rotate(0deg)';
      }
    }
  }
});

// Set Active Navigation Link
function setActiveNavLink() {
  const currentPath = window.location.pathname;
  const navLinks = document.querySelectorAll('.nav-link');
  
  navLinks.forEach(link => {
    link.classList.remove('active');
    
    // Skip links that are placeholders or use onclick handlers
    const href = link.getAttribute('href');
    if (!href || href === '#' || href.startsWith('#') || link.hasAttribute('onclick')) {
      return; // Skip this link
    }
    
    try {
      // Check if the link href matches the current path
      const linkPath = new URL(link.href).pathname;
      if (linkPath === currentPath) {
        link.classList.add('active');
      }
    } catch (e) {
      // Skip invalid URLs
      return;
    }
  });
}

// Responsive Sidebar Handling
function handleResize() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  
  if (window.innerWidth > 768) {
    // Desktop: Always show sidebar, hide overlay, restore body scroll
    if (sidebar) sidebar.classList.remove('show');
    if (overlay) overlay.classList.remove('show');
    document.body.style.overflow = '';
  }
}

// Ensure body overflow is properly reset
function resetBodyOverflow() {
  // Always ensure body can scroll normally on page load
  document.body.style.overflow = '';
  
  // Only apply overflow hidden if sidebar is actually open on mobile
  const sidebar = document.getElementById('sidebar');
  if (sidebar && sidebar.classList.contains('show') && window.innerWidth <= 768) {
    document.body.style.overflow = 'hidden';
  }
}

// Disable any carousel or slideshow behavior
function disableCarouselBehavior() {
  // Remove any scroll-snap properties that might cause carousel behavior
  document.body.style.scrollSnapType = 'none';
  document.documentElement.style.scrollSnapType = 'none';
  
  // Ensure normal scrolling behavior
  document.body.style.scrollBehavior = 'auto';
  document.documentElement.style.scrollBehavior = 'auto';
  
  // Remove any transforms on body or html that might cause sliding
  document.body.style.transform = 'none';
  document.documentElement.style.transform = 'none';
  
  // Ensure proper overflow settings
  document.body.style.overflowX = 'hidden';
  document.body.style.overflowY = 'auto';
  
  // Target feature cards specifically
  setTimeout(() => {
    const featuresContainer = document.querySelector('.features-container');
    if (featuresContainer) {
      featuresContainer.style.display = 'flex';
      featuresContainer.style.flexWrap = 'wrap';
      featuresContainer.style.position = 'static';
      featuresContainer.style.transform = 'none';
      featuresContainer.style.scrollSnapType = 'none';
      featuresContainer.style.overflow = 'visible';
      featuresContainer.style.justifyContent = 'center';
      
      // Fix all cards in the container
      const cards = featuresContainer.querySelectorAll('.card');
      cards.forEach(card => {
        card.style.position = 'static';
        card.style.transform = 'none';
        card.style.scrollSnapAlign = 'none';
        card.style.flex = '1 1 300px';
        card.style.maxWidth = '400px';
        card.style.minWidth = '300px';
        card.style.width = 'auto';
      });
    }
    
    // Disable any potential carousel libraries
    if (window.Swiper) {
      console.log('Disabling Swiper');
    }
    if (window.Glide) {
      console.log('Disabling Glide');
    }
    if (window.Flickity) {
      console.log('Disabling Flickity');
    }
  }, 100);
}

// Flash Message Auto-Hide
function initFlashMessages() {
  const alerts = document.querySelectorAll('.alert');
  
  alerts.forEach(alert => {
    // Auto-hide success messages after 5 seconds
    if (alert.classList.contains('success')) {
      setTimeout(() => {
        alert.style.opacity = '0';
        alert.style.transform = 'translateY(-10px)';
        setTimeout(() => alert.remove(), 300);
      }, 5000);
    }
  });
}

// Smooth Scrolling for Anchor Links
function initSmoothScrolling() {
  const anchorLinks = document.querySelectorAll('a[href^="#"]');
  
  anchorLinks.forEach(link => {
    link.addEventListener('click', function(e) {
      const targetId = this.getAttribute('href').substring(1);
      const targetElement = document.getElementById(targetId);
      
      if (targetElement) {
        e.preventDefault();
        targetElement.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }
    });
  });
}

// Accordion Functionality
function initAccordions() {
  const accordionItems = document.querySelectorAll('.accordion-item');
  
  if (accordionItems.length === 0) {
    return; // No accordions found
  }
  
  // Clear any existing accordion state and listeners
  accordionItems.forEach(item => {
    item.classList.remove('active');
    const header = item.querySelector('.accordion-header');
    if (header) {
      // Clone the header to remove all event listeners
      const newHeader = header.cloneNode(true);
      header.parentNode.replaceChild(newHeader, header);
    }
  });
  
  // Open first item by default
  accordionItems[0].classList.add('active');
  
  // Add fresh event listeners
  accordionItems.forEach(item => {
    const header = item.querySelector('.accordion-header');
    
    if (header) {
      header.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        const isCurrentlyActive = item.classList.contains('active');
        
        if (isCurrentlyActive) {
          // Close the currently active item
          item.classList.remove('active');
        } else {
          // Close all items
          accordionItems.forEach(otherItem => {
            otherItem.classList.remove('active');
          });
          
          // Open the clicked item
          item.classList.add('active');
        }
      });
    }
  });
}

// Form Enhancements
function initFormEnhancements() {
  // Add focus/blur effects to form inputs
  const formInputs = document.querySelectorAll('.form-input');
  
  formInputs.forEach(input => {
    input.addEventListener('focus', function() {
      this.parentElement.classList.add('focused');
    });
    
    input.addEventListener('blur', function() {
      this.parentElement.classList.remove('focused');
    });
  });
  
  // Auto-resize textareas
  const textareas = document.querySelectorAll('textarea.form-input');
  textareas.forEach(textarea => {
    textarea.addEventListener('input', function() {
      this.style.height = 'auto';
      this.style.height = this.scrollHeight + 'px';
    });
  });
}

// Keyboard Navigation
function initKeyboardNavigation() {
  document.addEventListener('keydown', function(event) {
    // ESC key closes sidebar and dropdowns
    if (event.key === 'Escape') {
      closeSidebar();
      
      // Close user dropdown
      const userDropdown = document.getElementById('user-dropdown');
      const userInfo = document.querySelector('.user-info');
      if (userDropdown && userInfo) {
        userDropdown.classList.remove('show');
        userInfo.classList.remove('active');
      }
    }
    
    // Toggle sidebar with Ctrl+B
    if (event.ctrlKey && event.key === 'b') {
      event.preventDefault();
      toggleSidebar();
    }
  });
}

// Initialize Page
function initPage() {
  disableCarouselBehavior(); // Disable any carousel/slideshow behavior
  resetBodyOverflow(); // Ensure proper scrolling on page load
  setActiveNavLink();
  initFlashMessages();
  initSmoothScrolling();
  initAccordions();
  initFormEnhancements();
  initKeyboardNavigation();
  initImageModal(); // Initialize image modal functionality
}

// Initialize Image Modal
function initImageModal() {
  // Initialize feature card click handlers if they exist
  const featureCards = document.querySelectorAll('.feature-card');
  featureCards.forEach(card => {
    card.addEventListener('click', function() {
      const imageSrc = this.dataset.image;
      const title = this.dataset.title;
      const description = this.dataset.description;
      
      showImageModal(imageSrc, title, description);
    });
  });
  
  // Close modal with Escape key
  document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
      closeImageModal();
    }
  });
}

// Event Listeners
document.addEventListener('DOMContentLoaded', initPage);
window.addEventListener('resize', function() {
  handleResize();
  resetBodyOverflow();
});

// Legacy Functions (for compatibility with existing modals and functionality)
// Note: Modal functions are now implemented inline in base.html to avoid conflicts

// Utility Functions
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

function throttle(func, limit) {
  let inThrottle;
  return function() {
    const args = arguments;
    const context = this;
    if (!inThrottle) {
      func.apply(context, args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}

// Image Modal Functions
function showImageModal(imageSrc, title, description) {
  const modal = document.getElementById('imageModal');
  const modalImage = document.getElementById('modalImage');
  const modalTitle = document.getElementById('modalTitle');
  const modalDescription = document.getElementById('modalDescription');
  
  if (!modal || !modalImage || !modalTitle || !modalDescription) {
    console.error('Modal elements not found');
    return;
  }
  
  modalImage.src = imageSrc;
  modalImage.alt = title;
  modalTitle.textContent = title;
  modalDescription.textContent = description;
  
  // Force modal to overlay properly
  modal.style.display = 'flex';
  modal.style.position = 'fixed';
  modal.style.top = '0';
  modal.style.left = '0';
  modal.style.right = '0';
  modal.style.bottom = '0';
  modal.style.zIndex = '99999';
  modal.style.justifyContent = 'center';
  modal.style.alignItems = 'center';
  modal.style.width = '100vw';
  modal.style.height = '100vh';
  
  document.body.style.overflow = 'hidden';
}

function closeImageModal() {
  const modal = document.getElementById('imageModal');
  if (modal) {
    modal.style.display = 'none';
    document.body.style.overflow = 'auto';
  }
}

// Export functions for use in other scripts
window.MTGODB = {
  toggleSidebar,
  closeSidebar,
  toggleUserDropdown,
  setActiveNavLink,
  initAccordions,
  showImageModal,
  closeImageModal,
  debounce,
  throttle
};