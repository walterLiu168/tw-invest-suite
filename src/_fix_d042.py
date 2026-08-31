#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D042 fix: 4-step wizard (persona, direction, range+sub3a, sort).
- remove WIZARD_BRANCH_STEPS block (短/波/長 6/7/7 options)
- remove WIZARD_RANGE_STEP duplicate
- getWizardSteps returns WIZARD_STEPS_BASE directly
- buildPendingFromWizard maps answers[0]=persona, [1]=direction, [2]=range, [3]=sub3a
- fix 7 typos
- clean dead zone (L9079-9113)
- remove duplicate sum-reshuffle / sum-save / sum-edit handlers
"""
import re
import sys

PATH = r'C:\Users\icemo\Projects\tw-invest-suite\public\chips.html'

with open(PATH, 'r', encoding='utf-8') as f:
    content = f.read()

orig = content

# ============================================================
# Fix 1: 7 typos
# ============================================================
typo_map = [
    ('點擇下方 11 個 persona，目标分數分',
     '點選下方 11 個 persona 策略，看哪個適合你'),
    ("{ label: '📉 空方避電', val: 'same_sell' }",
     "{ label: '📉 空方避雷', val: 'same_sell' }"),
    ('全市場 / 概念股 / 對憑特定產業',
     '全市場 / 概念股 / 鎖定特定產業'),
    ("{ label: '🏺 特定產業', val: 'industry' }",
     "{ label: '🏭 特定產業', val: 'industry' }"),
    ("{ label: '3 法人公司 ↓', val: 'three_5d_shares' }",
     "{ label: '3 法人合計 (張) ↓', val: 'three_5d_shares' }"),
    ("{ label: '新聞情緓 ↓', val: 'news_desc' }",
     "{ label: '新聞情緒 ↓', val: 'news_desc' }"),
    ("新聞情緓", "新聞情緒"),  # summary bar label (剩 4 個)
]
for old, new in typo_map:
    cnt = content.count(old)
    if cnt:
        content = content.replace(old, new)
        print(f'[typo] {old!r} -> {new!r}  ({cnt})')
    else:
        print(f'[typo-NOT-FOUND] {old!r}')

# ============================================================
# Fix 2: remove WIZARD_BRANCH_STEPS block (L8604-8649)
# ============================================================
# Mark from `// WIZARD_BRANCH_STEPS = {` until matching `};\n` after the long block.
# We'll use a regex anchored by the start comment and end pattern.
branch_pattern = re.compile(
    r'// WIZARD_BRANCH_STEPS = \{.*?\n\};\n',
    re.DOTALL,
)
m = branch_pattern.search(content)
if m:
    content = content[:m.start()] + '// (WIZARD_BRANCH_STEPS removed in D042 — wizard is 4-step)\n' + content[m.end():]
    print(f'[branch] removed {m.end() - m.start()} chars')
else:
    print('[branch-NOT-FOUND]')

# ============================================================
# Fix 3: replace WIZARD_RANGE_STEP block (now duplicate of WIZARD_STEPS_BASE[2])
# ============================================================
range_pattern = re.compile(
    r'// 範圍步（最後一步）\nWIZARD_RANGE_STEP = \{.*?\n\};\n',
    re.DOTALL,
)
m = range_pattern.search(content)
if m:
    content = content[:m.start()] + '// (WIZARD_RANGE_STEP removed in D042 — range is in WIZARD_STEPS_BASE[2])\n' + content[m.end():]
    print(f'[range] removed {m.end() - m.start()} chars')
else:
    print('[range-NOT-FOUND]')

# ============================================================
# Fix 4: simplify getWizardSteps
# ============================================================
old_getwiz = '''// 取得完整步驟陣列（依 Q1 動態）
function getWizardSteps() {
  var style = WIZARD.answers[0] || 'short';
  var branch = WIZARD_BRANCH_STEPS[style] || WIZARD_BRANCH_STEPS.short;
  return WIZARD_STEPS_BASE.concat([branch, WIZARD_RANGE_STEP]);
}'''
new_getwiz = '''// D042: 取得 4 步驟（persona → direction → range → sort）
function getWizardSteps() {
  return WIZARD_STEPS_BASE;
}'''
if old_getwiz in content:
    content = content.replace(old_getwiz, new_getwiz)
    print('[getWizardSteps] simplified')
else:
    print('[getWizardSteps-NOT-FOUND]')

# ============================================================
# Fix 5: rewrite buildPendingFromWizard
# answers[0] = persona key (streak3 / ws_aqr / ws_moat / ...)
# answers[1] = direction (multi: [long] / [short] / [long,short])
# answers[2] = range (all/concept/industry)
# answers[3] = sub3a (concepts[] OR industry string)
# Persona numerics come from PERSONA_PRESETS / applyPersonaDirect rules.
# ============================================================
old_build = '''function buildPendingFromWizard() {
  var pending = { mode: 'AND', concepts: [], presets: [], industry: '', numerics: [] };
  // Step 0: 風格 - 影響進階篩選
  var style = WIZARD.answers[0] || 'short';
  // Step 1: 方向 (multi)
  var s1 = WIZARD.answers[1] || [];
  if (Array.isArray(s1) && s1.length > 0 && s1.indexOf('all') < 0) {
    if (s1.indexOf('long') >= 0 && s1.indexOf('short') < 0) pending.presets.push('streak3', 'same_buy');
    else if (s1.indexOf('short') >= 0 && s1.indexOf('long') < 0) pending.presets.push('streak3_sell', 'same_sell');
  }
  // Step 2: 分支題 (依 Q1 風格)
  var s2 = WIZARD.answers[2];
  if (style === 'short') {
    if (s2 === 'gentle') pending.numerics.push({field:'force_ratio', op:'>=', value:1.0});
    else if (s2 === 'medium') pending.numerics.push({field:'force_ratio', op:'>=', value:1.5});
    else if (s2 === 'strong') pending.numerics.push({field:'force_ratio', op:'>=', value:2.5});
    else if (s2 === 'multi') { pending.presets.push('streak3', 'same_buy'); }
    else if (s2 === 'vol5y') pending.numerics.push({field:'three_5d_twd', op:'>=', value:5});
    else if (s2 === 'today') { pending.numerics.push({field:'today_f', op:'>', value:0}, {field:'f_streak', op:'>=', value:3}); }
  } else if (style === 'swing') {
    if (s2 === 'f') pending.presets.push('f_5d_1y');
    else if (s2 === 't') pending.numerics.push({field:'t_5d_shares', op:'>', value:0});
    else if (s2 === 'd') pending.numerics.push({field:'d_5d_shares', op:'>', value:0});
    else if (s2 === 'three') pending.numerics.push({field:'three_5d_shares', op:'>', value:0});
    else if (s2 === 'f_t') { pending.numerics.push({field:'f_5d_shares', op:'>', value:0}, {field:'t_5d_shares', op:'>', value:0}); }
    else if (s2 === 'f_5y') pending.numerics.push({field:'f_5d_twd', op:'>=', value:5});
    else if (s2 === 't_1y') { pending.numerics.push({field:'t_5d_twd', op:'>=', val:1}, {field:'f_streak', op:'>=', value:3}); }
  } else if (style === 'long') {
    if (s2 === 'safe') pending.presets.push('streak3'); // safe >= 3, will refine
    else if (s2 === 'mid') pending.presets.push('streak3');
    else if (s2 === 'aggr') { pending.presets.push('streak3'); pending.numerics.push({field:'force_ratio', op:'>=', value:1.5}); }
    else if (s2 === 'stay10') pending.numerics.push({field:'f_stay_days', op:'>=', value:10});
    else if (s2 === 'dividend') { pending.presets.push('streak3'); pending.industries = ['金融保險','食品工業','油電燃氣業','半導體']; pending.industry = '金融保險'; }
    else if (s2 === 'lock') pending.numerics.push({field:'f_stay_days', op:'>=', value:5}, {field:'f_streak', op:'>=', value:3});
    else if (s2 === 'defense') pending.numerics.push({field:'three_5d_shares', op:'>', value:0}, {field:'three_5d_twd', op:'>=', value:0.1}, {field:'three_5d_twd', op:'<=', value:3});
  }
  // Step 3: 範圍
  var s3 = WIZARD.answers[3];
  if (s3 === 'concept') {
    pending.concepts = WIZARD.answers[4] || [];
  } else if (s3 === 'industry') {
    pending.industry = WIZARD.answers[4] || '';
  }
  // 去重 presets
  var seen = {};
  pending.presets = pending.presets.filter(function(p){ if (seen[p]) return false; seen[p] = true; return true; });
  return pending;
}'''

# New build: persona is the primary filter; direction just toggles
# between long-bias and short-bias via presets. If user picks "all", skip
# direction override (rely on persona defaults).
new_build = '''function buildPendingFromWizard() {
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

if old_build in content:
    content = content.replace(old_build, new_build)
    print('[buildPendingFromWizard] rewritten')
else:
    print('[buildPendingFromWizard-NOT-FOUND]')

# ============================================================
# Fix 6: clean dead zone (L9079-9113) - second copy of wizard action
# handlers AND the orphan script block after textsize.js
# ============================================================
# The dead zone is from "// D037c: wizard 換一組" until the second `</script></script>`
# closing at end of file.
dead_zone_pattern = re.compile(
    r'// D037c: wizard 換一組.*?</script></script>\s*</body>',
    re.DOTALL,
)
m = dead_zone_pattern.search(content)
if m:
    # Replace with clean closing
    content = content[:m.start()] + '// (dead zone removed in D042)\n</script>\n</body>'
    print(f'[dead-zone] removed {m.end() - m.start()} chars')
else:
    print('[dead-zone-NOT-FOUND]')

# ============================================================
# Fix 7: fix wiz-go intention string
# answers[0] = persona, answers[1] = direction, answers[2] = range, answers[3] = sub
# ============================================================
old_intention = """  // D037c: show wizard action panel
  var style = WIZARD.answers[0] || 'short';
  var dir = (WIZARD.answers[1] || []).filter(function(d){return d!=='all';});
  var range = WIZARD.answers[3] || 'all';
  var sub = WIZARD.answers[4] || '';
  var STYLE_NAMES = {short:'短線', swing:'波段', long:'長線'};
  var DIR_NAMES = {long:'偏多', short:'偏空'};
  var intention = '🚀 ' + STYLE_NAMES[style] + (dir.length?'（'+dir.map(function(d){return DIR_NAMES[d];}).join('+')+'）':'（全）') + ' ‧ ' + (range==='concept'?'概念: '+(Array.isArray(sub)?sub.join('/'):sub):range==='industry'?'產業: '+sub:'全市場');"""
new_intention = """  // D042: 4-step intention string (persona + direction + range)
  var persona = WIZARD.answers[0] || '';
  var dir = (WIZARD.answers[1] || []).filter(function(d){return d!=='all';});
  var range = WIZARD.answers[2] || 'all';
  var sub = WIZARD.answers[3] || '';
  var PERSONA_NAMES = {streak3:'法人連買', same_buy:'土洋同買', f_5d_1y:'外資大買', force_high:'量能爆發', f_stay_long:'外資停留', same_sell:'空方避雷', value:'金融存股', weak:'弱勢退場', ws_aqr:'AQR 雙優勢', ws_jt:'JT 動能', ws_mr:'跌深反彈', ws_qm:'法人鎖碼', ws_moat:'護城河之王', ws_news:'新聞利多', ws_eps:'EPS 成長'};
  var DIR_NAMES = {long:'偏多', short:'偏空'};
  var intention = '🎯 ' + (PERSONA_NAMES[persona] || persona) + (dir.length?'（'+dir.map(function(d){return DIR_NAMES[d];}).join('+')+'）':'') + ' ‧ ' + (range==='concept'?'概念: '+(Array.isArray(sub)?sub.join('/'):sub):range==='industry'?'產業: '+sub:'全市場');"""
if old_intention in content:
    content = content.replace(old_intention, new_intention)
    print('[intention] fixed (persona-based)')
else:
    print('[intention-NOT-FOUND]')

# ============================================================
# Fix 8: WIZARD.answers default - 4 steps now
# ============================================================
old_answers = "var WIZARD = { step: 0, answers: [null, null, null, null], history: [] };"
new_answers = "var WIZARD = { step: 0, answers: [null, null, null, null], history: [] };"
# (already 4 slots, but make sure the showWizard reset matches)
old_reset = "  WIZARD = { step: 0, answers: [null, ['long'], null, null], history: [] };"
new_reset = "  WIZARD = { step: 0, answers: [null, ['long'], null, null], history: [] };"
# Reset is fine as-is (4 slots), but the sub3a slot should be [4] not [3].
# Actually in D042, sub3a is answers[3], so reset to [null, ['long'], 'all', null]
new_reset = "  WIZARD = { step: 0, answers: [null, ['long'], 'all', null], history: [] };"
if old_reset in content:
    content = content.replace(old_reset, new_reset)
    print('[showWizard-reset] updated to 4-step')
else:
    print('[showWizard-reset-NOT-FOUND]')

# Also fix the wiz-go validation: it checks WIZARD.answers[3] for range and [4] for sub
# In D042, range = answers[2], sub = answers[3]
old_validation = """  if (WIZARD.answers[3] === 'concept' && (!WIZARD.answers[4] || WIZARD.answers[4].length === 0)) {
    alert('請至少選一個概念');
    return;
  }
  if (WIZARD.answers[3] === 'industry' && !WIZARD.answers[4]) {
    alert('請選一個產業');
    return;
  }"""
new_validation = """  if (WIZARD.answers[2] === 'concept' && (!WIZARD.answers[3] || WIZARD.answers[3].length === 0)) {
    alert('請至少選一個概念');
    return;
  }
  if (WIZARD.answers[2] === 'industry' && !WIZARD.answers[3]) {
    alert('請選一個產業');
    return;
  }"""
if old_validation in content:
    content = content.replace(old_validation, new_validation)
    print('[wiz-go validation] fixed')
else:
    print('[wiz-go validation-NOT-FOUND]')

# Also fix the sub3a toggle inside renderWizardStep: it uses WIZARD.answers[3]
# and writes WIZARD.answers[3]. That's already correct in D042.
# But the comment says "sub-step 3a" — fine.

# Save
if content == orig:
    print('\n*** NO CHANGES — file unchanged ***')
    sys.exit(1)

with open(PATH, 'w', encoding='utf-8') as f:
    f.write(content)
print(f'\nSaved: {len(content) - len(orig):+d} chars, new size = {len(content)}')
