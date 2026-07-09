  (() => {
    const chapterScrollPositions = new WeakMap();
    const search = document.getElementById('nd-chapter-search');
    const tbody = document.getElementById('nd-chapter-tbody');
    const noResults = document.getElementById('nd-chapter-no-results');
    const batchForm = document.getElementById('nd-batch-form');
    const batchSubmit = document.getElementById('nd-batch-submit');
    const batchSubmitIcon = document.getElementById('nd-batch-submit-icon');
    const batchSubmitLabel = document.getElementById('nd-batch-submit-label');
    const batchProgress = document.getElementById('nd-batch-progress');
    const batchCount = document.getElementById('nd-batch-count');
    const batchEligibleCount = document.getElementById('nd-batch-eligible-count');
    const selectAll = document.getElementById('nd-select-all');
    const tableWrap = tbody?.closest('.nd-table-wrap');
    const novelId = batchForm?.dataset?.novelId || 'unknown';
    const batchScrollKey = `novel-batch-scroll:${novelId}`;
    const pollIntervalMs = 5000;
    const normalize = (value) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('vi');
    let batchRunning = batchForm?.dataset?.disabled === '1';
    let pollActive = tbody?.dataset.pollActive === '1';
    let receivedPollHeader = false;
    let pollInFlight = false;
    let pollTimer = null;

    const ACTIVE_TBODY_SELECTOR = 'tr[data-display-status="queue"], tr[data-display-status="translating"], tr[data-display-status="fetching"]';
    const tbodyHasActiveRows = () => Boolean(tbody && tbody.querySelector(ACTIVE_TBODY_SELECTOR));
    const rowIsActive = (row) => Boolean(row && row.matches && row.matches(ACTIVE_TBODY_SELECTOR));
    const recomputePollActive = () => {
      const domActive = tbodyHasActiveRows();
      const serverActive = receivedPollHeader
        ? tbody?.dataset.pollActive === '1'
        : domActive;
      pollActive = domActive || serverActive;
      if (tbody) tbody.dataset.pollActive = pollActive ? '1' : '0';
    };

    const attachRowPolling = (row) => {
      if (!row || !row.dataset || !row.dataset.chapterId || !rowIsActive(row)) return;
      row.setAttribute('hx-get', `/novels/${novelId}/chapters/${row.dataset.chapterId}/row`);
      row.setAttribute('hx-trigger', 'every 2s');
      row.setAttribute('hx-target', 'this');
      row.setAttribute('hx-swap', 'outerHTML');
      row.setAttribute('hx-select', `#chapter-row-${row.dataset.chapterId}`);
      row.setAttribute('hx-disabled-elt', 'this');
      row.setAttribute('hx-on::before-request', "this.setAttribute('aria-busy','1')");
      row.setAttribute('hx-on::after-request', "this.removeAttribute('aria-busy')");
      if (window.htmx) htmx.process(row);
    };

    let selected = new Set();
    let cachedEligible = [];
    let lastClickedCheckbox = null;
    let quickControls = [];

    const collectQuickControls = () => {
      quickControls = Array.from(document.querySelectorAll(
        '#nd-range-from, #nd-range-to, #nd-select-range, #nd-select-visible, [data-select-next], #nd-clear-selection'
      ));
    };

    const setQuickControlsDisabled = () => {
      quickControls.forEach((el) => {
        el.disabled = batchRunning;
      });
    };

    const computeEligible = () => {
      if (!tbody) return [];
      const ids = [];
      tbody.querySelectorAll('tr.nd-row').forEach((row) => {
        if (row.dataset.batchEligible === '1') {
          const cb = row.querySelector('input.nd-batch-checkbox');
          if (cb) ids.push(cb.dataset.chapterId);
        }
      });
      return ids;
    };

    const refreshEligibleCache = () => {
      cachedEligible = computeEligible();
      return cachedEligible;
    };

    const refreshSelectedSubset = () => {
      const eligible = new Set(refreshEligibleCache());
      Array.from(selected).forEach((id) => {
        if (!eligible.has(id)) selected.delete(id);
      });
    };

    const eligibleRows = () => {
      if (!tbody) return [];
      return Array.from(tbody.querySelectorAll('tr.nd-row')).filter(
        (row) => row.dataset.batchEligible === '1'
      );
    };

    const visibleEligibleRows = () => eligibleRows().filter((row) => !row.hidden);

    const collectIdsFromRows = (rows) => rows
      .map((row) => row.dataset.chapterId)
      .filter((id) => id);

    const setSelectionForRows = (rows, checked) => {
      const ids = collectIdsFromRows(rows);
      ids.forEach((id) => {
        if (checked) selected.add(id);
        else selected.delete(id);
      });
    };

    const selectRangeByIndex = (from, to) => {
      const lo = Math.max(1, Math.min(from, to));
      const hi = Math.max(from, to);
      const matches = eligibleRows().filter((row) => {
        const idx = parseInt(row.dataset.chapterIndex || '0', 10);
        return idx >= lo && idx <= hi;
      });
      setSelectionForRows(matches, true);
    };

    const selectNextEligible = (count) => {
      if (!Number.isFinite(count) || count <= 0) return 0;
      const target = visibleEligibleRows().filter(
        (row) => !selected.has(row.dataset.chapterId)
      );
      const picks = target.slice(0, count);
      setSelectionForRows(picks, true);
      return picks.length;
    };

    const clearSelection = () => {
      selected.clear();
    };

    const applySelectionUI = () => {
      syncCheckboxes();
      buildHiddenInputs();
      updateBatchUI();
    };

    const buildHiddenInputs = () => {
      if (!batchForm) return;
      batchForm.querySelectorAll('input.nd-batch-hidden').forEach((el) => el.remove());
      selected.forEach((id) => {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'chapter_ids';
        input.value = id;
        input.className = 'nd-batch-hidden';
        batchForm.appendChild(input);
      });
    };

    const updateBatchUI = () => {
      if (batchCount) batchCount.textContent = `${selected.size} đã chọn`;
      const eligible = cachedEligible.length ? cachedEligible : refreshEligibleCache();
      const totalEligible = eligible.length;
      if (batchEligibleCount) batchEligibleCount.textContent = `Có ${totalEligible} chương đủ điều kiện`;
      const allChecked = totalEligible > 0 && eligible.every((id) => selected.has(id));
      const someChecked = eligible.some((id) => selected.has(id));
      if (selectAll) {
        selectAll.checked = allChecked;
        selectAll.indeterminate = !allChecked && someChecked;
        selectAll.disabled = batchRunning || totalEligible === 0;
      }
      if (batchSubmit) {
        const locked = batchRunning || selected.size === 0;
        batchSubmit.disabled = locked;
      }
      if (batchSubmitLabel) {
        batchSubmitLabel.textContent = batchRunning ? 'Đang dịch hàng đợi' : 'Dịch chương đã chọn';
      }
      if (batchSubmitIcon) batchSubmitIcon.classList.toggle('nd-spin', batchRunning);
      if (batchProgress) batchProgress.hidden = !batchRunning;
      if (batchForm) batchForm.dataset.disabled = batchRunning ? '1' : '0';
      setQuickControlsDisabled();
    };

    const refreshBatchRunning = () => {
      if (!tbody) return;
      batchRunning = Boolean(tbody.querySelector(
        'tr[data-display-status="queue"], tr[data-display-status="translating"]'
      ));
    };

    const showOptimisticBatchStatuses = () => {
      if (!tbody || selected.size === 0) return;
      const selectedRows = Array.from(tbody.querySelectorAll('tr.nd-row')).filter((row) => {
        const checkbox = row.querySelector('input.nd-batch-checkbox');
        return checkbox && selected.has(checkbox.dataset.chapterId);
      });
      selectedRows.forEach((row, index) => {
        const status = index === 0 ? 'translating' : 'queue';
        row.dataset.displayStatus = status;
        row.dataset.batchEligible = '0';
        row.classList.toggle('nd-row-active', status === 'translating');
        attachRowPolling(row);
        const checkbox = row.querySelector('input.nd-batch-checkbox');
        if (checkbox) checkbox.disabled = true;
        const statusCell = row.querySelector('.nd-status-cell');
        if (!statusCell) return;
        statusCell.innerHTML = status === 'translating'
          ? '<span class="nd-pill nd-pill-translating"><span class="material-symbols-outlined nd-spin">sync</span>Translating</span>'
          : '<span class="nd-pill nd-pill-queue"><span class="material-symbols-outlined">schedule</span>Queue</span>';
      });
    };

    const clearPollTimer = () => {
      if (pollTimer === null) return;
      window.clearTimeout(pollTimer);
      pollTimer = null;
    };

    const requestChapterRefresh = () => {
      clearPollTimer();
      if (!tbody || !pollActive || pollInFlight || document.hidden) return;
      pollInFlight = true;
      htmx.trigger(document.body, 'novel-chapters-refresh');
    };

    const scheduleChapterRefresh = () => {
      clearPollTimer();
      if (!tbody || !pollActive || pollInFlight || document.hidden) return;
      pollTimer = window.setTimeout(requestChapterRefresh, pollIntervalMs);
    };

    const syncCheckboxes = () => {
      if (!tbody) return;
      tbody.querySelectorAll('input.nd-batch-checkbox').forEach((cb) => {
        const id = cb.dataset.chapterId;
        cb.checked = selected.has(id);
      });
    };

    const applyFilter = () => {
      if (!tbody || !noResults) return;
      const query = normalize((search?.value || '').trim());
      let visible = 0;
      tbody.querySelectorAll('tr.nd-row').forEach((row) => {
        const matches = !query || normalize(row.dataset.search || '').includes(query);
        row.hidden = !matches;
        if (matches) visible += 1;
      });
      noResults.hidden = visible !== 0;
    };

    const onCheckboxChange = (event) => {
      const cb = event.target;
      if (!cb.classList || !cb.classList.contains('nd-batch-checkbox')) return;
      const id = cb.dataset.chapterId;
      if (!id) return;
      if (event.shiftKey && lastClickedCheckbox && lastClickedCheckbox !== cb) {
        const checkboxes = Array.from(tbody.querySelectorAll('input.nd-batch-checkbox'));
        const fromIdx = checkboxes.indexOf(lastClickedCheckbox);
        const toIdx = checkboxes.indexOf(cb);
        if (fromIdx !== -1 && toIdx !== -1) {
          const [lo, hi] = fromIdx < toIdx ? [fromIdx, toIdx] : [toIdx, fromIdx];
          const targetState = cb.checked;
          for (let i = lo; i <= hi; i += 1) {
            const sib = checkboxes[i];
            const sibId = sib.dataset.chapterId;
            if (!sibId) continue;
            const sibRow = sib.closest('tr.nd-row');
            if (!sibRow || sibRow.dataset.batchEligible !== '1') continue;
            sib.checked = targetState;
            if (targetState) selected.add(sibId);
            else selected.delete(sibId);
          }
        }
      } else {
        if (cb.checked) selected.add(id);
        else selected.delete(id);
      }
      lastClickedCheckbox = cb;
      buildHiddenInputs();
      updateBatchUI();
    };

    const onSelectAll = () => {
      if (!selectAll) return;
      const eligible = cachedEligible.length ? cachedEligible : refreshEligibleCache();
      if (selectAll.checked) {
        eligible.forEach((id) => selected.add(id));
      } else {
        eligible.forEach((id) => selected.delete(id));
      }
      syncCheckboxes();
      buildHiddenInputs();
      updateBatchUI();
    };

    document.body.addEventListener('change', onCheckboxChange);
    if (selectAll) selectAll.addEventListener('change', onSelectAll);

    const rangeFromInput = document.getElementById('nd-range-from');
    const rangeToInput = document.getElementById('nd-range-to');
    const rangeBtn = document.getElementById('nd-select-range');
    const visibleBtn = document.getElementById('nd-select-visible');
    const clearBtn = document.getElementById('nd-clear-selection');
    const nextButtons = Array.from(document.querySelectorAll('[data-select-next]'));

    if (rangeBtn) {
      rangeBtn.addEventListener('click', (event) => {
        event.preventDefault();
        if (batchRunning) return;
        const from = parseInt(rangeFromInput?.value || '', 10);
        const to = parseInt(rangeToInput?.value || '', 10);
        if (!Number.isFinite(from) || !Number.isFinite(to)) return;
        selectRangeByIndex(from, to);
        applySelectionUI();
      });
    }
    if (visibleBtn) {
      visibleBtn.addEventListener('click', (event) => {
        event.preventDefault();
        if (batchRunning) return;
        setSelectionForRows(visibleEligibleRows(), true);
        applySelectionUI();
      });
    }
    if (clearBtn) {
      clearBtn.addEventListener('click', (event) => {
        event.preventDefault();
        if (batchRunning) return;
        clearSelection();
        applySelectionUI();
      });
    }
    nextButtons.forEach((btn) => {
      btn.addEventListener('click', (event) => {
        event.preventDefault();
        if (batchRunning) return;
        const count = parseInt(btn.dataset.selectNext || '0', 10);
        selectNextEligible(count);
        applySelectionUI();
      });
    });
    if (batchForm) {
      batchForm.addEventListener('submit', (event) => {
        if (selected.size === 0 || batchRunning) {
          event.preventDefault();
          return false;
        }
        if (window.htmx) return;
        try {
          sessionStorage.setItem(batchScrollKey, JSON.stringify({
            windowY: window.scrollY,
            tableY: tableWrap?.scrollTop || 0,
          }));
        } catch (_) {
          // The translation can still start when browser storage is unavailable.
        }
      });
    }

    try {
      const savedScroll = JSON.parse(sessionStorage.getItem(batchScrollKey) || 'null');
      if (savedScroll) {
        sessionStorage.removeItem(batchScrollKey);
        if (tableWrap) tableWrap.scrollTop = savedScroll.tableY || 0;
        requestAnimationFrame(() => {
          window.scrollTo(0, savedScroll.windowY || 0);
          if (tableWrap) tableWrap.scrollTop = savedScroll.tableY || 0;
        });
      }
    } catch (_) {
      try { sessionStorage.removeItem(batchScrollKey); } catch (_) {}
    }

    document.body.addEventListener('htmx:beforeSwap', (event) => {
      const target = event.detail.target;
      if (!target || target.id !== 'nd-chapter-tbody') return;

      const responseText = event.detail.xhr?.responseText || '';
      if (responseText.includes('<body class="novel-detail-page"')) {
        event.detail.shouldSwap = false;
        pollInFlight = false;
        pollActive = true;
        target.dataset.pollActive = '1';
        scheduleChapterRefresh();
        return;
      }

      const scrollContainer = target.closest('.nd-table-wrap');
      if (scrollContainer) {
        chapterScrollPositions.set(target, scrollContainer.scrollTop);
      }
    });

    document.body.addEventListener('htmx:beforeRequest', (event) => {
      const requestElement = event.detail.elt;
      if (requestElement !== tbody && requestElement !== batchForm) return;
      clearPollTimer();
      pollInFlight = true;
      if (requestElement === batchForm) {
        batchRunning = true;
        pollActive = true;
        if (tbody) tbody.dataset.pollActive = '1';
        showOptimisticBatchStatuses();
        lastClickedCheckbox = null;
        updateBatchUI();
      }
    });

    document.body.addEventListener('htmx:afterRequest', (event) => {
      const requestElement = event.detail.elt;
      if (requestElement !== tbody && requestElement !== batchForm) return;
      pollInFlight = false;
      const activeHeader = event.detail.xhr?.getResponseHeader('X-Novel-Poll-Active');
      if (activeHeader === '1' || activeHeader === '0') {
        receivedPollHeader = true;
        tbody.dataset.pollActive = activeHeader;
      }
      if (requestElement === tbody) {
        recomputePollActive();
      }
      scheduleChapterRefresh();
    });

    document.body.addEventListener('novel-batch-notice', (event) => {
      batchRunning = false;
      pollActive = false;
      updateBatchUI();
      htmx.trigger(document.body, 'novel-chapters-refresh');
      const message = event.detail?.message;
      if (message) appToast(message, { kind: 'info' });
    });

    document.body.addEventListener('htmx:afterSwap', (event) => {
      const target = event.detail.target;
      if (!target || target.id !== 'nd-chapter-tbody') return;

      refreshBatchRunning();
      recomputePollActive();
      scheduleChapterRefresh();
      refreshSelectedSubset();
      syncCheckboxes();
      buildHiddenInputs();
      updateBatchUI();
      applyFilter();

      const scrollContainer = target.closest('.nd-table-wrap');
      const scrollTop = chapterScrollPositions.get(target);
      lastClickedCheckbox = null;
      if (!scrollContainer || scrollTop === undefined) return;

      scrollContainer.scrollTop = scrollTop;
      requestAnimationFrame(() => {
        scrollContainer.scrollTop = scrollTop;
      });
    });

    document.body.addEventListener('htmx:afterSwap', (event) => {
      const target = event.detail.target;
      if (!target || !target.matches || !target.matches('tr.nd-row')) return;

      refreshBatchRunning();
      recomputePollActive();
      scheduleChapterRefresh();
      refreshSelectedSubset();
      syncCheckboxes();
      buildHiddenInputs();
      updateBatchUI();
      applyFilter();
    });

    const onTbodySwapError = (event) => {
      const target = event.detail?.target || (event.detail?.elt && event.detail.elt.id === 'nd-chapter-tbody' ? event.detail.elt : null);
      if (!target || target.id !== 'nd-chapter-tbody') return;
      pollInFlight = false;
      recomputePollActive();
      scheduleChapterRefresh();
    };
    document.body.addEventListener('htmx:swapError', onTbodySwapError);
    document.body.addEventListener('htmx:responseError', onTbodySwapError);
    document.body.addEventListener('htmx:sendError', onTbodySwapError);

    if (search) {
      search.addEventListener('input', applyFilter);
      applyFilter();
    }

    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        clearPollTimer();
      } else if (pollActive && !pollInFlight) {
        requestChapterRefresh();
      }
    });

    collectQuickControls();
    refreshSelectedSubset();
    syncCheckboxes();
    buildHiddenInputs();
    updateBatchUI();
    scheduleChapterRefresh();
  })();
