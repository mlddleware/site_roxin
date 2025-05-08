let lastUpdate = 0;
let isUpdateInProgress = false;

function updateLastVisit() {
    const now = Date.now();
    
    // Если прошло менее 15 секунд с последнего обновления или уже идет обновление - выходим
    if (now - lastUpdate < 15000 || isUpdateInProgress) {
        return;
    }

    isUpdateInProgress = true;

    fetch('/update_last_visit', { 
        method: 'POST',
        credentials: 'same-origin'
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        lastUpdate = now;
    })
    .catch(error => console.error('Ошибка при обновлении last_visit:', error))
    .finally(() => {
        isUpdateInProgress = false;
    });
}

// Создаем throttle-функцию для scroll
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
    }
}

// Применяем throttle к updateLastVisit для scroll
document.addEventListener("scroll", throttle(updateLastVisit, 500));
document.addEventListener("mousemove", updateLastVisit);
document.addEventListener("keydown", updateLastVisit);
document.addEventListener("click", updateLastVisit);