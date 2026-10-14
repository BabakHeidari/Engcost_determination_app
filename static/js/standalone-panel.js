if (document.body.dataset.state === 'preparing') {
  const timer = setInterval(async () => {
    try {
      const response = await fetch('/_local/status');
      const state = (await response.json()).state;
      if (state !== 'preparing') {
        clearInterval(timer);
        if (state === 'ready') location.replace('/login');
        else location.reload();
      }
    } catch (_) { clearInterval(timer); location.reload(); }
  }, 500);
}
