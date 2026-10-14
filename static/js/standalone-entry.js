/* The private capability stays out of request URLs, referrers and history. */
(async () => {
  const capability = location.hash.slice(1);
  history.replaceState(null, '', '/_local/');
  if (capability) {
    const response = await fetch('/_local/authorize', {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({capability})});
    if (!response.ok) {
      document.getElementById('startup-message').textContent = 'اتصال معتبر نیست. دوباره روی نشان برنامه کلیک کنید.';
      return;
    }
  }
  const status = await fetch('/_local/status');
  const state = status.ok ? (await status.json()).state : '';
  location.replace(state === 'ready' ? '/login' : '/_local/panel');
})().catch(() => {
  document.getElementById('startup-message').textContent = 'اتصال انجام نشد. دوباره روی نشان برنامه کلیک کنید.';
});
