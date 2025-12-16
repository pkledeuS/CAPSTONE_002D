document.addEventListener('DOMContentLoaded', () => {
  /*
   * TODO: conectar con backend
   * Adjuntar telemetria a botones con data-reco-track para medir clicks.
   */
  document
    .querySelectorAll('[data-reco-track]')
    .forEach(btn => btn.setAttribute('aria-pressed', 'false'));

  document
    .querySelectorAll('[data-reco-toggle]')
    .forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.getAttribute('data-reco-toggle');
        if (!target) return;
        const items = document.querySelectorAll(`[data-reco-more="${target}"]`);
        if (!items.length) return;
        const expanded = btn.getAttribute('data-reco-expanded') === 'true';
        btn.setAttribute('data-reco-expanded', (!expanded).toString());
        items.forEach(el => {
          if (expanded) {
            el.classList.add('d-none');
          } else {
            el.classList.remove('d-none');
          }
        });
        btn.textContent = expanded ? 'Mostrar mas' : 'Mostrar menos';
      });
    });
});
