const mobileMenuButton = document.querySelector('[aria-controls="mobile-auth-menu"]');
const mobileAuthMenu = document.getElementById('mobile-auth-menu');

const closeMobileAuthMenu = () => {
  if (!mobileAuthMenu || mobileAuthMenu.hidden) return;

  mobileAuthMenu.hidden = true;
  mobileMenuButton?.setAttribute('aria-expanded', 'false');
  mobileMenuButton?.setAttribute('aria-label', 'Open menu');
};

mobileMenuButton?.addEventListener('click', () => {
  if (!mobileAuthMenu) return;

  mobileAuthMenu.hidden = !mobileAuthMenu.hidden;
  const isOpen = !mobileAuthMenu.hidden;
  mobileMenuButton.setAttribute('aria-expanded', String(isOpen));
  mobileMenuButton.setAttribute('aria-label', isOpen ? 'Close menu' : 'Open menu');

  if (isOpen) mobileAuthMenu.querySelector('button')?.focus();
});

mobileAuthMenu?.addEventListener('click', (event) => {
  if (event.target !== mobileAuthMenu) return;

  closeMobileAuthMenu();
  mobileMenuButton?.focus();
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape' || !mobileAuthMenu || mobileAuthMenu.hidden) return;

  closeMobileAuthMenu();
  mobileMenuButton?.focus();
});
