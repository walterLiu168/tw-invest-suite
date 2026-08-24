/* 3 段字級切換器 — 套用在 readme / watchlist / sectors */
(function () {
  var KEY = 'textsize';
  function getSize() {
    try { return localStorage.getItem(KEY) || 'small'; } catch (e) { return 'small'; }
  }
  function setSize(s) {
    try { localStorage.setItem(KEY, s); } catch (e) {}
    document.documentElement.setAttribute('data-textsize', s);
    updateButtons(s);
  }
  function updateButtons(s) {
    document.querySelectorAll('.ts-tool button[data-size]').forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-size') === s);
    });
  }
  // 套用 user choice
  setSize(getSize());
  // 插入 UI（每頁都共用）
  if (!document.querySelector('.ts-tool')) {
    var t = document.createElement('div');
    t.className = 'ts-tool';
    t.setAttribute('role', 'group');
    t.setAttribute('aria-label', '字級');
    t.innerHTML =
      '<button type="button" data-size="small">小</button>' +
      '<button type="button" data-size="medium">中</button>' +
      '<button type="button" data-size="large">大</button>';
    document.body.appendChild(t);
    t.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-size]');
      if (b) setSize(b.getAttribute('data-size'));
    });
    updateButtons(getSize());
  }
})();
