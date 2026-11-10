document.querySelectorAll('.chrome').forEach(function (el) {
  el.outerHTML =
    '<div class="status"><span>9:41</span><span style="font-size:13px;letter-spacing:.1em">●●● ▲ ▬</span></div>' +
    '<div class="dm"><span style="font-size:20px">‹</span><div class="av sm">J</div><span class="name">Juno</span><span class="tag">APP</span></div>';
});
document.querySelectorAll('[data-juno]').forEach(function (el) {
  el.insertAdjacentHTML('afterbegin',
    '<div class="av">J</div>');
  var body = el.querySelector('.body');
  body.insertAdjacentHTML('afterbegin',
    '<div class="nl"><b>Juno</b><span class="tag">APP</span><span class="t">' + el.dataset.juno + '</span></div>');
});
document.querySelectorAll('[data-me]').forEach(function (el) {
  el.insertAdjacentHTML('afterbegin', '<div class="av me">M</div>');
  el.querySelector('.body').insertAdjacentHTML('afterbegin',
    '<div class="nl"><b>You</b><span class="t">' + el.dataset.me + '</span></div>');
});
(function () {
  var m = location.search.match(/only=(\d)/);
  if (!m) return;
  document.querySelector('.lbl') && (document.querySelector('.lbl').style.display = 'none');
  document.body.style.padding = '0';
  document.querySelectorAll('.phone').forEach(function (p, i) { if (i !== +m[1]) p.style.display = 'none'; });
})();
