  (() => {
    const reader = document.querySelector('.cr-reader');
    const novelId = reader?.dataset?.novelId || '';
    const chapterId = reader?.dataset?.chapterId || '';
    if (reader?.dataset?.autoReload === '1') {
      window.setTimeout(() => window.location.reload(), 5000);
    }
    const dialog = document.getElementById('chapterListDialog');
    const openButton = document.getElementById('openChapterList');
    const closeButton = document.getElementById('closeChapterList');
    const search = document.getElementById('chapterSearch');
    const list = document.getElementById('chapterList');
    const loading = document.getElementById('chapterListLoading');
    const noResults = document.getElementById('chapterNoResults');
    let items = [...document.querySelectorAll('.cr-dialog-item')];
    const normalize = (value) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('vi');

    const buildSearchText = (item) => {
      const index = (item.querySelector('.cr-dialog-index')?.textContent || '').trim();
      const title = (item.querySelector('.cr-dialog-title')?.textContent || '').trim();
      const fromAttr = item.dataset.search || '';
      const tokens = [
        index,
        `chuong ${index}`,
        `chương ${index}`,
        `chapter ${index}`,
        title,
        fromAttr,
      ];
      return normalize(tokens.filter(Boolean).join(' '));
    };

    const statusFromRow = (row) => {
      if (row.querySelector('.nd-pill-translated')) return ['translated', 'Đã dịch'];
      if (row.querySelector('.nd-pill-translating')) return ['translating', 'Đang dịch'];
      if (row.querySelector('.nd-pill-fetching')) return ['fetching', 'Đang tải'];
      if (row.querySelector('.nd-pill-fetched')) return ['fetched', 'Đã tải'];
      if (row.querySelector('.nd-pill-error')) return ['error', 'Có lỗi'];
      return ['not_fetched', 'Chưa tải'];
    };

    const applyFilter = () => {
      const query = normalize((search?.value || '').trim());
      const tokens = query ? query.split(/\s+/) : [];
      let visible = 0;
      items.forEach((item) => {
        const haystack = buildSearchText(item);
        const matches = tokens.length === 0 || tokens.every((token) => haystack.includes(token));
        item.hidden = !matches;
        if (matches) visible += 1;
      });
      if (noResults) noResults.hidden = visible !== 0;
    };

    const refreshItems = () => {
      items = [...list.querySelectorAll('.cr-dialog-item')];
      applyFilter();
    };

    const loadChapterItems = async () => {
      if (items.length) return;
      loading.hidden = false;
      loading.textContent = 'Đang tải danh sách chương...';
      try {
        const response = await fetch(`/novels/${novelId}/chapters`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const table = document.createElement('table');
        table.innerHTML = `<tbody>${await response.text()}</tbody>`;
        const fragment = document.createDocumentFragment();
        table.querySelectorAll('tr').forEach((row) => {
          const sourceLink = row.querySelector('.nd-title-cell a');
          const index = row.querySelector('.nd-idx')?.textContent.trim() || '';
          if (!sourceLink) return;

          const item = document.createElement('a');
          item.href = sourceLink.getAttribute('href');
          item.className = 'cr-dialog-item';
          if (item.href.endsWith(`/chapters/${chapterId}`)) item.classList.add('active');
          if (row.dataset.search) item.dataset.search = row.dataset.search;

          const indexNode = document.createElement('span');
          indexNode.className = 'cr-dialog-index';
          indexNode.textContent = index;
          const titleNode = document.createElement('span');
          titleNode.className = 'cr-dialog-title';
          titleNode.textContent = sourceLink.textContent.trim();
          const [statusKey, statusLabel] = statusFromRow(row);
          const statusNode = document.createElement('span');
          statusNode.className = `cr-dialog-status cr-dialog-status-${statusKey}`;
          statusNode.textContent = statusLabel;
          item.append(indexNode, titleNode, statusNode);
          fragment.appendChild(item);
        });
        list.insertBefore(fragment, loading);
        refreshItems();
        loading.hidden = true;
        if (!items.length) {
          loading.textContent = 'Không có chương nào.';
          loading.hidden = false;
        }
      } catch (error) {
        loading.textContent = 'Không thể tải danh sách chương. Vui lòng thử lại.';
      }
    };

    openButton.addEventListener('click', async () => {
      dialog.showModal();
      await loadChapterItems();
      refreshItems();
      const activeItem = dialog.querySelector('.cr-dialog-item.active');
      if (activeItem && !activeItem.hidden) activeItem.scrollIntoView({ block: 'center' });
      const value = search.value;
      search.value = '';
      if (value) {
        search.value = value;
      }
      search.focus();
    });
    closeButton.addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', (event) => {
      const rect = dialog.getBoundingClientRect();
      const inDialog = event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom;
      if (!inDialog) dialog.close();
    });
    search.addEventListener('input', applyFilter);
    applyFilter();

    const chapterNav = document.querySelector('.cr-chapter-nav');
    const prevUrl = chapterNav?.dataset.prevUrl || '';
    const nextUrl = chapterNav?.dataset.nextUrl || '';
    const isTypingTarget = (target) => {
      if (!target) return false;
      const tag = target.tagName;
      return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
    };
    document.addEventListener('keydown', (event) => {
      if (event.defaultPrevented) return;
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      if (dialog.open) return;
      if (isTypingTarget(event.target)) return;
      if (event.key === 'ArrowLeft' && prevUrl) {
        event.preventDefault();
        window.location.assign(prevUrl);
      } else if (event.key === 'ArrowRight' && nextUrl) {
        event.preventDefault();
        window.location.assign(nextUrl);
      }
    });
  })();
