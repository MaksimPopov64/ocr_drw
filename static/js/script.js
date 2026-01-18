// Drag and drop функциональность
const dropArea = document.getElementById('dropArea');
const fileInput = document.getElementById('fileInput');
const processBtn = document.getElementById('processBtn');
const loading = document.getElementById('loading');
const resultContainer = document.getElementById('resultContainer');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const batchInput = document.getElementById('batchInput');
const historyCard = document.getElementById('historyCard');
const historyBody = document.getElementById('historyBody');

let selectedFile = null;

// Показать сообщение пользователю
function showMessage(message, type = 'info') {
    const messageDiv = document.createElement('div');
    messageDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        border-radius: 4px;
        font-size: 14px;
        z-index: 10000;
        animation: slideIn 0.3s ease-out;
    `;

    if (type === 'error') {
        messageDiv.style.backgroundColor = '#f44336';
        messageDiv.style.color = 'white';
    } else if (type === 'success') {
        messageDiv.style.backgroundColor = '#4caf50';
        messageDiv.style.color = 'white';
    } else {
        messageDiv.style.backgroundColor = '#2196f3';
        messageDiv.style.color = 'white';
    }

    messageDiv.textContent = message;
    document.body.appendChild(messageDiv);

    setTimeout(() => {
        messageDiv.remove();
    }, 3000);
}

// Загружаем историю при загрузке страницы
document.addEventListener('DOMContentLoaded', loadHistory);

// Предотвращаем стандартное поведение для drag and drop
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

// Подсветка области при перетаскивании
['dragenter', 'dragover'].forEach(eventName => {
    dropArea.addEventListener(eventName, highlight, false);
});

['dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, unhighlight, false);
});

function highlight() {
    dropArea.style.borderColor = '#764ba2';
    dropArea.style.backgroundColor = '#eef2ff';
}

function unhighlight() {
    dropArea.style.borderColor = '#667eea';
    dropArea.style.backgroundColor = '#f8f9fa';
}

// Обработка drop
dropArea.addEventListener('drop', handleDrop, false);

function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;

    if (files.length > 0) {
        handleFile(files[0]);
    }
}

// Обработка выбора файла через кнопку
fileInput.addEventListener('change', function (e) {
    if (this.files.length > 0) {
        handleFile(this.files[0]);
    }
});

// Обработка пакетной загрузки
batchInput.addEventListener('change', function (e) {
    if (this.files.length > 0) {
        handleBatchUpload(this.files);
    }
});

function handleFile(file) {
    selectedFile = file;

    // Показываем информацию о файле
    fileInfo.style.display = 'block';
    fileName.innerHTML = `
        <i class="fas fa-file"></i> ${file.name} 
        (${formatFileSize(file.size)})
    `;

    // Активируем кнопку обработки
    processBtn.disabled = false;
}

function handleBatchUpload(files) {
    if (files.length === 0) return;

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files[]', files[i]);
    }

    loading.style.display = 'block';
    resultContainer.innerHTML = '';

    fetch('/batch', {
        method: 'POST',
        body: formData
    })
        .then(response => response.json())
        .then(data => {
            loading.style.display = 'none';

            if (data.success) {
                showBatchResults(data.results);
            } else {
                showError(data.error || 'Ошибка при пакетной обработке');
            }
        })
        .catch(error => {
            loading.style.display = 'none';
            showError('Ошибка сети: ' + error.message);
        });
}

function processDocument() {
    if (!selectedFile) {
        alert('Пожалуйста, выберите файл для обработки');
        return;
    }

    const expectedClaim = document.getElementById('expectedClaim').value;

    // Показываем индикатор загрузки
    loading.style.display = 'block';
    resultContainer.innerHTML = '';

    // Создаем FormData
    const formData = new FormData();
    formData.append('file', selectedFile);
    if (expectedClaim) {
        formData.append('expected_claim', expectedClaim);
    }

    // Отправляем запрос
    fetch('/upload_improved', {
        method: 'POST',
        body: formData
    })
        .then(response => response.json())
        .then(data => {
            loading.style.display = 'none';

            if (data.success) {
                // Перенаправляем на страницу результата
                window.location.href = `/result/${data.file_id}`;
            } else {
                showError(data.error || 'Произошла ошибка при обработке');
            }
        })
        .catch(error => {
            loading.style.display = 'none';
            showError('Ошибка сети: ' + error.message);
        });
}

function showError(message) {
    resultContainer.innerHTML = `
        <div class="card">
            <div class="status-badge status-rejected">
                <i class="fas fa-exclamation-circle"></i> ОШИБКА
            </div>
            <p style="color: #721c24; margin-top: 20px;">${message}</p>
            <button class="btn" onclick="window.location.reload()" style="margin-top: 20px;">
                <i class="fas fa-redo"></i> Попробовать снова
            </button>
        </div>
    `;
}

function showBatchResults(results) {
    let html = '<div class="card"><h3>Результаты пакетной обработки</h3>';

    results.forEach(result => {
        let statusBadge;
        if (result.status === 'APPROVED') {
            statusBadge = '<span class="status-badge status-approved" style="font-size: 12px;">ПРИНЯТ</span>';
        } else if (result.status === 'REJECTED') {
            statusBadge = '<span class="status-badge status-rejected" style="font-size: 12px;">ОТКЛОНЕН</span>';
        } else {
            statusBadge = '<span class="status-badge status-review" style="font-size: 12px;">ПРОВЕРКА</span>';
        }

        html += `
            <div style="border-bottom: 1px solid #eee; padding: 10px 0;">
                <strong>${result.original_filename}</strong>
                ${statusBadge}
                <div style="color: #666; font-size: 14px; margin-top: 5px;">
                    Заявка: ${result.parsed_data?.claim_number || 'Не найден'}
                </div>
            </div>
        `;
    });

    html += '</div>';
    resultContainer.innerHTML = html;

    // Обновляем историю
    loadHistory();
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function loadHistory() {
    fetch('/history')
        .then(response => response.json())
        .then(data => {
            if (data.history && data.history.length > 0) {
                historyCard.style.display = 'block';

                let html = '';
                data.history.slice(0, 10).forEach(item => {
                    let statusBadge;
                    if (item.status === 'APPROVED') {
                        statusBadge = '<span class="status-badge status-approved" style="font-size: 11px; padding: 4px 8px;">ПРИНЯТ</span>';
                    } else if (item.status === 'REJECTED') {
                        statusBadge = '<span class="status-badge status-rejected" style="font-size: 11px; padding: 4px 8px;">ОТКЛОНЕН</span>';
                    } else {
                        statusBadge = '<span class="status-badge status-review" style="font-size: 11px; padding: 4px 8px;">ПРОВЕРКА</span>';
                    }

                    html += `
                        <tr>
                            <td>${item.timestamp ? new Date(item.timestamp).toLocaleString('ru-RU') : 'N/A'}</td>
                            <td>${item.claim_number || 'Не найден'}</td>
                            <td>${statusBadge}</td>
                            <td>
                                <a href="/result/${item.file_id}" class="btn" style="padding: 4px 8px; font-size: 12px;">
                                    <i class="fas fa-eye"></i> Просмотр
                                </a>
                            </td>
                        </tr>
                    `;
                });

                historyBody.innerHTML = html;
            }
        })
        .catch(error => {
            console.error('Ошибка при загрузке истории:', error);
        });
}

async function processWithAI() {
    if (!selectedFile) {
        showMessage('Пожалуйста, выберите файл для обработки', 'error');
        return;
    }

    const expectedClaim = document.getElementById('expectedClaim').value;

    loading.style.display = 'block';
    resultContainer.innerHTML = '';

    const formData = new FormData();
    formData.append('file', selectedFile);
    if (expectedClaim) {
        formData.append('expected_claim', expectedClaim);
    }

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            window.location.href = `/result/${data.file_id}`;
        } else {
            showMessage(data.error || 'Произошла ошибка при обработке', 'error');
        }
    } catch (error) {
        showMessage('Ошибка сети: ' + error.message, 'error');
    } finally {
        loading.style.display = 'none';
    }
}