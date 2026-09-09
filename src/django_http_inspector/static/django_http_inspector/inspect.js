(() => {
  const page = document.body;
  const base = page.dataset.inspectorBase;
  const list = document.querySelector('[data-request-list]');
  const empty = document.querySelector('[data-stream-empty]');
  const count = document.querySelector('[data-request-count]');
  const liveState = document.querySelector('[data-live-state]');
  const selectedId = page.dataset.selectedId;
  let cursor = page.dataset.listCursor;
  let pollTimer = null;
  let polling = false;
  let retryDelay = 2000;
  let editMode = false;

  const setLiveState = (state, label) => {
    if (!liveState) return;
    liveState.className = `capture-state is-${state}`;
    const text = liveState.querySelector('span');
    if (text) text.textContent = label;
  };

  const selectTab = (name) => {
    document.querySelectorAll('[data-tab]').forEach((item) => item.setAttribute('aria-selected', String(item.dataset.tab === name)));
    document.querySelectorAll('[data-panel]').forEach((panel) => { panel.hidden = panel.dataset.panel !== name; });
  };

  document.querySelectorAll('[data-tab]').forEach((button) => {
    button.addEventListener('click', () => selectTab(button.dataset.tab));
  });

  document.querySelectorAll('[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  const editForm = document.querySelector('[data-edit-form]');
  const requestView = document.querySelector('[data-request-view]');
  const editButton = document.querySelector('[data-edit-request]');
  const headersInput = document.querySelector('[data-edit-headers]');
  const bodyInput = document.querySelector('[data-edit-body]');
  const originalDraft = editForm ? { headers: headersInput.value, body: bodyInput.value } : null;

  const isDirty = () => Boolean(editForm && (headersInput.value !== originalDraft.headers || bodyInput.value !== originalDraft.body));

  const clearErrors = () => {
    document.querySelectorAll('[data-error-for]').forEach((node) => {
      node.hidden = true;
      node.textContent = '';
    });
  };

  const setEditMode = (enabled) => {
    if (!editForm || !requestView) return;
    editMode = enabled;
    editForm.hidden = !enabled;
    requestView.hidden = enabled;
    if (enabled) {
      selectTab('request');
      headersInput.focus();
    } else {
      clearErrors();
    }
  };

  if (editButton) editButton.addEventListener('click', () => setEditMode(true));
  document.querySelector('[data-edit-cancel]')?.addEventListener('click', () => {
    if (!isDirty() || window.confirm('Discard your replay edits?')) setEditMode(false);
  });
  document.querySelector('[data-edit-reset]')?.addEventListener('click', () => {
    if (!isDirty() || window.confirm('Reset headers and body to the captured request?')) {
      headersInput.value = originalDraft.headers;
      bodyInput.value = originalDraft.body;
      clearErrors();
    }
  });

  window.addEventListener('beforeunload', (event) => {
    if (!editMode || !isDirty()) return;
    event.preventDefault();
    event.returnValue = '';
  });

  document.addEventListener('click', (event) => {
    const link = event.target.closest('[data-request-link]');
    if (link && editMode && isDirty() && !window.confirm('Discard your replay edits and open another request?')) event.preventDefault();
  });

  const showEditError = (payload) => {
    const field = payload.field && document.querySelector(`[data-error-for="${payload.field}"]`);
    if (field) {
      field.textContent = payload.message || 'Unable to replay this request.';
      field.hidden = false;
      field.scrollIntoView({ block: 'nearest' });
    } else {
      window.alert(payload.message || 'Unable to replay this request.');
    }
  };

  const showNotice = (message, failed = false) => {
    const notice = document.querySelector('[data-replay-notice]');
    if (!notice) return;
    notice.textContent = message;
    notice.className = failed ? 'warning' : 'notice';
    notice.hidden = false;
  };

  editForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearErrors();
    const submit = editForm.querySelector('[data-edit-submit]');
    submit.disabled = true;
    submit.textContent = 'Replaying…';
    try {
      const response = await fetch(editForm.dataset.endpoint, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: page.dataset.token, headers_text: headersInput.value, body_text: bodyInput.value }),
      });
      const payload = await response.json().catch(() => ({ message: `Replay failed with HTTP ${response.status}.` }));
      if (!response.ok) {
        showEditError(payload);
        return;
      }
      showNotice(payload.message || (payload.ok ? 'Replay completed.' : 'Replay failed.'), !payload.ok);
    } catch (error) {
      showEditError({ message: `Inspector could not be reached: ${error.message}` });
    } finally {
      submit.disabled = false;
      submit.textContent = 'Replay edited request';
    }
  });

  const makeText = (tag, className, value) => {
    const node = document.createElement(tag);
    node.className = className;
    node.textContent = value;
    return node;
  };

  const renderList = (rows) => {
    if (!list || !empty) return;
    const previousIds = new Set(Array.from(list.querySelectorAll('[data-exchange-id]'), (node) => node.dataset.exchangeId));
    const fragment = document.createDocumentFragment();
    rows.forEach((row) => {
      const item = document.createElement('li');
      item.dataset.exchangeId = String(row.id);
      const link = document.createElement('a');
      link.href = `${base}/requests/${row.id}/`;
      link.dataset.requestLink = '';
      link.className = `request-row${String(row.id) === selectedId ? ' selected' : ''}${previousIds.has(String(row.id)) ? '' : ' is-new'}`;
      link.append(makeText('span', `method method-${String(row.method).toLowerCase()}`, row.method));
      link.append(makeText('span', 'request-path', row.path));
      const meta = makeText('span', 'request-meta', '');
      meta.append(makeText('b', row.response_status ? `status status-${String(row.response_status)[0]}xx` : '', row.response_status || '…'));
      if (row.duration_ms !== null) meta.append(document.createTextNode(` ${Math.round(row.duration_ms)} ms`));
      link.append(meta);
      item.append(link);
      fragment.append(item);
    });
    list.replaceChildren(fragment);
    list.hidden = rows.length === 0;
    empty.hidden = rows.length !== 0;

    if (selectedId && !rows.some((row) => String(row.id) === selectedId)) {
      document.querySelector('[data-removed-warning]')?.removeAttribute('hidden');
      document.querySelectorAll('[data-capture-action]').forEach((button) => { button.disabled = true; });
    }
  };

  const schedulePoll = (delay = retryDelay) => {
    window.clearTimeout(pollTimer);
    if (!document.hidden) pollTimer = window.setTimeout(poll, delay);
  };

  const poll = async () => {
    if (polling || document.hidden) return;
    polling = true;
    setLiveState('syncing', 'Syncing');
    try {
      const response = await fetch(`${base}/api/exchanges?cursor=${encodeURIComponent(cursor || '')}`, { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (payload.cursor !== cursor) renderList(payload.exchanges || []);
      cursor = payload.cursor;
      if (count) count.textContent = String(payload.total ?? 0);
      retryDelay = 2000;
      setLiveState('live', 'Live');
    } catch (_error) {
      retryDelay = Math.min(retryDelay * 2, 30000);
      setLiveState('offline', 'Reconnecting');
    } finally {
      polling = false;
      schedulePoll();
    }
  };

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      window.clearTimeout(pollTimer);
      setLiveState('paused', 'Paused');
    } else {
      retryDelay = 2000;
      poll();
    }
  });

  if (base && list) schedulePoll(2000);
})();
