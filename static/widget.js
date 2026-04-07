(function() {
  var scripts = document.querySelectorAll('script[data-nerq-tool]');
  scripts.forEach(function(s) {
    var tool = s.getAttribute('data-nerq-tool');
    var style = s.getAttribute('data-nerq-style') || 'badge';

    fetch('https://nerq.ai/v1/preflight?target=' + encodeURIComponent(tool) + '&source=widget')
      .then(function(r) { return r.json(); })
      .then(function(d) {
        var el = document.createElement('div');
        var score = d.trust_score || '?';
        var grade = d.target_grade || '?';
        var name = d.target_name || tool;
        var color = score >= 70 ? '#16a34a' : score >= 50 ? '#ca8a04' : '#dc2626';

        if (style === 'badge') {
          el.innerHTML = '<a href="https://nerq.ai/is-' + encodeURIComponent(tool) + '-safe" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:4px;background:' + color + '22;color:' + color + ';font:600 12px system-ui;text-decoration:none">\u{1F6E1}\uFE0F Trust: ' + score + ' (' + grade + ')</a>';
        } else {
          el.innerHTML = '<div style="border:1px solid #e5e7eb;border-radius:8px;padding:12px;font:14px system-ui;max-width:280px"><div style="font-weight:600">\u{1F6E1}\uFE0F ' + name + '</div><div style="color:' + color + ';font-size:20px;font-weight:700">' + score + '/100 (' + grade + ')</div><div style="color:#6b7280;font-size:12px">' + (d.cves && d.cves.critical ? d.cves.critical + ' CVEs' : '0 CVEs') + ' \u00B7 Updated daily</div><a href="https://nerq.ai/is-' + encodeURIComponent(tool) + '-safe" target="_blank" rel="noopener" style="color:#2563eb;font-size:12px">Full report \u2192</a><div style="color:#9ca3af;font-size:10px;margin-top:4px">Powered by Nerq</div></div>';
        }
        s.parentNode.insertBefore(el, s.nextSibling);
      })
      .catch(function() {});
  });
})();
