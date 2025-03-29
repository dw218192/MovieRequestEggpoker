async function loadUserProfile() {
    const res = await fetch('/fragment/user', {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
    });
    if (res.ok) {
        const html = await res.text();
        document.getElementById('userProfile').innerHTML = html;
    } else {
        throw new Error('Failed to load user profile');
    }
}

async function onClick_searchBtn() {
    const type = document.getElementById('searchType').value;
    const query = document.getElementById('searchInput').value;
    const loading = document.getElementById('loading');
    loading.style.display = 'inline';

    try {
        const res = await fetch('/fragment/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type, query })
        });
        const html = await res.text();
        document.getElementById('result').innerHTML = html;
        const table = document.getElementById('result-table');
        if (!table) {
            console.error('Table not found in the response HTML');
            return;
        }
        new Tablesort(table);
    } catch (e) {
        document.getElementById('result').innerHTML = '<p>Error during search</p>';
    } finally {
        loading.style.display = 'none';
    }
}

async function fetchQBitTorrentStats() {
    const res = await fetch('/fragment/qbittorrent/stats', {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
    });
    if (res.ok) {
        const html = await res.text();
        document.getElementById('qbittorrent').innerHTML = html;
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    document.getElementById('searchBtn').onclick = onClick_searchBtn;
    await loadUserProfile();
    setInterval(fetchQBitTorrentStats, 5000);
    await fetchQBitTorrentStats();
});
