// 縣市設定：/api/public/site-config.js 先載入 window.SITE（承辦機關、聯絡資訊等），
// 這裡把頁面上標記 data-site 的文字換成該縣市的內容；HTML 內原本的文字是基隆市的備援值。
//   data-site="agency"                    → 元素文字
//   data-site-attr="placeholder:address_example" → 屬性（多個以 ; 分隔）
//   data-site-tel                          → href="tel:…"
(function () {
  const DEFAULT_SITE_NAME = '基隆市防災士培訓報名系統';
  const s = window.SITE || null;

  // 頁面腳本組字串時使用，例：site('agency', '基隆市政府消防局')
  window.site = (key, fallback) => (s && s[key]) || fallback || '';
  window.siteName = () => window.site('site_name', DEFAULT_SITE_NAME);

  if (!s) return;
  document.title = document.title.replace(DEFAULT_SITE_NAME, s.site_name);

  function fill() {
    document.querySelectorAll('[data-site]').forEach((el) => {
      const v = s[el.dataset.site];
      if (v) el.textContent = v;
    });
    document.querySelectorAll('[data-site-attr]').forEach((el) => {
      el.dataset.siteAttr.split(';').forEach((pair) => {
        const [attr, key] = pair.split(':').map((x) => x.trim());
        if (attr && s[key]) el.setAttribute(attr, s[key]);
      });
    });
    document.querySelectorAll('[data-site-tel]').forEach((el) => {
      if (s.tel_uri) el.setAttribute('href', `tel:${s.tel_uri}`);
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fill);
  else fill();
})();
