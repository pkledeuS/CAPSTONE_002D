(function () {
  const links = document.querySelectorAll('.admin-link');
  const path = window.location.pathname.replace(/\/+$/, ''); // sin slash final
  links.forEach(a => {
    const href = a.getAttribute('href') || '';
    if (!href) return;
    // comparación simple por prefijo (admin-panel/...):
    if (path.startsWith(href.replace(/\/+$/, ''))) {
      a.classList.add('active');
    }
  });
}());