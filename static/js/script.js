// Toggle achievements
const achievementsToggle = document.querySelector('.achievements-toggle');
const achievementsContent = document.getElementById('achievementsContent');
const chevronIcon = document.querySelector('.icon-chevron-down');

achievementsToggle.addEventListener('click', () => {
  achievementsContent.classList.toggle('show');
  chevronIcon.style.transform = achievementsContent.classList.contains('show') 
    ? 'rotate(180deg)' 
    : 'rotate(0)';
});

// Modal handling
const editButton = document.getElementById('editButton');
const settingsButton = document.getElementById('settingsButton');
const editModal = document.getElementById('editModal');
const settingsModal = document.getElementById('settingsModal');
const closeButtons = document.querySelectorAll('.close-button');

function openModal(modal) {
  modal.classList.add('show');
}

function closeModal(modal) {
  modal.classList.remove('show');
}

editButton.addEventListener('click', () => openModal(editModal));
settingsButton.addEventListener('click', () => openModal(settingsModal));

closeButtons.forEach(button => {
  button.addEventListener('click', () => {
    const modal = button.closest('.modal');
    closeModal(modal);
  });
});

// Close modal when clicking outside
window.addEventListener('click', (event) => {
  if (event.target.classList.contains('modal')) {
    closeModal(event.target);
  }
});