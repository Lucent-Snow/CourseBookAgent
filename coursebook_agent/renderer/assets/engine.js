/* CourseBookAgent MD Viewer Engine — shared logic (no external deps at runtime) */
(function () {
  'use strict';

  var SAMPLE = null;
  var headings = [];
  var currentChapterIndex = -1;

  function sampleText() {
    if (SAMPLE !== null) return SAMPLE;
    var el = document.getElementById('sample-md');
    SAMPLE = el ? el.textContent.replace(/^\uFEFF/, '') : '';
    return SAMPLE;
  }

  function setupMarked() {
    if (!window.marked) { console.error('marked not loaded'); return false; }
    marked.setOptions({ gfm: true, breaks: false, mangle: false, headerIds: true });
    return true;
  }

  function renderTo(html, container) {
    container.innerHTML = html;
    container.classList.add('book-rendered');
  }

  /* Decorate structural bits: callouts, time-links, hr+h1 chapter rhythm */
  function decorate(container) {
    // blockquote callouts
    container.querySelectorAll('blockquote').forEach(function (bq) {
      var t = bq.textContent || '';
      bq.classList.add('cq');
      if (t.indexOf('【例题】') !== -1) bq.classList.add('cq-example');
      else if (t.indexOf('【步骤】') !== -1) bq.classList.add('cq-procedure');
      else if (t.indexOf('【易错】') !== -1 || t.indexOf('⚠️') !== -1 || t.indexOf('⚠') !== -1) bq.classList.add('cq-warning');
      else if (t.indexOf('旁注') !== -1) bq.classList.add('cq-note');
      else if (/^模块：/.test(t.trim()) || t.indexOf('根据智云课堂字幕') !== -1 || t.indexOf('本讲内容待生成') !== -1) bq.classList.add('cq-meta');
      // mark source-ref italics inside callout
      bq.querySelectorAll('em').forEach(function (em) { if ((em.textContent||'').indexOf('来源') !== -1) em.classList.add('cq-source'); });
    });

    // italic time-link paragraphs
    container.querySelectorAll('p').forEach(function (p) {
      var txt = p.textContent || '';
      var em = p.querySelector('em');
      if (em && /^字幕时间段/.test(txt.trim())) { p.classList.add('time-links'); }
      if (/^适用：/.test(txt.trim())) p.classList.add('when-use');
    });

    // heading ids (marked already assigns; guarantee unique anyway)
    container.querySelectorAll('h1, h2, h3').forEach(function (h) {
      if (!h.id) h.id = h.textContent.replace(/\s+/g, '-').replace(/[^\w\u4e00-\u9fa5-]/g, '');
    });
  }

  function setBookMeta(container) {
    var h1 = container.querySelector('h1');
    if (h1) document.title = h1.textContent;
    var metaEl = document.getElementById('book-meta-title');
    if (metaEl && h1) metaEl.textContent = h1.textContent;
  }

  /* Build sidebar TOC from h1/h2 */
  function buildToc(container, listEl) {
    if (!listEl) return;
    listEl.innerHTML = '';
    var frag = document.createDocumentFragment();
    var stack = []; // h1 li, h2 li
    container.querySelectorAll('h1, h2').forEach(function (h) {
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = '#' + h.id;
      a.textContent = h.textContent;
      a.dataset.level = h.tagName === 'H1' ? '1' : '2';
      li.appendChild(a);
      if (h.tagName === 'H1') {
        li.dataset.h1 = '1';
        frag.appendChild(li);
        stack = [li];
      } else {
        if (stack.length) {
          var sub = stack[0].querySelector('ul');
          if (!sub) { sub = document.createElement('ul'); stack[0].appendChild(sub); }
          sub.appendChild(li);
        } else {
          frag.appendChild(li);
        }
      }
    });
    listEl.appendChild(frag);
  }

  function scrollSpy(listEl) {
    if (!listEl || !('IntersectionObserver' in window)) return;
    var links = Array.prototype.slice.call(listEl.querySelectorAll('a'));
    var map = {};
    links.forEach(function (a) { map[a.getAttribute('href').slice(1)] = a; });
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        var a = map[en.target.id];
        if (a) {
          if (en.isIntersecting) {
            links.forEach(function (x) { x.classList.remove('active'); });
            a.classList.add('active');
            var li = a.closest('li');
            if (li && li.parentElement && li.parentElement.closest('li')) {
              var p = li.parentElement.closest('li').querySelector(':scope > a');
              if (p) p.classList.add('active');
            }
          }
        }
      });
    }, { rootMargin: '-20% 0px -70% 0px' });
    document.querySelectorAll('#content h1, #content h2').forEach(function (h) { obs.observe(h); });
  }

  /* Fix the md's own inline TOC anchors to match marked's heading ids */
  function fixInlineToc(container) {
    var h1s = Array.prototype.slice.call(container.querySelectorAll('h1'));
    var seen = {};
    h1s.forEach(function (h) {
      var key = h.textContent;
      seen[key] = (seen[key] || 0) + 1;
      h.dataset.occ = String(seen[key]);
    });
    container.querySelectorAll('h2').forEach(function (h2) {
      if ((h2.textContent || '').trim() !== '目录') return;
      var list = h2.nextElementSibling;
      while (list && list.tagName !== 'UL') list = list.nextElementSibling;
      if (!list) return;
      list.querySelectorAll('a').forEach(function (a) {
        var raw = a.textContent;
        var m = raw.match(/^(.*?)（/);
        var title = m ? m[1].trim() : raw.trim();
        var occ = 0;
        var found = null;
        for (var i = 0; i < h1s.length; i++) {
          var txt = h1s[i].textContent;
          if (txt === title || txt.indexOf(title) === 0 || title.indexOf(txt) === 0) {
            occ += 1;
            if (title === txt || txt.indexOf(title) === 0) { found = h1s[i]; break; }
          }
        }
        if (found) a.setAttribute('href', '#' + found.id);
      });
    });
  }

  /* Turn recurring sections into cards / banners for modern & reader skins */
  function enrichSections(container) {
    if (!container) return;
    var map = {
      '知识地图':'card-grid', '学习路径':'card-grid', '如何使用本书':'card-grid',
      '本章重点':'key-list', '核心概念':'concept-list', '先修概念':'concept-list',
      '易错点':'mistake-list', '课堂例子与补充':'example-list',
      '本章小结':'summary-list', '来源':'source-list'
    };
    var bridge = { '承上':'bridge bridge-prev', '启下':'bridge bridge-next' };
    container.querySelectorAll('h2').forEach(function (h) {
      var t = (h.textContent || '').trim();
      if (map[t]) {
        h.classList.add('sec-' + t);
        var n = h.nextElementSibling;
        while (n && n.tagName === 'P' && (n.textContent||'').trim() === '') n = n.nextElementSibling;
        if (n && /^UL|^OL/.test(n.tagName)) {
          n.classList.add(map[t]);
          Array.prototype.forEach.call(n.children, function (li) { li.classList.add('mini-card'); });
        }
      }
      if (bridge[t]) {
        var p = h.nextElementSibling;
        while (p && p.tagName !== 'P') p = p.nextElementSibling;
        if (p) bridge[t].split(' ').forEach(function (c) { p.classList.add(c); });
      }
    });
  }


  /* ---------- inline video player for node jump ---------- */
  var _playerStylesInjected = false;
  function ensurePlayerStyles() {
    if (_playerStylesInjected) return;
    _playerStylesInjected = true;
    var st = document.createElement('style');
    st.textContent = [
      '#cba-overlay{position:fixed;inset:0;z-index:9999;background:rgba(10,12,16,.88);display:none;align-items:center;justify-content:center;font-family:var(--sans,"PingFang SC","Microsoft YaHei",system-ui,sans-serif)}',
      '#cba-overlay.open{display:flex}',
      '#cba-overlay .cba-box{width:min(1100px,94vw);background:#000;border-radius:14px;overflow:hidden;box-shadow:0 24px 80px rgba(0,0,0,.6)}',
      '#cba-overlay .cba-top{display:flex;align-items:center;gap:10px;padding:10px 14px;background:#14171c;color:#e8ecf3;font-size:13.5px}',
      '#cba-overlay .cba-top .cba-t{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
      '#cba-overlay .cba-top button{border:1px solid #333b47;background:#1d222a;color:#cdd4de;border-radius:8px;padding:5px 12px;cursor:pointer;font-size:12.5px}',
      '#cba-overlay .cba-top button:hover{background:#2a3341}',
      '#cba-overlay video{width:100%;max-height:80vh;display:block;background:#000}',
      '#cba-overlay .cba-msg{padding:26px;color:#cdd4de;text-align:center;font-size:14px;background:#0c0e12;line-height:1.9}',
      '#cba-overlay .cba-msg a{color:#7aa7ff}'
    ].join('\n');
    (document.head || document.documentElement).appendChild(st);
  }
  function openVideoNode(chapter, sec, replayUrl) {
    var files = (typeof window.BOOK_VIDEO_FILES === 'object' && window.BOOK_VIDEO_FILES) ? window.BOOK_VIDEO_FILES : {};
    var file = files[chapter];
    if (!file) { if (replayUrl) window.open(replayUrl, '_blank'); return; }
    ensurePlayerStyles();
    var overlay = document.getElementById('cba-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'cba-overlay';
      overlay.innerHTML = '<div class="cba-box">' +
        '<div class="cba-top"><span class="cba-t"></span>' +
        '<button class="cba-replay">回放页</button><button class="cba-close">✕ 关闭</button></div>' +
        '<video controls playsinline preload="metadata"></video>' +
        '<div class="cba-msg" style="display:none"></div></div>';
      document.body.appendChild(overlay);
      overlay.querySelector('.cba-close').addEventListener('click', closeVideoNode);
      overlay.addEventListener('click', function (e) { if (e.target === overlay) closeVideoNode(); });
    }
    var box = overlay.querySelector('.cba-box');
    var video = overlay.querySelector('video');
    var msg = overlay.querySelector('.cba-msg');
    var replayBtn = overlay.querySelector('.cba-replay');
    overlay.querySelector('.cba-t').textContent = chapter + '  ·  ' + (function (t) {
      var h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), secs = t % 60;
      return (h ? String(h).padStart(2, '0') + ':' : '') + String(m).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
    })(sec);
    replayBtn.onclick = function () { if (replayUrl) window.open(replayUrl, '_blank'); };
    msg.style.display = 'none';
    box.style.display = '';
    video.style.display = 'block';
    overlay.classList.add('open');
    video.removeAttribute('src');
    video.load();
    video.src = file;
    var done = false;
    function jump() {
      if (done) return;
      done = true;
      try { if (isFinite(video.duration) && video.duration > 0) video.currentTime = Math.min(sec, video.duration - 0.5); } catch (e) {}
      var p = video.play();
      if (p && p.catch) p.catch(function () {});
    }
    video.addEventListener('loadedmetadata', jump, { once: true });
    video.addEventListener('error', function () {
      msg.textContent = '视频直链加载失败（可能需校园网/登录）。可点右上角“回放页”打开智云回放，或稍后重试。';
      msg.style.display = '';
      box.style.display = 'none';
    }, { once: true });
    setTimeout(function () { if (!done && video.readyState >= 1) jump(); }, 1500);
  }
  function closeVideoNode() {
    var overlay = document.getElementById('cba-overlay');
    if (!overlay) return;
    overlay.classList.remove('open');
    var video = overlay.querySelector('video');
    if (video) { video.pause(); video.removeAttribute('src'); video.load(); }
  }
  function wireTimeJumpClicks(container) {
    container.querySelectorAll('.time-jump').forEach(function (a) {
      if (a.dataset.wired) return;
      a.dataset.wired = '1';
      a.addEventListener('click', function (e) {
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        var chapter = a.dataset.chapter || '';
        var sec = parseInt(a.dataset.sec || '0', 10) || 0;
        e.preventDefault();
        openVideoNode(chapter, sec, a.href);
      });
    });
  }

  /* ---------- video time-jump links ---------- */
  var _memVideo = {};
  function _store() { try { return window.localStorage; } catch (e) { return null; } }
  function videoMap() {
    var m = Object.assign({}, _memVideo);
    try { var st = _store(); var raw = st && st.getItem('cba-video-links'); if (raw) m = Object.assign(m, JSON.parse(raw) || {}); } catch (e) {}
    return m;
  }
  function saveVideoMap(m) {
    _memVideo = Object.assign({}, m);
    try { var st = _store(); if (st) st.setItem('cba-video-links', JSON.stringify(m)); } catch (e) {}
  }
  function timeToSeconds(t) {
    t = String(t || '').trim();
    var parts = t.split(':').map(function (x) { return parseInt(x, 10) || 0; });
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    if (parts.length === 2) return parts[0] * 60 + parts[1];
    return parts[0] || 0;
  }
  function chapterTitleOf(el, container) {
    var h1s = container.querySelectorAll('h1');
    var cur = null;
    h1s.forEach(function (h) { if (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) cur = h; });
    return cur ? cur.textContent.trim() : '';
  }
  function safeAttr(v) { return String(v).replace(/[<>"']/g, ''); }
  function linkTimeRanges(container) {
    if (!container) return;
    var map = videoMap();
    var preset = (typeof window.BOOK_VIDEO_LINKS === 'object' && window.BOOK_VIDEO_LINKS) ? window.BOOK_VIDEO_LINKS : {};
    container.querySelectorAll('p.time-links').forEach(function (p) {
      if (!p.dataset.raw) {
        var em0 = p.querySelector('em');
        p.dataset.raw = em0 ? em0.textContent : p.textContent;
      }
      var raw = p.dataset.raw.replace(/^字幕时间段\s*[:：]\s*/, '');
      var chapter = chapterTitleOf(p, container);
      var url = preset[chapter] || map[chapter] || '';
      var parts = raw.split('|').map(function (tok) {
        tok = tok.trim();
        if (!tok) return null;
        var sec = timeToSeconds(tok.split('-')[0]);
        if (url) {
          var u = url.indexOf('{ts}') >= 0 ? url.replace('{ts}', String(sec))
                 : url + (url.indexOf('?') >= 0 ? '&' : '?') + 'ts=' + sec;
          return '<a class="time-jump" target="_blank" rel="noopener" href="' + safeAttr(u) + '" data-chapter="' + safeAttr(chapter) + '" data-sec="' + sec + '" title="点击播放本讲视频 ' + tok + '（原视频节点）">' + tok + '</a>';
        }
        return '<span class="time-unlinked" title="点击为《' + safeAttr(chapter) + '》配置回放地址后即可跳转">' + tok + '</span>';
      }).filter(Boolean);
      p.innerHTML = '<span class="time-label">字幕时间段：</span>' + parts.join('<span class="time-sep"> | </span>');
    });
    wireTimeJumpClicks(container);
    container.querySelectorAll('.time-unlinked').forEach(function (span) {
      span.addEventListener('click', function () {
        var chapter = chapterTitleOf(span, container);
        var m = videoMap();
        var cur = preset[chapter] || m[chapter] || '';
        var msg = '为《' + chapter + '》设置本讲回放地址\n\n' +
          '方法：打开该讲回放页面，复制浏览器地址栏 URL（类似 https://classroom.zju.edu.cn/...?course_id=...&sub_id=...）。\n' +
          '保存后，本讲所有“字幕时间段”都会变成可跳转到对应时间的链接（保存在本机浏览器）。';
        var val = prompt(msg, cur);
        if (val === null) return;
        val = val.trim();
        if (val) m[chapter] = val; else delete m[chapter];
        saveVideoMap(m);
        linkTimeRanges(container);
      });
    });
  }

  function loadMarkdown(text, container, listEl) {
    if (!text || !text.trim()) { alert('没有可渲染的内容'); return; }
    if (!setupMarked()) return;
    var html = marked.parse(text);
    renderTo(html, container);
    decorate(container);
    enrichSections(container);
    linkTimeRanges(container);
    setBookMeta(container);
    fixInlineToc(container);
    if (listEl) { buildToc(container, listEl); scrollSpy(listEl); }
    if (window.__afterRender) window.__afterRender();
  }

  function wireFileOpen(container, listEl) {
    var input = document.getElementById('file-input');
    var btn = document.getElementById('btn-open');
    if (btn && input) {
      btn.addEventListener('click', function () { input.click(); });
      input.addEventListener('change', function () {
        var f = input.files && input.files[0];
        if (!f) return;
        var r = new FileReader();
        r.onload = function () { loadMarkdown(String(r.result), container, listEl); };
        r.readAsText(f, 'utf-8');
      });
    }
  }

  function wireDrop(container, listEl) {
    var zone = document.getElementById('drop-zone');
    if (!zone) return;
    function prevent(e) { e.preventDefault(); e.stopPropagation(); }
    window.addEventListener('dragover', prevent);
    window.addEventListener('drop', prevent);
    window.addEventListener('dragenter', function () { zone.classList.add('show'); });
    window.addEventListener('dragleave', function (e) { if (!zone.contains(e.relatedTarget)) zone.classList.remove('show'); });
    zone.addEventListener('drop', function (e) {
      zone.classList.remove('show');
      var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (!f) return;
      if (!/\.(md|markdown|txt)$/i.test(f.name)) { alert('请拖入 .md / .markdown / .txt 文件'); return; }
      var r = new FileReader();
      r.onload = function () { loadMarkdown(String(r.result), container, listEl); };
      r.readAsText(f, 'utf-8');
    });
  }


  /* Export current rendered book as a standalone static HTML file */
  function exportHtmlFile() {
    var content = document.getElementById('content');
    if (!content || !content.innerHTML.trim()) { alert('没有可导出的内容'); return; }
    var clone = document.documentElement.cloneNode(true);
    // drop interactive / chrome elements from the export copy
    clone.querySelectorAll('script, style[data-export-keep], .topbar, .sidebar, .drawer, .scrim, .bottomnav, #progress, #drop-zone, #file-input, .tools').forEach(function (n) { n.remove(); });
    // fix layout leftovers when chrome is gone
    var style = document.createElement('style');
    style.textContent = [
      'body{background:var(--bg,#fff)!important}',
      '.layout{display:block!important}',
      '.main{padding-top:0!important}',
      '.content-wrap{max-width:900px!important;margin:0 auto!important;padding:46px 34px 70px!important}',
      '.page{margin:0 auto!important;box-shadow:none!important}',
      '#content{line-height:2!important}',
      '#content > hr + h1{page-break-before:always}',
      '#content blockquote,ul.card-grid li.mini-card,ul.key-list li,ul.summary-list li{break-inside:avoid}'
    ].join('\n');
    clone.querySelector('head').appendChild(style);
    var title = document.title || 'coursebook';
    var safe = title.replace(/[\\/:*?"<>|\s]+/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '') || 'coursebook';
    var html = '<!doctype html>\n' + clone.outerHTML;
    var blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = safe + '.html';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 3000);
  }

  function wireControls() {
    var content = document.getElementById('content');
    // font size
    document.querySelectorAll('[data-font]').forEach(function (b) {
      b.addEventListener('click', function () {
        if (!content) return;
        var cur = parseFloat(getComputedStyle(content).fontSize) || 17;
        var next = b.dataset.font === 'up' ? Math.min(24, cur + 1) : Math.max(13, cur - 1);
        content.style.fontSize = next + 'px';
      });
    });
    // progress bar
    var bar = document.getElementById('progress');
    if (bar) {
      window.addEventListener('scroll', function () {
        var h = document.documentElement.scrollHeight - window.innerHeight;
        var p = h > 0 ? (window.scrollY / h) * 100 : 0;
        bar.style.width = p + '%';
      });
    }
    // back to top
    var topBtn = document.getElementById('btn-top');
    if (topBtn) topBtn.addEventListener('click', function () { window.scrollTo({ top: 0, behavior: 'smooth' }); });
    // export as html file
    var exp = document.getElementById('btn-export');
    if (exp) exp.addEventListener('click', exportHtmlFile);
    // print / save as pdf
    var prn = document.getElementById('btn-print');
    if (prn) prn.addEventListener('click', function () { window.print(); });
    // nav (previous/next chapter)
    document.querySelectorAll('[data-nav]').forEach(function (b) {
      b.addEventListener('click', function () {
        var h1s = Array.prototype.slice.call(document.querySelectorAll('#content > h1'));
        var i = currentChapterIndex;
        if (b.dataset.nav === 'next' && i < h1s.length - 1) i += 1;
        else if (b.dataset.nav === 'prev' && i > 0) i -= 1;
        else return;
        currentChapterIndex = i;
        h1s[i].scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
    if (window.__onScroll && document.getElementById('content')) {
      window.addEventListener('scroll', function () {
        var h1s = Array.prototype.slice.call(document.querySelectorAll('#content > h1'));
        var pos = window.scrollY + window.innerHeight * 0.3;
        currentChapterIndex = -1;
        for (var i = 0; i < h1s.length; i++) { if (h1s[i].offsetTop <= pos) currentChapterIndex = i; }
        if (typeof window.__onScroll === 'function') window.__onScroll(currentChapterIndex);
      });
    }
  }

  function init(cfg) {
    if (!cfg) cfg = {};
    ensurePlayerStyles();
    var container = document.getElementById(cfg.contentId || 'content');
    var listEl = cfg.toc ? document.getElementById(cfg.tocId || 'toc-list') : null;
    if (!container) return;
    wireControls();
    wireFileOpen(container, listEl);
    wireDrop(container, listEl);
    loadMarkdown(sampleText(), container, listEl);
    // menu toggles delegated per design
    document.body.addEventListener('click', function (e) {
      var t = e.target.closest ? e.target.closest('[data-action]') : null;
      if (!t) return;
      var act = t.dataset.action;
      var body = document.body;
      if (act === 'toggle-sidebar') body.classList.toggle('sidebar-open');
      if (act === 'toggle-reader-menu') body.classList.toggle('reader-menu-open');
      if (act === 'set-theme') {
        body.dataset.theme = t.dataset.theme || 'light';
        document.querySelectorAll('[data-theme]').forEach(function (b) {
          b.classList.toggle('on', b === t);
        });
      }
    });
    document.addEventListener('keydown', function (e) {
      if (e.target && /input|textarea|select/i.test(e.target.tagName)) return;
      if (e.key === 'Escape') { body.classList.remove('sidebar-open', 'reader-menu-open'); closeVideoNode(); }
    });
    if (cfg.afterRender) window.__afterRender = cfg.afterRender;
    if (cfg.onScroll) window.__onScroll = cfg.onScroll;
  }

  window.initBookViewer = init;
  window.renderSampleAgain = function () {
    var container = document.getElementById('content');
    var listEl = document.querySelector('#toc-list');
    loadMarkdown(sampleText(), container, listEl);
  };
})();
