async function loadUserProfile() {
    const res = await fetch('/fragment/user', {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
    });
    if (res.ok) {
        const html = await res.text();
        document.getElementById('userProfile').innerHTML = html;
    } else {
        console.error('Failed to load user profile');
    }
}

async function onClick_searchBtn(btn) {
    const type = document.getElementById('searchType').value;
    const query = document.getElementById('searchInput').value;
    const loading = document.getElementById('loading');

    btn.disabled = true;
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
        btn.disabled = false;
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

async function onClick_torrentRequestBtn(torrentTitle, torrentLink, torrentSize, btn) {
    btn.disabled = true;
    const originalText = btn.innerText;
    btn.innerText = "Working...";
    const res = await fetch('/api/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ torrentTitle, torrentLink, torrentSize })
    });

    if (!res.ok) {
        const errorMessage = await res.text();
        alert(`Error submitting request: ${errorMessage}`);
    }
    btn.disabled = false;
    btn.innerText = originalText;
}
async function onClick_cancelTorrentRequestBtn(torrentHash, btn) {
    if (!confirm("Are you sure you want to cancel this request?")) return;

    btn.disabled = true;
    const originalText = btn.innerText;
    btn.innerText = "Working...";

    const res = await fetch(`/api/request/delete/${torrentHash}`, {
        method: "DELETE"
    });
    if (!res.ok) {
        const errorMessage = await res.text();
        alert(`Error canceling request: ${errorMessage}`);
    }
    else {
        await fetchQBitTorrentStats();
    }

    btn.disabled = false;
    btn.innerText = originalText;
}

function filterTable(inputElem) {
    const filter = inputElem.value.toLowerCase().trim();
    const tableId = inputElem.getAttribute("data-target-table");
    const table = document.getElementById(tableId);
    const trs = table.getElementsByTagName("tr");

    for (let i = 1; i < trs.length; i++) { // skip header
        const tds = trs[i].getElementsByTagName("td");

        if (tds.length === 0) continue; // skip rows without <td>

        if (filter === "") {
            trs[i].style.display = "";
            continue;
        }

        let match = false;
        for (let j = 0; j < tds.length; j++) {
            const cellText = tds[j].textContent || tds[j].innerText;
            if (cellText.toLowerCase().includes(filter)) {
                match = true;
                break;
            }
        }

        trs[i].style.display = match ? "" : "none";
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    await loadUserProfile();
    await fetchQBitTorrentStats();

    setInterval(fetchQBitTorrentStats, 5000);
});
