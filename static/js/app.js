const API_URL = '/api'; 
let token = localStorage.getItem('token');
let services = []; // Store services data
let isEditing = null;  // Track if we're editing


// Initial setup
document.addEventListener('DOMContentLoaded', () => {
    if (token) {
        showApp();
        loadServices();
    } else {
        showLogin();
    }
});


async function testService(serviceId) {
    const response = await fetch(`${API_URL}/services/${serviceId}/test`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`
        }
    });
    const result = await response.json();
    alert(`Status: ${result.status}\nResponse time: ${result.response_time}ms`);
}


// Auth functions
async function login(username, password) {
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);
    
    const response = await fetch(`${API_URL}/token`, {
        method: 'POST',
        body: formData
    });

    if (response.ok) {
        const data = await response.json();
        token = data.access_token;
        localStorage.setItem('token', token);
        return true;
    }
    return false;
}

function logout() {
    localStorage.removeItem('token');
    token = null;
    showLogin();
}

// UI functions
function showLogin() {
    document.getElementById('login-container').classList.remove('hidden');
    document.getElementById('app-container').classList.add('hidden');
}

function showApp() {
    document.getElementById('login-container').classList.add('hidden');
    document.getElementById('app-container').classList.remove('hidden');
}

async function loadServices() {
    const response = await fetch(`${API_URL}/services/`, {
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        },
    });
    
    if (response.ok) {
        const data = await response.json();
        services = data.services; // Store services
        renderServices(data.services);
    }
}

function renderServices(services) {
    const container = document.getElementById('services-list');
    container.innerHTML = services.map(service => `
        <div class="service-item">
            <h3>${service.name}</h3>
            <p>Type: ${service.type}</p>
            <p>Target: ${service.target}</p>
            <p>Status: <span class="status-${service.status}">${service.status}</span></p>
                        <button onclick="testService(${service.id})">Test</button>

            <button onclick="editService(${service.id})">Edit</button>
            <button onclick="deleteService(${service.id})">Delete</button>
        </div>
    `).join('');
}

// Event Listeners
document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    
    if (await login(username, password)) {
        showApp();
        loadServices();
    } else {
        alert('Login failed');
    }
});

document.getElementById('logout-btn').addEventListener('click', logout);

document.getElementById('service-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const service = Object.fromEntries(formData);
    
    const url = isEditing ? 
        `${API_URL}/services/${isEditing}` : 
        `${API_URL}/services`;
        
    const method = isEditing ? 'PUT' : 'POST';
    
    await fetch(url, {
        method,
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(service)
    });
    
    isEditing = null;
    e.target.reset();
    loadServices();
});


async function editService(serviceId) {
    isEditing = serviceId;
    const service = services.find(s => s.id === serviceId);
    if (!service) return;
    
    const form = document.getElementById('service-form');
    for (const [key, value] of Object.entries(service)) {
        const input = form.elements[key];
        if (input) input.value = value;
    }
    
    form.onsubmit = async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const updatedService = Object.fromEntries(formData);
        
        await fetch(`${API_URL}/services/${serviceId}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(updatedService)
        });
        
        loadServices();
        form.reset();
        form.onsubmit = null;
    };
}

async function deleteService(serviceId) {
    if (!confirm('Delete this service?')) return;
    
    await fetch(`${API_URL}/services/${serviceId}`, {
        method: 'DELETE',
        headers: {
            'Authorization': `Bearer ${token}`
        }
    });
    
    loadServices();
}




// Load SMTP config
async function loadSMTPConfig() {
    const response = await fetch(`${API_URL}/smtp`, {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    });
    if (response.ok) {
        const config = await response.json();
        document.getElementById('smtp-host').value = config.host;
        document.getElementById('smtp-port').value = config.port;
        document.getElementById('smtp-username').value = config.username;
        document.getElementById('smtp-from').value = config.from_email;
        document.getElementById('smtp-tls').checked = config.use_tls;
    }
}

// Handle SMTP form submission
document.getElementById('smtp-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const config = {
        host: formData.get('host'),
        port: parseInt(formData.get('port')),
        username: formData.get('username'),
        password: formData.get('password'),
        from_email: formData.get('from_email'),
        use_tls: formData.get('use_tls') === 'on'
    };
    
    await fetch(`${API_URL}/smtp`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(config)
    });
    
    alert('SMTP configuration saved');
});

// Handle test SMTP button
document.getElementById('test-smtp').addEventListener('click', async () => {
    try {
        const response = await fetch(`${API_URL}/smtp/test`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            alert('Test email sent successfully');
        } else {
            const error = await response.json();
            alert(`Failed to send test email: ${error.detail}`);
        }
    } catch (e) {
        alert('Failed to send test email');
    }
});

// Add to showApp function
function showApp() {
    document.getElementById('login-container').classList.add('hidden');
    document.getElementById('app-container').classList.remove('hidden');
    loadSMTPConfig();
}