#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D043 patch: persona cards 重排 + 風格標籤 + wizard 3 步
- Reorder 16 persona cards: 新手精靈 first, then by direction group
- Add [短][波][長] style tag to each card
- Fix typo: AQR 偵優勢 -> 雙優勢
- WIZARD_STEPS_BASE 3 steps: 方向 → 時段 → 3 張推薦
- Remove range+sub3a, sort step
- buildPendingFromWizard → getRecommendedPersonas(direction, style)
"""
import re
import sys

PATH = r'C:\Users\icemo\Projects\tw-invest-suite\public\chips.html'
with open(PATH, 'r', encoding='utf-8') as f:
    content = f.read()
orig = content

# ============================================================
# Style tag map (style short → 短 / wave → 波 / long → 長)
# ============================================================
STYLE_TAGS = {
    'streak3':     ['short', 'wave', 'long'],
    'same_buy':    ['short', 'wave', 'long'],
    'f_5d_1y':     ['short', 'wave'],
    'force_high':  ['short'],
    'f_stay_long': ['wave', 'long'],
    'same_sell':   ['wave', 'long'],
    'value':       ['long'],
    'weak':        ['wave', 'long'],
    'ws_aqr':      ['wave', 'long'],
    'ws_jt':       ['short', 'wave'],
    'ws_mr':       ['short'],
    'ws_qm':       ['wave', 'long'],
    'ws_moat':     ['long'],
    'ws_news':     ['short', 'wave'],
    'ws_eps':      ['wave', 'long'],
}

TAG_LABEL = {'short': '短', 'wave': '波', 'long': '長'}

# ============================================================
# Build new persona cards HTML (按方向分組，新手精靈第一)
# Order:
#   Row 1: 新手精靈 + 9 偏多 (streak3, same_buy, f_5d_1y, force_high, f_stay_long, value, ws_aqr, ws_jt, ws_qm)
#   Row 2: 2 偏空 (same_sell, weak) + 1 反轉 (ws_mr) + 3 中性 (ws_moat, ws_news, ws_eps)
# ============================================================
PERSONA_DATA = {
    'newbie':     ('🆕', '新手精靈', '2 步問券'),
    'streak3':    ('⚔️', '法人連買', '連買 3 天+'),
    'same_buy':   ('🔥', '土洋同買', '3 法人齊買'),
    'f_5d_1y':    ('💵', '外資大買', '5 日 ≥ 1 億'),
    'force_high': ('⚡', '量能爆發', '力道 ≥ 1.5×'),
    'f_stay_long':('🚀', '外資停留', '停留 5 天+'),
    'value':      ('💎', '金融存股', '金融/食品 + 連買'),
    'ws_aqr':     ('📈', 'AQR 雙優勢', '低估值 + 動能'),
    'ws_jt':      ('📈', 'JT 動能王', '3-12 月動能'),
    'ws_qm':      ('🏛', '法人鎖碼', '重量級 + 融資穩'),
    'same_sell':  ('📉', '空方避雷', '同賣 + 連賣'),
    'weak':       ('💧', '弱勢退場', '力道 ≤ -1.0×'),
    'ws_mr':      ('🔄', '跌深反彈', '5 日賣 + 20 日買'),
    'ws_moat':    ('🏰', '護城河之王', '寬護城河 ≥ 0.75'),
    'ws_news':    ('📰', '新聞利多', '新聞情緒 ≥ 0'),
    'ws_eps':     ('📈', 'EPS 成長', 'EPS YoY ≥ 0'),
}

# Order: row1 (新手 + 偏多), row2 (偏空 + 反轉 + 中性)
ORDER = [
    'newbie',
    'streak3', 'same_buy', 'f_5d_1y', 'force_high', 'f_stay_long', 'value', 'ws_aqr', 'ws_jt', 'ws_qm',
    'same_sell', 'weak', 'ws_mr', 'ws_moat', 'ws_news', 'ws_eps',
]

def make_card(key):
    icon, name, desc = PERSONA_DATA[key]
    tags = STYLE_TAGS.get(key, [])
    tag_html = ''.join(
        f'<span class="tag-{t}">{TAG_LABEL[t]}</span>' for t in tags
    )
    tag_block = f'<div class="tags">{tag_html}</div>' if tag_html else ''
    return f'''    <button class="persona-card" data-persona="{key}">
      <div class="icon">{icon}</div>
      <div class="name">{name}</div>
      <div class="desc">{desc}</div>
      {tag_block}
    </button>'''

# Build all 16 cards
new_cards_html = '\n'.join(make_card(k) for k in ORDER)

# ============================================================
# Replace the entire persona card section (streak3..ws_eps in main row + ws_eps closing)
# Old structure: persona-row > persona-row-inner (with 9 cards) + persona-row-ws (with 4 + 3 cards)
# New: persona-row > persona-row-inner (with all 16 cards in one grid)
# ============================================================
# Find from `<div class="persona-row">` opening before streak3 to the close right before wizard/summary-bar
old_section_pattern = re.compile(
    r'<div class="persona-row">.*?</div>\s*</div>\s*</div>',
    re.DOTALL,
)
m = old_section_pattern.search(content)
if not m:
    print('*** section not found ***')
    sys.exit(1)
print(f'old section: {m.end() - m.start()} chars, lines {content[:m.start()].count(chr(10))+1}..{content[:m.end()].count(chr(10))+1}')

new_section = f'''<div class="persona-row">
  <div class="persona-row-inner">
{new_cards_html}
  </div>
</div>'''
content = content[:m.start()] + new_section + content[m.end():]
print(f'new section: {len(new_section)} chars')

# ============================================================
# Add CSS for tag-short/wave/long
# ============================================================
old_css_anchor = '.persona-card.active {'
if old_css_anchor in content:
    new_css = '''.persona-card .tags { display:flex; gap:3px; margin-top:5px; flex-wrap:wrap; justify-content:center; }
.persona-card .tag-short, .persona-card .tag-wave, .persona-card .tag-long {
  display:inline-block; padding:1px 5px; border-radius:4px; font-size:0.62rem; font-weight:600;
  line-height:1.3;
}
.persona-card .tag-short { background:rgba(236,112,99,0.18); color:#ec7063; border:1px solid rgba(236,112,99,0.35); }
.persona-card .tag-wave  { background:rgba(243,156,18,0.18); color:#f39c12; border:1px solid rgba(243,156,18,0.35); }
.persona-card .tag-long  { background:rgba(52,152,219,0.18); color:#3498db; border:1px solid rgba(52,152,219,0.35); }

.persona-card.active {'''
    content = content.replace(old_css_anchor, new_css, 1)
    print('CSS tags added')

# ============================================================
# Replace WIZARD_STEPS_BASE (4 步) with 3 步 (方向 → 時段 → 3 張推薦)
# ============================================================
old_wizard_steps = '''var WIZARD_STEPS_BASE = [
  {
    id: 'persona',
    title: '👉 第一步：選 persona 策略',
    sub: '點選下方 11 個 persona 策略，看哪個適合你',
    type: 'single',
    options: [
      { label: '⚔️ 法人連買', val: 'streak3' },
      { label: '🔥 土洋同買', val: 'same_buy' },
      { label: '💵 外資大買', val: 'f_5d_1y' },
      { label: '⚡ 量能爆發', val: 'force_high' },
      { label: '🚀 外資停留', val: 'f_stay_long' },
      { label: '📉 空方避雷', val: 'same_sell' },
      { label: '💎 金融存股', val: 'value' },
      { label: '💧 弱勢退場', val: 'weak' },
      { label: '🏰 護城河之王', val: 'ws_moat' },
      { label: '📰 新聞利多', val: 'ws_news' },
      { label: '📈 EPS 成長', val: 'ws_eps' }
    ]
  },
  {
    id: 'direction',
    title: '想找哪個方向？',
    sub: '可複選（點多又偏空）',
    type: 'multi',
    options: [
      { label: '🔴 偏多 (buy)', val: 'long' },
      { label: '🔵 偏空 (sell)', val: 'short' },
      { label: '⚪ 全部', val: 'all' }
    ]
  },
  {
    id: 'range',
    title: '📍 第三步：看哪個範圍？',
    sub: '全市場 / 概念股 / 鎖定特定產業',
    type: 'single',
    rangeFollowup: true,
    options: [
      { label: '🌐 全市場 (1,962 檔)', val: 'all' },
      { label: '🔥 概念股', val: 'concept' },
      { label: '🏭 特定產業', val: 'industry' }
    ]
  },
  {
    id: 'sort',
    title: '📊 最後：按哪種排序？',
    sub: '點擊 persona 可用 persona sort，或自己選',
    type: 'single',
    options: [
      { label: '預設 persona sort', val: 'persona' },
      { label: '股價 ↓', val: 'price_desc' },
      { label: '股價 ↑', val: 'price_asc' },
      { label: '3 法人合計 (張) ↓', val: 'three_5d_shares' },
      { label: '3 法人金額 ↓', val: 'three_5d_twd' },
      { label: '力道 ↓', val: 'force' },
      { label: '連買天數 ↓', val: 'streak' },
      { label: '停留天數 ↓', val: 'stay' },
      { label: '護城河 ↓', val: 'moat_desc' },
      { label: 'EPS YoY ↓', val: 'eps_yoy_desc' },
      { label: '新聞情緒 ↓', val: 'news_desc' }
    ]
  }
];'''

new_wizard_steps = '''// D043: 3 步 wizard — 方向 → 時段 → 3 張推薦 persona
var WIZARD_STEPS_BASE = [
  {
    id: 'direction',
    title: '🎯 第一步：先選方向',
    sub: '看多 / 看空 / 全部',
    type: 'single',
    field: 'direction',
    options: [
      { label: '🔴 看多', val: 'long' },
      { label: '🟢 看空', val: 'short' },
      { label: '⚪ 全部', val: 'all' }
    ]
  },
  {
    id: 'style',
    title: '⏱️ 第二步：看哪個時段？',
    sub: '短線 / 波段 / 長期',
    type: 'single',
    field: 'style',
    options: [
      { label: '⚡ 短線', val: 'short' },
      { label: '📊 波段', val: 'wave' },
      { label: '🏦 長期', val: 'long' }
    ]
  },
  {
    id: 'recommend',
    title: '✨ 第三步：挑一張卡套用',
    sub: '依你選的方向 + 時段，推薦 3 張 persona',
    type: 'recommend',
    field: 'recommend'
  }
];'''

if old_wizard_steps in content:
    content = content.replace(old_wizard_steps, new_wizard_steps)
    print('WIZARD_STEPS_BASE: 4 步 → 3 步 (方向→時段→推薦)')
else:
    print('*** WIZARD_STEPS_BASE not found ***')

# ============================================================
# Replace buildPendingFromWizard with 3-step recommendation
# ============================================================
old_build = '''function buildPendingFromWizard() {
  var pending = { mode: 'AND', concepts: [], presets: [], industry: '', numerics: [] };
  // Step 0: persona (e.g. streak3 / same_buy / ws_aqr / ws_moat / ws_news / ws_eps)
  var persona = WIZARD.answers[0];
  // Step 1: direction (multi: long / short / all)
  var dir = WIZARD.answers[1] || [];
  // Map persona -> { presets, numerics } (D037b / D038 rules)
  var pMap = {
    streak3:    { presets: ['streak3'], numerics: [] },
    same_buy:   { presets: ['streak3','same_buy'], numerics: [] },
    f_5d_1y:    { presets: ['f_5d_1y'], numerics: [] },
    force_high: { presets: ['force_high'], numerics: [] },
    f_stay_long:{ presets: ['f_stay_long'], numerics: [] },
    same_sell:  { presets: ['streak3_sell','same_sell'], numerics: [] },
    value:      { presets: ['streak3'], numerics: [], industry: '金融保險' },
    weak:       { presets: ['force_low'], numerics: [] },
    ws_aqr:     { presets: [], numerics: [
        {field:'force_ratio', op:'>=', value:1.2},
        {field:'cost_gap_pct', op:'<=', value:0}
    ]},
    ws_jt:      { presets: [], numerics: [
        {field:'force_ratio', op:'>=', value:1.0},
        {field:'f_5d_twd', op:'>', value:0}
    ]},
    ws_mr:      { presets: [], numerics: [
        {field:'f_5d_shares', op:'<=', value:0},
        {field:'f_20d_shares', op:'>', value:0}
    ]},
    ws_qm:      { presets: [], numerics: [
        {field:'f_streak', op:'>=', value:5},
        {field:'margin_change', op:'>=', value:0},
        {field:'f_5d_twd', op:'>=', value:1}
    ]},
    ws_moat:    { presets: [], numerics: [{field:'moat_score', op:'>=', value:0.75}] },
    ws_news:    { presets: [], numerics: [{field:'news_score', op:'>', value:0}] },
    ws_eps:     { presets: [], numerics: [{field:'eps_yoy_pct', op:'>=', value:0}] }
  };
  var def = pMap[persona];
  if (def) {
    if (def.presets) def.presets.forEach(function(p){ pending.presets.push(p); });
    if (def.numerics) def.numerics.forEach(function(n){ pending.numerics.push(n); });
    if (def.industry) pending.industry = def.industry;
  }
  // Step 1 direction override: long-only / short-only / all
  if (Array.isArray(dir) && dir.indexOf('all') < 0) {
    if (dir.indexOf('long') >= 0 && dir.indexOf('short') < 0) {
      // 加一個 long-bias 預設 (3 法人合計 > 0)，但不要蓋掉 persona 的設定
      pending.presets.push('same_buy');
    } else if (dir.indexOf('short') >= 0 && dir.indexOf('long') < 0) {
      pending.presets.push('same_sell');
    }
  }
  // Step 2: 範圍 (all / concept / industry)
  var range = WIZARD.answers[2];
  // Step 3: sub3a (concept list / industry name)
  var sub = WIZARD.answers[3];
  if (range === 'concept' && Array.isArray(sub) && sub.length > 0) {
    pending.concepts = sub;
  } else if (range === 'industry' && sub) {
    pending.industry = sub;
  }
  // 去重 presets
  var seen = {};
  pending.presets = pending.presets.filter(function(p){ if (seen[p]) return false; seen[p] = true; return true; });
  return pending;
}'''

new_build = '''// D043: 依 direction + style 推薦 3 張 persona（基於 STYLE_TAGS 標籤）
function getRecommendedPersonas(direction, style) {
  // 候選順序：偏多 8 張 → 偏空/反轉/中性
  var allPersonas = {
    streak3:    'long',  same_buy:   'long',  f_5d_1y:    'long',  force_high: 'long',
    f_stay_long:'long',  value:      'long',  ws_aqr:     'long',  ws_jt:      'long',
    ws_qm:      'long',
    same_sell:  'short', weak:       'short',
    ws_mr:      'reverse',
    ws_moat:    'neutral', ws_news:  'neutral', ws_eps:    'neutral'
  };
  // 風格標籤 map (跟 STYLE_TAGS 一致)
  var tagsMap = {
    streak3: ['short','wave','long'], same_buy: ['short','wave','long'],
    f_5d_1y: ['short','wave'], force_high: ['short'],
    f_stay_long: ['wave','long'], same_sell: ['wave','long'],
    value: ['long'], weak: ['wave','long'],
    ws_aqr: ['wave','long'], ws_jt: ['short','wave'],
    ws_mr: ['short'], ws_qm: ['wave','long'],
    ws_moat: ['long'], ws_news: ['short','wave'],
    ws_eps: ['wave','long']
  };
  // 過濾
  var candidates = [];
  for (var key in allPersonas) {
    var dir = allPersonas[key];
    var tags = tagsMap[key] || [];
    // 方向過濾
    if (direction === 'long' && dir !== 'long') continue;
    if (direction === 'short' && dir !== 'short' && dir !== 'reverse') continue;
    // 時段過濾
    if (style && tags.indexOf(style) < 0) continue;
    candidates.push(key);
  }
  // 取前 3 張
  return candidates.slice(0, 3);
}

// 從 persona 套用既有的 applyPersonaDirect 邏輯
// D043 簡化：wizard 推薦 → user 點 → 直接套用 persona
// 不再需要 buildPendingFromWizard（wizard 是 discovery UI，套用是 persona-card 1-click）'''

if old_build in content:
    content = content.replace(old_build, new_build)
    print('buildPendingFromWizard → getRecommendedPersonas + wizard 只負責推薦')
else:
    print('*** buildPendingFromWizard not found ***')

# ============================================================
# Fix renderWizardStep: handle 'recommend' type (3 張 persona cards)
# ============================================================
# Find the section that handles options rendering and add recommend support
old_render_options = '''  step.options.forEach(function(o){
    var btn = document.createElement('button');
    btn.className = 'wizard-opt';
    if (prev !== null) {
      if (step.type === 'multi' && Array.isArray(prev) && prev.indexOf(o.val) >= 0) btn.classList.add('on');
      if (step.type === 'single' && prev === o.val) btn.classList.add('on');
    }
    btn.textContent = o.label;
    btn.addEventListener('click', function(){
      if (step.type === 'multi') {
        btn.classList.toggle('on');
      } else {
        opts.querySelectorAll('.wizard-opt').forEach(function(x){ x.classList.remove('on'); });
        btn.classList.add('on');
      }
      collectWizardAnswer();
    });
    opts.appendChild(btn);
  });'''

new_render_options = '''  if (step.type === 'recommend') {
    // D043: 顯示 3 張推薦 persona cards
    var direction = WIZARD.answers[0] || 'all';
    var style = WIZARD.answers[1] || '';
    var recs = (typeof getRecommendedPersonas === 'function') ? getRecommendedPersonas(direction, style) : [];
    recs.forEach(function(key){
      var def = (typeof PERSONAS !== 'undefined' && PERSONAS[key]) ? PERSONAS[key] : null;
      var btn = document.createElement('button');
      btn.className = 'wizard-recommend-card persona-card';
      btn.setAttribute('data-persona', key);
      var tagHtml = '';
      if (def && def.tags) tagHtml = '<div class="tags">' + def.tags.map(function(t){
        return '<span class="tag-' + t + '">' + (t==='short'?'短':t==='wave'?'波':'長') + '</span>';
      }).join('') + '</div>';
      btn.innerHTML = '<div class="icon">' + (def?def.icon:'📊') + '</div>'
        + '<div class="name">' + (def?def.name:key) + '</div>'
        + '<div class="desc">' + (def?def.desc:'') + '</div>'
        + tagHtml;
      btn.addEventListener('click', function(){
        // 套用 persona + 關 wizard
        if (typeof applyPersonaDirect === 'function') {
          try { localStorage.setItem('tank-akali-active-persona-v1', key); } catch(e){}
          ACTIVE_PERSONA = key;
          document.querySelectorAll('.persona-card').forEach(function(c){
            c.classList.toggle('active', c.getAttribute('data-persona') === key);
          });
          applyPersonaDirect(key);
        }
        document.getElementById('wizard').hidden = true;
        // 顯示意圖
        var dirLabel = {long:'看多', short:'看空', all:'全部'}[direction] || direction;
        var styleLabel = {short:'短線', wave:'波段', long:'長期'}[style] || style;
        var personaName = def ? def.name : key;
        var intention = '🎯 ' + personaName + '（' + dirLabel + ' ‧ ' + styleLabel + '）';
        document.getElementById('sum-intention').textContent = intention;
      });
      opts.appendChild(btn);
    });
    if (recs.length === 0) {
      var noMatch = document.createElement('div');
      noMatch.style.cssText = 'padding:20px;text-align:center;color:var(--muted);';
      noMatch.textContent = '沒有符合條件的 persona，試試其他方向或時段';
      opts.appendChild(noMatch);
    }
  } else {
    step.options.forEach(function(o){
      var btn = document.createElement('button');
      btn.className = 'wizard-opt';
      if (prev !== null) {
        if (step.type === 'multi' && Array.isArray(prev) && prev.indexOf(o.val) >= 0) btn.classList.add('on');
        if (step.type === 'single' && prev === o.val) btn.classList.add('on');
      }
      btn.textContent = o.label;
      btn.addEventListener('click', function(){
        if (step.type === 'multi') {
          btn.classList.toggle('on');
        } else {
          opts.querySelectorAll('.wizard-opt').forEach(function(x){ x.classList.remove('on'); });
          btn.classList.add('on');
        }
        collectWizardAnswer();
      });
      opts.appendChild(btn);
    });
  }'''

if old_render_options in content:
    content = content.replace(old_render_options, new_render_options)
    print('renderWizardStep: recommend type added')
else:
    print('*** renderWizardOptions not found ***')

# ============================================================
# Fix showWizard: WIZARD.answers 3 slots now
# ============================================================
old_show = '''  WIZARD = { step: 0, answers: [null, ['long'], 'all', null], history: [] };'''
new_show = '''  WIZARD = { step: 0, answers: [null, null, null], history: [] };'''
if old_show in content:
    content = content.replace(old_show, new_show)
    print('showWizard reset: 4 slots → 3 slots')

# ============================================================
# Fix WIZARD init declaration
# ============================================================
old_init = 'var WIZARD = { step: 0, answers: [null, null, null, null], history: [] };'
new_init = 'var WIZARD = { step: 0, answers: [null, null, null], history: [] };'
if old_init in content:
    content = content.replace(old_init, new_init)
    print('WIZARD init: 4 slots → 3 slots')

# ============================================================
# Fix wiz-go handler: no more range/sub3a validation
# ============================================================
old_go_validation = '''  if (WIZARD.answers[2] === 'concept' && (!WIZARD.answers[3] || WIZARD.answers[3].length === 0)) {
    alert('請至少選一個概念');
    return;
  }
  if (WIZARD.answers[2] === 'industry' && !WIZARD.answers[3]) {
    alert('請選一個產業');
    return;
  }'''
new_go_validation = '''  // D043: wizard 3 步 → user 必須選完方向 + 時段
  if (!WIZARD.answers[0]) { alert('請先選方向'); return; }
  if (!WIZARD.answers[1]) { alert('請選時段'); return; }
  // Step 3 為 recommend 卡片，user 點任一張就會自己觸發，wiz-go 不做事'''
if old_go_validation in content:
    content = content.replace(old_go_validation, new_go_validation)
    print('wiz-go validation simplified')

# ============================================================
# Fix wiz-go handler: remove buildPendingFromWizard call
# ============================================================
old_go_block = '''  PENDING = buildPendingFromWizard();
  commitFilter();
  document.getElementById('wizard').hidden = true;
  renderSummary('newbie', PERSONAS.newbie);
  // D041: 套用當前 sort dropdown 值
  var sortSel = document.getElementById('sort-sel');
  if (sortSel && sortSel.value !== 'default') {
    CURRENT_SORT = sortSel.value;
    applySort();
  }'''
new_go_block = '''  // D043: wizard 3 步 — Step 3 (recommend) 點 persona card 時已自動套用 + 關 wizard
  // wiz-go 純粹是「沒選就返回」或「回到 wizard」用
  document.getElementById('wizard').hidden = true;'''
if old_go_block in content:
    content = content.replace(old_go_block, new_go_block)
    print('wiz-go block: buildPendingFromWizard removed (recommend 已直接套用)')

# ============================================================
# Fix wizard intention string (D042-based code, now simplified)
# ============================================================
old_intention = '''  // D042: 4-step intention string (persona + direction + range)
  var persona = WIZARD.answers[0] || '';
  var dir = (WIZARD.answers[1] || []).filter(function(d){return d!=='all';});
  var range = WIZARD.answers[2] || 'all';
  var sub = WIZARD.answers[3] || '';
  var PERSONA_NAMES = {streak3:'法人連買', same_buy:'土洋同買', f_5d_1y:'外資大買', force_high:'量能爆發', f_stay_long:'外資停留', same_sell:'空方避雷', value:'金融存股', weak:'弱勢退場', ws_aqr:'AQR 雙優勢', ws_jt:'JT 動能', ws_mr:'跌深反彈', ws_qm:'法人鎖碼', ws_moat:'護城河之王', ws_news:'新聞利多', ws_eps:'EPS 成長'};
  var DIR_NAMES = {long:'偏多', short:'偏空'};
  var intention = '🎯 ' + (PERSONA_NAMES[persona] || persona) + (dir.length?'（'+dir.map(function(d){return DIR_NAMES[d];}).join('+')+'）':'') + ' ‧ ' + (range==='concept'?'概念: '+(Array.isArray(sub)?sub.join('/'):sub):range==='industry'?'產業: '+sub:'全市場');
  document.getElementById('sum-intention').textContent = intention;
  document.getElementById('wizard-actions').hidden = false;'''
# We removed most of this in new_go_block, so this part may not be in content anymore
# Just to be safe, do a no-op if not found
if old_intention in content:
    content = content.replace(old_intention, '  // (D043: intention now set in recommend-card click handler)')
    print('wizard intention string: simplified to no-op')

# ============================================================
# Fix previewWizard (it used buildPendingFromWizard)
# ============================================================
old_preview = '''function previewWizard() {
  // 用目前答案即時命中 preview
  var fakePending = buildPendingFromWizard();
  var conds = collectMatchers(fakePending);
  var n = 0;
  if (conds.length === 0) n = Object.keys(TICKER_DATA).length || 1921;
  else {
    Object.keys(TICKER_DATA).forEach(function(t){
      var p = TICKER_DATA[t];
      if (p && conds.every(function(c){ return c(p); })) n++;
    });
  }
  document.querySelector('#wizard .wizard-hint b').textContent = n;
}'''
new_preview = '''function previewWizard() {
  // D043: 3 步 wizard — Step 1/2 用 persona 標籤 hint，Step 3 顯示 3 張卡
  var step = getWizardSteps()[WIZARD.step];
  var hint = document.querySelector('#wizard .wizard-hint b');
  if (step.id === 'recommend') {
    var direction = WIZARD.answers[0] || 'all';
    var style = WIZARD.answers[1] || '';
    var recs = (typeof getRecommendedPersonas === 'function') ? getRecommendedPersonas(direction, style) : [];
    hint.textContent = recs.length + ' 張推薦';
  } else {
    // Step 1/2 顯示全部 stock 數
    hint.textContent = Object.keys(TICKER_DATA).length || 1921;
  }
}'''
if old_preview in content:
    content = content.replace(old_preview, new_preview)
    print('previewWizard: simplified (no longer calls buildPendingFromWizard)')

# ============================================================
# Fix wiz-cancel: was OK but let's verify
# ============================================================

# ============================================================
# Fix wiz-next behavior: allow skipping Step 1/2 to Step 3
# ============================================================
old_next = '''document.getElementById('wiz-next').addEventListener('click', function(){
  // 允許跳過（沒選也讓 next，最後 Go 時再驗證範圍）
  if (WIZARD.step < getWizardSteps().length - 1) { WIZARD.step++; renderWizardStep(); }
});'''
new_next = '''document.getElementById('wiz-next').addEventListener('click', function(){
  // D043: 必須選完方向 + 時段才能到 Step 3
  var step = getWizardSteps()[WIZARD.step];
  if (step.id === 'direction' && !WIZARD.answers[0]) { alert('請先選方向'); return; }
  if (step.id === 'style' && !WIZARD.answers[1]) { alert('請選時段'); return; }
  if (WIZARD.step < getWizardSteps().length - 1) { WIZARD.step++; renderWizardStep(); }
});'''
if old_next in content:
    content = content.replace(old_next, new_next)
    print('wiz-next: require answers before moving forward')

# ============================================================
# Update showWizard to also auto-apply "newbie" persona active highlight
# ============================================================

# ============================================================
# Save
# ============================================================
if content == orig:
    print('\n*** NO CHANGES ***')
    sys.exit(1)
with open(PATH, 'w', encoding='utf-8') as f:
    f.write(content)
print(f'\nSaved: {len(content) - len(orig):+d} chars, new size = {len(content)}')
