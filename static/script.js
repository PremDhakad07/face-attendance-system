document.addEventListener('DOMContentLoaded', () => {
    // --- Theme Toggle Logic ---
    const themeToggleBtn = document.getElementById('theme-toggle');
    const body = document.body;

    // Check for saved theme preference on page load
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
        body.setAttribute('data-theme', savedTheme);
        themeToggleBtn.textContent = savedTheme === 'dark' ? '☀️' : '🌙';
    } else {
        // Default to dark mode if no preference is found
        body.setAttribute('data-theme', 'dark');
        localStorage.setItem('theme', 'dark');
        themeToggleBtn.textContent = '☀️';
    }

    themeToggleBtn.addEventListener('click', () => {
        const currentTheme = body.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        body.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        themeToggleBtn.textContent = newTheme === 'dark' ? '☀️' : '🌙';
    });

    // --- General Utility Functions ---
    // Function to show temporary messages
    window.showMessage = (message, type, duration) => {
        const messageBox = document.createElement('div');
        messageBox.classList.add('status-message', type);
        messageBox.textContent = message;
        const form = document.querySelector('form');
        if (form) {
            form.prepend(messageBox);
        } else {
            document.body.appendChild(messageBox);
        }
        setTimeout(() => {
            messageBox.remove();
        }, duration);
    };

    // --- Dynamic Logic for Various Pages ---
    
    // --- Teacher Login page specific logic
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        const passwordInput = document.getElementById('password');
        const error = loginForm.dataset.error;
        if (error) {
            showMessage(error, 'error', 5000);
        }
        passwordInput.focus();
    }

    // --- Manage Students page specific logic
    const exportBtn = document.getElementById('export-btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', () => {
            showMessage("Exporting data...", "info", 3000);
        });
    }

    // --- Main Menu page specific logic
    const shutdownBtn = document.getElementById('shutdown-btn');
    if (shutdownBtn) {
        shutdownBtn.addEventListener('click', () => {
            if (confirm('Are you sure you want to shut down the server?')) {
                fetch('/shutdown', {
                    method: 'POST',
                }).then(() => {
                    showMessage("Server is shutting down...", 'info', 5000);
                }).catch(error => {
                    showMessage("Error during shutdown.", 'error', 5000);
                    console.error('Error during shutdown:', error);
                });
            }
        });
    }
    
    // --- Attendance page specific logic
    const logList = document.getElementById('log-list');
    if (logList) {
        let attendanceLog = {};

        function addLogEntry(message, type) {
            const entry = document.createElement('div');
            entry.classList.add('log-entry', `status-message`, type);
            entry.textContent = message;
            if (logList.firstChild) {
                logList.insertBefore(entry, logList.firstChild);
            } else {
                logList.appendChild(entry);
            }
            if (logList.children.length > 20) {
                logList.lastChild.remove();
            }
        }
    
        setInterval(async () => {
            try {
                const response = await fetch('/get_latest_attendance');
                if (response.ok) {
                    const data = await response.json();
                    if (data && data.length > 0) {
                        data.forEach(entry => {
                            const logKey = `${entry.reg_no}-${entry.timestamp}`;
                            if (!attendanceLog[logKey]) {
                                addLogEntry(`✅ ${entry.name} (${entry.reg_no}) checked in at ${entry.timestamp.split(' ')[1]}`, 'success');
                                attendanceLog[logKey] = true;
                            }
                        });
                    }
                }
            } catch (e) {
                console.error("Failed to fetch latest attendance log:", e);
            }
        }, 3000); // Check every 3 seconds
    }
});