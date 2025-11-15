(function () {
  function parseJSONScript(id) {
    const el = document.getElementById(id);
    if (!el) return {};
    try {
      return JSON.parse(el.textContent || '{}');
    } catch (err) {
      console.warn('[product-form] JSON parse failed for', id, err);
      return {};
    }
  }

  function normalizeKey(str) {
    return (str || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  function initProductForm() {
    const specContainer = document.getElementById('spec-formset');
    if (!specContainer) return;

    const totalInput = document.getElementById('id_spec-TOTAL_FORMS');
    const templateEl = document.getElementById('spec-empty-form');
    const addBtn = document.getElementById('add-spec-field');
    const templateBtn = document.getElementById('apply-spec-template');
    const typeSelect = document.getElementById('id_tipo_producto');

    const specTemplatesRaw = parseJSONScript('spec-templates-data');
    const specPlaceholders = parseJSONScript('spec-placeholders-data');
    const specTemplatesBySlug = {};

    Object.entries(specTemplatesRaw).forEach(([label, specs]) => {
      specTemplatesBySlug[normalizeKey(label)] = specs;
    });

    function syncDefaultPlaceholder(card) {
      const valueInput = card.querySelector('.spec-value');
      if (valueInput && !valueInput.dataset.defaultPlaceholder) {
        valueInput.dataset.defaultPlaceholder = valueInput.getAttribute('placeholder') || '';
      }
    }

    function attachRemoveHandler(card) {
      syncDefaultPlaceholder(card);
      const removeBtn = card.querySelector('[data-spec-remove]');
      const deleteInput = card.querySelector(`input[name$='-DELETE']`);
      if (!removeBtn || !deleteInput) return;
      removeBtn.addEventListener('click', () => {
        deleteInput.checked = true;
        card.classList.add('d-none');
      });
    }

    function allCards() {
      return Array.from(specContainer.querySelectorAll('[data-spec-card]'));
    }

    function addSpecCard() {
      if (!templateEl || !totalInput) return null;
      const rawHtml = templateEl.innerHTML.replace(/__prefix__/g, totalInput.value);
      const wrapper = document.createElement('div');
      wrapper.innerHTML = rawHtml.trim();
      const newCard = wrapper.firstElementChild;
      specContainer.appendChild(newCard);
      totalInput.value = String(Number(totalInput.value) + 1);
      attachRemoveHandler(newCard);
      return newCard;
    }

    function reviveCard(card) {
      const deleteInput = card.querySelector(`input[name$='-DELETE']`);
      if (deleteInput) deleteInput.checked = false;
      card.classList.remove('d-none');
    }

    function ensureCardForSpec() {
      const cards = allCards();
      for (const card of cards) {
        reviveCard(card);
        const nameInput = card.querySelector('.spec-name');
        if (nameInput && !nameInput.value.trim()) {
          const valueInput = card.querySelector('.spec-value');
          if (valueInput) valueInput.value = '';
          return card;
        }
      }
      return addSpecCard();
    }

    function clearSpecs() {
      allCards().forEach(card => {
        reviveCard(card);
        const nameInput = card.querySelector('.spec-name');
        const valueInput = card.querySelector('.spec-value');
        if (nameInput) nameInput.value = '';
        if (valueInput) {
          valueInput.value = '';
          valueInput.placeholder = valueInput.dataset.defaultPlaceholder || '';
        }
      });
    }

    function hasFilledSpecs() {
      return allCards().some(card => {
        const nameInput = card.querySelector('.spec-name');
        return nameInput && nameInput.value.trim();
      });
    }

    function getSelectedTypeMeta() {
      if (!typeSelect) return null;
      const option = typeSelect.options[typeSelect.selectedIndex];
      if (!option) return null;
      const label = option.text.trim();
      const slug = normalizeKey(option.getAttribute('data-template-key') || label);
      const specs = specTemplatesBySlug[slug] || null;
      return { label, slug, specs };
    }

    function applyTemplate(meta, options = { interactive: false }) {
      if (!meta || !Array.isArray(meta.specs)) return;
      const alreadyFilled = hasFilledSpecs();
      if (alreadyFilled && !options.interactive) return;
      if (alreadyFilled && options.interactive) {
        const confirmed = window.confirm('Se reemplazarán las especificaciones actuales por la plantilla seleccionada.');
        if (!confirmed) return;
      }
      clearSpecs();
      meta.specs.forEach(specName => {
        const card = ensureCardForSpec();
        if (!card) return;
        const nameInput = card.querySelector('.spec-name');
        const valueInput = card.querySelector('.spec-value');
        if (nameInput) nameInput.value = specName;
        if (valueInput) {
          const hint = specPlaceholders[specName] || valueInput.dataset.defaultPlaceholder || '';
          valueInput.placeholder = hint;
        }
      });
    }

    allCards().forEach(attachRemoveHandler);

    if (addBtn) {
      addBtn.addEventListener('click', () => {
        addSpecCard();
      });
    }

    if (templateBtn) {
      templateBtn.addEventListener('click', () => {
        const meta = getSelectedTypeMeta();
        if (!meta) {
          alert('Selecciona un tipo de producto primero.');
          return;
        }
        applyTemplate(meta, { interactive: true });
      });
    }

    function autoApplyInitialTemplate() {
      if (hasFilledSpecs()) return;
      const meta = getSelectedTypeMeta();
      if (!meta || !meta.specs) return;
      applyTemplate(meta, { interactive: false });
    }

    if (specContainer.dataset.allowAutofill === '1' && typeSelect) {
      typeSelect.addEventListener('change', () => {
        const meta = getSelectedTypeMeta();
        if (!meta) return;
        applyTemplate(meta, { interactive: false });
      });
      if (typeSelect.value) {
        autoApplyInitialTemplate();
      }
    }
  }

  document.addEventListener('DOMContentLoaded', initProductForm);
})();
