// NFL Pick'em - Main JavaScript

document.addEventListener('DOMContentLoaded', function() {
    initializeTheme();
    initializeMobileMenu();
    initializeUserMenu();
    initializeFlashMessages();
    initializeFormEnhancements();
});

// Group Selector in Nav
function changeGroup() {
    const select = document.getElementById('nav-group-select');
    const groupSlug = select.value;
    if (groupSlug) {
        // Update button text with selected group name
        const selectedOption = select.options[select.selectedIndex];
        const buttonText = document.getElementById('current-group-name');
        if (buttonText) {
            buttonText.textContent = selectedOption.text;
        }
        
        // Store selected group in session storage
        sessionStorage.setItem('selectedGroup', groupSlug);
        
        // Reload current page with new group parameter
        const url = new URL(window.location);
        url.searchParams.set('group', groupSlug);
        window.location.href = url.toString();
    }
}

// Theme Management
function initializeTheme() {
    const themeToggle = document.getElementById('theme-toggle');
    if (!themeToggle) return;

    // Load saved theme or default to light
    const savedTheme = localStorage.getItem('theme') || 'light';
    setTheme(savedTheme);

    themeToggle.addEventListener('click', function() {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        setTheme(newTheme);
        localStorage.setItem('theme', newTheme);
    });
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    
    const themeToggle = document.getElementById('theme-toggle');
    const moonIcon = document.getElementById('theme-toggle-moon');
    const sunIcon = document.getElementById('theme-toggle-sun');
    
    if (themeToggle && moonIcon && sunIcon) {
        if (theme === 'dark') {
            moonIcon.classList.add('hidden');
            sunIcon.classList.remove('hidden');
        } else {
            moonIcon.classList.remove('hidden');
            sunIcon.classList.add('hidden');
        }
    }
}

// Mobile Menu Management
function initializeMobileMenu() {
    const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
    const mobileMenu = document.getElementById('mobile-menu');
    
    if (!mobileMenuToggle || !mobileMenu) return;

    mobileMenuToggle.addEventListener('click', function() {
        const isOpen = mobileMenu.classList.contains('hidden');
        
        if (isOpen) {
            mobileMenu.classList.remove('hidden');
            mobileMenu.classList.add('animate-slide-in');
            mobileMenuToggle.setAttribute('aria-expanded', 'true');
        } else {
            mobileMenu.classList.add('hidden');
            mobileMenu.classList.remove('animate-slide-in');
            mobileMenuToggle.setAttribute('aria-expanded', 'false');
        }
    });

    // Close mobile menu when clicking outside
    document.addEventListener('click', function(event) {
        if (!mobileMenu.contains(event.target) && !mobileMenuToggle.contains(event.target)) {
            if (!mobileMenu.classList.contains('hidden')) {
                mobileMenu.classList.add('hidden');
                mobileMenu.classList.remove('animate-slide-in');
                mobileMenuToggle.setAttribute('aria-expanded', 'false');
            }
        }
    });
}

// User Dropdown Menu
function initializeUserMenu() {
    const userMenuButton = document.getElementById('user-menu-button');
    const userMenu = document.getElementById('user-menu');
    
    if (!userMenuButton || !userMenu) return;

    userMenuButton.addEventListener('click', function(event) {
        event.stopPropagation();
        event.preventDefault();
        const isOpen = !userMenu.classList.contains('hidden');
        
        if (isOpen) {
            userMenu.classList.add('hidden');
            userMenuButton.setAttribute('aria-expanded', 'false');
        } else {
            userMenu.classList.remove('hidden');
            userMenuButton.setAttribute('aria-expanded', 'true');
        }
    });

    // Close user menu when clicking outside
    document.addEventListener('click', function(event) {
        if (!userMenu.contains(event.target) && !userMenuButton.contains(event.target)) {
            if (!userMenu.classList.contains('hidden')) {
                userMenu.classList.add('hidden');
                userMenuButton.setAttribute('aria-expanded', 'false');
            }
        }
    });
    
    // Prevent dropdown from closing when clicking inside it (but allow links to work)
    userMenu.addEventListener('click', function(event) {
        // Only stop propagation if not clicking on a link or button
        if (!event.target.closest('a') && !event.target.closest('button')) {
            event.stopPropagation();
        }
    });
}

// Flash Messages Management
function initializeFlashMessages() {
    const flashMessages = document.querySelectorAll('.flash-message');
    
    flashMessages.forEach(function(message) {
        // Auto-hide success messages after 5 seconds
        if (message.classList.contains('flash-success')) {
            setTimeout(function() {
                hideFlashMessage(message);
            }, 5000);
        }
        
        // Add close button if not present
        if (!message.querySelector('.flash-close')) {
            const closeButton = document.createElement('button');
            closeButton.className = 'flash-close absolute top-2 right-2 text-gray-400 hover:text-gray-600 focus:outline-none';
            closeButton.innerHTML = '&times;';
            closeButton.addEventListener('click', function() {
                hideFlashMessage(message);
            });
            
            message.style.position = 'relative';
            message.appendChild(closeButton);
        }
    });
}

function hideFlashMessage(message) {
    message.style.opacity = '0';
    message.style.transform = 'translateX(100%)';
    setTimeout(function() {
        if (message.parentNode) {
            message.parentNode.removeChild(message);
        }
    }, 300);
}

// Form Enhancements
function initializeFormEnhancements() {
    // Add loading states to form submissions
    const forms = document.querySelectorAll('form');
    
    forms.forEach(function(form) {
        form.addEventListener('submit', function(event) {
            const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');
            
            if (submitButton && !submitButton.disabled) {
                const originalText = submitButton.textContent || submitButton.value;
                
                // Prevent double submission
                submitButton.disabled = true;
                
                if (submitButton.tagName === 'BUTTON') {
                    submitButton.textContent = 'Loading...';
                } else {
                    submitButton.value = 'Loading...';
                }
                
                // Re-enable after a delay if form doesn't actually submit
                setTimeout(function() {
                    if (submitButton.disabled) {
                        submitButton.disabled = false;
                        if (submitButton.tagName === 'BUTTON') {
                            submitButton.textContent = originalText;
                        } else {
                            submitButton.value = originalText;
                        }
                    }
                }, 10000);
            }
        });
    });

    // Enhanced form validation
    const inputs = document.querySelectorAll('.form-input');
    
    inputs.forEach(function(input) {
        input.addEventListener('blur', function() {
            validateInput(input);
        });
        
        input.addEventListener('input', function() {
            // Clear validation errors on input
            const errorElement = input.parentNode.querySelector('.form-error');
            if (errorElement && input.value.trim()) {
                errorElement.style.display = 'none';
            }
        });
    });
}

function validateInput(input) {
    const value = input.value.trim();
    let isValid = true;
    let errorMessage = '';

    // Required field validation
    if (input.hasAttribute('required') && !value) {
        isValid = false;
        errorMessage = 'This field is required.';
    }
    
    // Email validation
    if (input.type === 'email' && value) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(value)) {
            isValid = false;
            errorMessage = 'Please enter a valid email address.';
        }
    }
    
    // Password validation
    if (input.type === 'password' && input.name === 'password' && value) {
        if (value.length < 8) {
            isValid = false;
            errorMessage = 'Password must be at least 8 characters long.';
        }
    }
    
    // Confirm password validation
    if (input.name === 'password2' && value) {
        const passwordField = document.querySelector('input[name="password"]');
        if (passwordField && passwordField.value !== value) {
            isValid = false;
            errorMessage = 'Passwords do not match.';
        }
    }
    
    // Show/hide validation error
    let errorElement = input.parentNode.querySelector('.form-error');
    
    if (!isValid) {
        if (!errorElement) {
            errorElement = document.createElement('div');
            errorElement.className = 'form-error';
            input.parentNode.appendChild(errorElement);
        }
        errorElement.textContent = errorMessage;
        errorElement.style.display = 'block';
        input.classList.add('border-red-500');
    } else {
        if (errorElement) {
            errorElement.style.display = 'none';
        }
        input.classList.remove('border-red-500');
    }
    
    return isValid;
}

// Utility Functions
function showNotification(message, type = 'info', duration = 3000) {
    const notification = document.createElement('div');
    notification.className = `flash-message flash-${type} fixed top-4 right-4 z-50 animate-slide-in max-w-sm`;
    notification.textContent = message;
    notification.style.minWidth = '200px';
    
    // Add close button
    const closeButton = document.createElement('button');
    closeButton.className = 'absolute top-2 right-2 text-gray-400 hover:text-gray-600 focus:outline-none';
    closeButton.innerHTML = '&times;';
    closeButton.addEventListener('click', function() {
        hideFlashMessage(notification);
    });
    
    notification.style.position = 'relative';
    notification.appendChild(closeButton);
    
    document.body.appendChild(notification);
    
    // Auto-hide after duration
    setTimeout(function() {
        hideFlashMessage(notification);
    }, duration);
    
    return notification;
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = function() {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Auto-refresh for live games
function setupAutoRefresh(interval = 30000) {
    if (window.hasLiveGames) {
        setInterval(function() {
            if (!document.hidden) {
                // Only refresh if the page is visible
                window.location.reload();
            }
        }, interval);
    }
}

// AJAX helper function
function makeRequest(url, options = {}) {
    const defaultOptions = {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin'
    };
    
    const mergedOptions = { ...defaultOptions, ...options };
    
    return fetch(url, mergedOptions)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return response.json();
            } else {
                return response.text();
            }
        })
        .catch(error => {
            console.error('Request failed:', error);
            throw error;
        });
}

// Keyboard shortcuts
document.addEventListener('keydown', function(event) {
    // Ctrl/Cmd + K to focus search (if search exists)
    if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
        event.preventDefault();
        const searchInput = document.querySelector('input[type="search"], input[placeholder*="search"]');
        if (searchInput) {
            searchInput.focus();
        }
    }
    
    // Escape key to close modals/dropdowns
    if (event.key === 'Escape') {
        // Close user menu
        const userMenu = document.getElementById('user-menu');
        const userMenuButton = document.getElementById('user-menu-button');
        if (userMenu && !userMenu.classList.contains('hidden')) {
            userMenu.classList.add('hidden');
            userMenuButton.setAttribute('aria-expanded', 'false');
        }
        
        // Close mobile menu
        const mobileMenu = document.getElementById('mobile-menu');
        const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
        if (mobileMenu && !mobileMenu.classList.contains('hidden')) {
            mobileMenu.classList.add('hidden');
            mobileMenuToggle.setAttribute('aria-expanded', 'false');
        }
    }
});

// Performance monitoring
if ('performance' in window && 'navigation' in performance) {
    window.addEventListener('load', function() {
        setTimeout(function() {
            const perfData = performance.getEntriesByType('navigation')[0];
            const loadTime = perfData.loadEventEnd - perfData.loadEventStart;
            
            if (loadTime > 3000) {
                console.warn('Page load time is slow:', loadTime + 'ms');
            }
        }, 0);
    });
}