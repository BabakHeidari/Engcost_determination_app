(() => {
  'use strict';

  const configNode = document.getElementById('profilePageConfig');
  if (!configNode) return;
  const config = JSON.parse(configNode.textContent);
  const users = new Map(config.users.map(user => [user.id, user]));
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;

  function showMessage(node, text, success = false) {
    node.textContent = text;
    node.className = `alert alert-${success ? 'success' : 'danger'}`;
  }

  function clearMessage(node) {
    node.textContent = '';
    node.className = 'alert d-none';
  }

  async function requestJson(url, options) {
    const headers = {'Content-Type': 'application/json', 'Accept': 'application/json', ...(options.headers || {})};
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;
    let response;
    try {
      response = await fetch(url, {...options, headers});
    } catch (_error) {
      throw new Error('ارتباط با سرور برقرار نشد.');
    }
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      if (response.status === 401 || response.status === 403 || response.redirected) {
        throw new Error('نشست یا دسترسی شما معتبر نیست. صفحه را تازه‌سازی کنید.');
      }
      throw new Error('پاسخ نامعتبر از سرور دریافت شد.');
    }
    let result;
    try {
      result = await response.json();
    } catch (_error) {
      throw new Error('پاسخ سرور قابل خواندن نیست.');
    }
    if (!response.ok) throw new Error(result.message || 'انجام درخواست امکان‌پذیر نشد.');
    return result;
  }

  function withSubmissionLock(button, operation) {
    if (button.disabled) return Promise.resolve();
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    return operation().finally(() => {
      button.disabled = false;
      button.removeAttribute('aria-busy');
    });
  }

  document.getElementById('profileBackButton')?.addEventListener('click', () => window.history.back());

  const editForm = document.getElementById('editUserForm');
  if (editForm) {
    const modal = document.getElementById('editUserModal');
    const message = document.getElementById('editUserMessage');
    const passwordFields = [editForm.elements.reset_password, editForm.elements.reset_confirmation];
    const clearPasswords = () => passwordFields.forEach(field => { field.value = ''; });
    modal.addEventListener('hidden.bs.modal', () => { clearPasswords(); clearMessage(message); });
    document.querySelectorAll('.edit-user').forEach(button => button.addEventListener('click', () => {
      const user = users.get(button.dataset.userId);
      if (!user) return;
      editForm.reset();
      clearMessage(message);
      editForm.elements.user_id.value = user.id;
      editForm.elements.expected_revision.value = user.revision;
      ['full_name', 'email', 'job_title', 'system_role'].forEach(key => { editForm.elements[key].value = user[key] || ''; });
      editForm.elements.is_active.checked = user.is_active;
      window.profileAccessManager.load('editAccessManager', user.access_state || {global: {}, factories: {}});
      window.profileAccessManager.toggleRole('editAccessManager', user.system_role);
      clearPasswords();
    }));
    editForm.elements.system_role.addEventListener('change', () => {
      window.profileAccessManager.toggleRole('editAccessManager', editForm.elements.system_role.value);
    });
    editForm.addEventListener('submit', event => {
      event.preventDefault();
      const submit = event.submitter;
      withSubmissionLock(submit, async () => {
        clearMessage(message);
        const id = editForm.elements.user_id.value;
        const payload = {
          expected_revision: Number(editForm.elements.expected_revision.value),
          full_name: editForm.elements.full_name.value,
          email: editForm.elements.email.value,
          job_title: editForm.elements.job_title.value,
          system_role: editForm.elements.system_role.value,
          is_active: editForm.elements.is_active.checked,
          access_grants: window.profileAccessManager.serialize('editAccessManager')
        };
        try {
          await requestJson(`${config.user_api_base_url}/${encodeURIComponent(id)}`, {method: 'PATCH', body: JSON.stringify(payload)});
          window.location.reload();
        } catch (error) {
          showMessage(message, error.message || 'ویرایش ناموفق بود.');
        }
      });
    });
    document.getElementById('resetPasswordSubmit').addEventListener('click', event => {
      const button = event.currentTarget;
      withSubmissionLock(button, async () => {
        const password = passwordFields[0].value;
        if (password !== passwordFields[1].value) {
          showMessage(message, 'گذرواژه و تکرار آن یکسان نیستند.');
          return;
        }
        const id = editForm.elements.user_id.value;
        try {
          const result = await requestJson(`${config.user_api_base_url}/${encodeURIComponent(id)}/password-reset`, {
            method: 'POST',
            body: JSON.stringify({password, password_confirmation: passwordFields[1].value, expected_revision: Number(editForm.elements.expected_revision.value)})
          });
          editForm.elements.expected_revision.value = result.user.revision;
          clearPasswords();
          showMessage(message, 'گذرواژه بازنشانی شد. کاربر در ورود بعدی باید آن را تغییر دهد.', true);
        } catch (error) {
          clearPasswords();
          showMessage(message, error.message || 'بازنشانی ناموفق بود.');
        }
      });
    });
  }

  const createUserForm = document.getElementById('createUserForm');
  if (createUserForm) {
    const modal = document.getElementById('createUserModal');
    const message = document.getElementById('createUserMessage');
    const role = document.getElementById('newUserRole');
    const fullAccessHelp = document.getElementById('fullAccessHelp');
    const passwordFields = [createUserForm.elements.initial_password, createUserForm.elements.initial_password_confirmation];
    const clearPasswords = () => passwordFields.forEach(field => { field.value = ''; });
    window.profileAccessManager.load('createAccessManager', {global: {}, factories: {}});
    modal.addEventListener('hidden.bs.modal', () => { clearPasswords(); clearMessage(message); });
    role.addEventListener('change', () => {
      const isAdmin = role.selectedOptions[0]?.dataset.isAdmin === 'true';
      fullAccessHelp.hidden = !isAdmin;
      window.profileAccessManager.toggleRole('createAccessManager', role.value);
    });
    role.dispatchEvent(new Event('change'));
    createUserForm.addEventListener('submit', event => {
      event.preventDefault();
      withSubmissionLock(event.submitter, async () => {
        clearMessage(message);
        if (passwordFields[0].value !== passwordFields[1].value) {
          showMessage(message, 'گذرواژه و تکرار آن یکسان نیستند.');
          return;
        }
        const payload = Object.fromEntries(new FormData(createUserForm).entries());
        payload.access_grants = window.profileAccessManager.serialize('createAccessManager');
        try {
          await requestJson(config.create_user_url, {method: 'POST', body: JSON.stringify(payload)});
          clearPasswords();
          window.location.reload();
        } catch (error) {
          clearPasswords();
          showMessage(message, error.message || 'ذخیره کاربر ناموفق بود.');
        }
      });
    });
  }

  const createFactoryForm = document.getElementById('createFactoryForm');
  if (createFactoryForm) {
    const modal = document.getElementById('createFactoryModal');
    const message = document.getElementById('createFactoryMessage');
    createFactoryForm.addEventListener('submit', event => {
      event.preventDefault();
      withSubmissionLock(event.submitter, async () => {
        clearMessage(message);
        try {
          await requestJson(config.create_factory_url, {
            method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(createFactoryForm).entries()))
          });
          createFactoryForm.reset();
          window.location.reload();
        } catch (error) {
          showMessage(message, error.message || 'ذخیره کارخانه ناموفق بود.');
        }
      });
    });
    modal.addEventListener('hidden.bs.modal', () => { createFactoryForm.reset(); clearMessage(message); });
  }
})();
