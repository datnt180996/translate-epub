    (function () {
      // ===== App confirm dialog (replaces native window.confirm) =====
      const dialog = document.getElementById('appConfirmDialog');
      const titleEl = document.getElementById('appConfirmTitle');
      const bodyEl = document.getElementById('appConfirmBody');
      const iconEl = document.getElementById('appConfirmIcon');
      const iconWrap = document.getElementById('appConfirmIconWrap');
      const cancelBtn = document.getElementById('appConfirmCancel');
      const acceptBtn = document.getElementById('appConfirmAccept');

      const ICONS = {
        danger: 'delete',
        warn: 'priority_high',
        primary: 'check_circle',
        default: 'help',
      };

      function escapeHtml(value) {
        if (value == null) return '';
        return String(value).replace(/[&<>"']/g, (c) => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
      }

      function openConfirm(form, opts) {
        const variant = (opts.variant || 'default').toLowerCase();
        titleEl.textContent = opts.title || 'Xác nhận';
        // body is plain text, render as textContent via temp element so any
        // user-supplied message stays safe (no HTML injection via data attr).
        bodyEl.textContent = opts.message || '';
        acceptBtn.textContent = opts.confirmLabel || 'Xác nhận';
        cancelBtn.textContent = opts.cancelLabel || 'Hủy';
        iconEl.textContent = ICONS[variant] || ICONS.default;
        dialog.classList.remove(
          'app-confirm-variant-danger',
          'app-confirm-variant-warn',
          'app-confirm-variant-primary',
        );
        if (variant === 'danger' || variant === 'warn' || variant === 'primary') {
          dialog.classList.add('app-confirm-variant-' + variant);
        }
        if (typeof dialog.showModal === 'function') {
          dialog.showModal();
        } else {
          dialog.setAttribute('open', '');
        }
        dialog._pendingForm = form;
      }

      // Click outside the dialog (backdrop) cancels it.
      dialog.addEventListener('click', (event) => {
        if (event.target === dialog) {
          dialog.close('cancel');
        }
      });

      dialog.addEventListener('close', () => {
        const submittedValue = dialog.returnValue;
        const pending = dialog._pendingForm;
        dialog._pendingForm = null;
        if (submittedValue === 'confirm' && pending && pending.__confirmBypass !== true) {
          pending.__confirmBypass = true;
          let submitted = false;
          const onSubmitOnce = () => {
            // Run after HTMX / native handlers finish so we can clear bypass
            // for subsequent (re)submissions on the same form (e.g. same-page
            // htmx swaps where the page does not reload).
            pending.__confirmBypass = false;
          };
          pending.addEventListener('submit', () => { submitted = true; }, { capture: true, once: true });
          if (typeof pending.requestSubmit === 'function') {
            pending.requestSubmit();
          } else {
            pending.submit();
          }
          // Defer clearing until after the re-dispatched submit event loops.
          window.setTimeout(onSubmitOnce, 0);
          if (!submitted) pending.__confirmBypass = false;
        }
      });

      // Intercept submits on forms that opt-in via data-confirm.
      document.addEventListener('submit', (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) return;
        if (!form.hasAttribute('data-confirm')) return;
        if (form.__confirmBypass === true) return;
        event.preventDefault();
        openConfirm(form, {
          title: form.getAttribute('data-confirm-title') || 'Xác nhận',
          message: form.getAttribute('data-confirm-message') || '',
          variant: form.getAttribute('data-confirm-variant') || 'default',
          confirmLabel: form.getAttribute('data-confirm-confirm-label') || 'Xác nhận',
          cancelLabel: form.getAttribute('data-confirm-cancel-label') || 'Hủy',
        });
      }, true);

      // ===== App toast (replaces native window.alert for non-blocking notice) =====
      const TOAST_ICONS = {
        info: 'info',
        success: 'check_circle',
        warn: 'priority_high',
        error: 'error',
      };
      const TOAST_DEFAULT_TIMEOUT = 4500;

      function showToast(message, opts) {
        const options = opts || {};
        const kind = (options.kind || 'info').toLowerCase();
        const timeout = options.timeout || TOAST_DEFAULT_TIMEOUT;
        const stack = document.getElementById('appToastStack');
        if (!stack) return;
        const toast = document.createElement('div');
        toast.className = 'app-toast app-toast-' + kind;
        const icon = document.createElement('span');
        icon.className = 'material-symbols-outlined';
        icon.textContent = TOAST_ICONS[kind] || TOAST_ICONS.info;
        const body = document.createElement('div');
        body.className = 'app-toast-body';
        body.textContent = message == null ? '' : String(message);
        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'app-toast-close';
        close.setAttribute('aria-label', 'Đóng thông báo');
        close.innerHTML = '<span class="material-symbols-outlined" style="font-size:18px">close</span>';
        close.addEventListener('click', () => dismiss(toast));
        toast.appendChild(icon);
        toast.appendChild(body);
        toast.appendChild(close);
        stack.appendChild(toast);
        const timer = window.setTimeout(() => dismiss(toast), timeout);
        function dismiss(node) {
          if (!node || !node.parentNode) return;
          window.clearTimeout(timer);
          node.classList.add('app-toast-out');
          window.setTimeout(() => {
            if (node.parentNode) node.parentNode.removeChild(node);
          }, 220);
        }
      }

      // Forward window.alert(...) through the custom toast so existing call
      // sites stop showing the browser-native dialog. Flash messages from
      // server already render via .flash-area, so this only catches the
      // JS-triggered notices (e.g. batch batch-notice event).
      window.alert = function (message) { showToast(message, { kind: 'info' }); };
      window.appToast = showToast;
    })();