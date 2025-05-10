// scripts.js
function updateSignals() {
    document.getElementById('loading').style.display = 'block';
    fetch('/get_latest_signals')
        .then(response => response.json())
        .then(data => {
            // Update top coins table
            const topCoinsTable = document.getElementById('top-coins-table');
            topCoinsTable.innerHTML = '';
            data.top_coins.forEach(coin => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${coin.symbol || 'N/A'}</td>
                    <td>${coin.timeframe || 'N/A'}</td>
                    <td>$${coin.current_price ? Number(coin.current_price).toFixed(4) : 'N/A'}</td>
                    <td>${coin.signal || 'N/A'}</td>
                    <td>$${coin.entry ? Number(coin.entry).toFixed(4) : 'N/A'}</td>
                    <td>$${coin.tp ? Number(coin.tp).toFixed(4) : 'N/A'}</td>
                    <td>$${coin.sl ? Number(coin.sl).toFixed(4) : 'N/A'}</td>
                `;
                topCoinsTable.appendChild(row);
            });

            // Update active signals table
            const activeSignalsTable = document.getElementById('active-signals-table');
            activeSignalsTable.innerHTML = '';
            data.active_signals.forEach(s => {
                const row = document.createElement('tr');
                const isFutures = s.signal.includes('FUTURES') ? 'futures' : '';
                row.innerHTML = `
                    <td>${s.symbol || 'N/A'}</td>
                    <td>${s.timeframe || 'N/A'}</td>
                    <td>${s.signal || 'N/A'}</td>
                    <td>$${s.entry ? Number(s.entry).toFixed(4) : 'N/A'}</td>
                    <td>$${s.tp ? Number(s.tp).toFixed(4) : 'N/A'}</td>
                    <td>$${s.sl ? Number(s.sl).toFixed(4) : 'N/A'}</td>
                    <td>$${s.current_price ? Number(s.current_price).toFixed(4) : 'N/A'}</td>
                    <td><span class="status-badge ${isFutures}">${s.status || 'N/A'}</span></td>
                    <td>${s.time || 'N/A'}</td>
                    <td>${s.duration || 'N/A'}</td>
                `;
                activeSignalsTable.appendChild(row);
            });

            // Apply badge styling
            applyBadgeStyling();
            applySignalBadgeStyling();

            // Update last updated time
            const now = new Date().toLocaleString();
            document.getElementById('last-updated').textContent = now;
            document.getElementById('loading').style.display = 'none';
        })
        .catch(error => {
            console.error('Error updating signals:', error);
            document.getElementById('loading').style.display = 'none';
        });
}

function applyBadgeStyling() {
    const badges = document.querySelectorAll('.status-badge');
    badges.forEach(badge => {
        const text = badge.textContent;
        if (text.includes('✅')) {
            badge.style.backgroundColor = '#d4edda';
            badge.style.color = '#155724';
        } else if (text.includes('❌')) {
            badge.style.backgroundColor = '#f8d7da';
            badge.style.color = '#721c24';
        } else if (text.includes('⏳')) {
            badge.style.backgroundColor = '#fff3cd';
            badge.style.color = '#856404';
        } else if (text.includes('⚠️')) {
            badge.style.backgroundColor = '#ffeeba';
            badge.style.color = '#856404';
        }
    });
}

function applySignalBadgeStyling() {
    const signalCells = document.querySelectorAll('#active-signals-table td:nth-child(3), #top-coins-table td:nth-child(4)');
    signalCells.forEach(cell => {
        const text = cell.textContent;
        if (text.includes('🟢🚀')) {
            cell.style.backgroundColor = '#c3e6cb';
            cell.style.color = '#155724';
            cell.classList.add('futures');
        } else if (text.includes('🔻🚀')) {
            cell.style.backgroundColor = '#f5c6cb';
            cell.style.color = '#721c24';
            cell.classList.add('futures');
        } else if (text.includes('🟢⬆️')) {
            cell.style.backgroundColor = '#d4edda';
            cell.style.color = '#155724';
        } else if (text.includes('🔻')) {
            cell.style.backgroundColor = '#f8d7da';
            cell.style.color = '#721c24';
        }
    });
}

function startCountdown() {
    let timeLeft = 180; // 3 phút = 180 giây
    const countdownElement = document.getElementById('countdown');
    const interval = setInterval(() => {
        timeLeft--;
        countdownElement.textContent = timeLeft;
        if (timeLeft <= 0) {
            // Tự động tải lại toàn bộ trang sau 3 phút
            window.location.reload();
        }
    }, 1000); // Cập nhật mỗi giây
}

document.addEventListener('DOMContentLoaded', () => {
    updateSignals();
    startCountdown();
    applySignalBadgeStyling();
});