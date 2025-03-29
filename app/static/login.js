async function login(username, password) {
    const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
    });
    return res.ok;
}

async function onClick_loginBtn(params) {
    const errorDiv = document.getElementById('loginError');
    const user = document.getElementById('username').value;
    const pass = document.getElementById('password').value;
    errorDiv.innerText = '';

    const success = await login(user, pass);
    if (success) {
        window.location.href = '/';
    } else {
        errorDiv.innerText = "❌ Invalid username or password. Please try again.";
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('username').focus();
    document.getElementById('loginBtn').onclick = onClick_loginBtn;
});
