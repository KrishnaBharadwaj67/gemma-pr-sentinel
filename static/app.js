/* ══════════════════════════════════════════════════════════════════════════
   DiffShield — Frontend Application
   State management, diff renderer, issue filters, Markdown exporter
   ══════════════════════════════════════════════════════════════════════════ */

const DiffShield = (() => {
  'use strict';

  // ── State ──────────────────────────────────────────────────────────────
  const state = {
    review: null,         // { summary, risk_score, verdict, issues }
    files: [],            // [{ path, language, additions, deletions }]
    engine: null,         // "hybrid_ai" | "static_fallback" | "static_only"
    telemetry: null,      // { model, latency_ms, tokens_generated, status }
    parsedDiff: '',       // raw diff text used for the last review
    activeFilters: new Set(['CRITICAL', 'WARNING', 'NITPICK']),
    ollamaStatus: 'checking',
  };

  // ── DOM Refs ───────────────────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  // ── Initialize ─────────────────────────────────────────────────────────
  function init() {
    setupTabs();
    setupDragDrop();
    checkOllamaHealth();
    // Periodically check Ollama status
    setInterval(checkOllamaHealth, 30000);
  }

  // ── Tab switching ──────────────────────────────────────────────────────
  function setupTabs() {
    $$('.input-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        $$('.input-tab').forEach(t => t.classList.remove('active'));
        $$('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        const target = tab.dataset.tab;
        $(`#tab-${target}`).classList.add('active');
      });
    });
  }

  // ── Drag & Drop ────────────────────────────────────────────────────────
  function setupDragDrop() {
    const uploadArea = $('#upload-area');
    if (!uploadArea) return;

    ['dragenter', 'dragover'].forEach(evt => {
      uploadArea.addEventListener(evt, e => {
        e.preventDefault();
        uploadArea.style.borderColor = 'var(--accent-indigo)';
        uploadArea.style.background = 'var(--accent-indigo-glow)';
      });
    });

    ['dragleave', 'drop'].forEach(evt => {
      uploadArea.addEventListener(evt, e => {
        e.preventDefault();
        uploadArea.style.borderColor = '';
        uploadArea.style.background = '';
      });
    });

    uploadArea.addEventListener('drop', e => {
      const file = e.dataTransfer.files[0];
      if (file) readPatchFile(file);
    });
  }

  // ── File upload handler ────────────────────────────────────────────────
  function handleFileUpload(event) {
    const file = event.target.files[0];
    if (file) readPatchFile(file);
  }

  function readPatchFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target.result;
      $('#diff-input').value = text;
      // Switch to paste tab to show content
      $$('.input-tab').forEach(t => t.classList.remove('active'));
      $$('.tab-content').forEach(c => c.classList.remove('active'));
      $$('.input-tab')[0].classList.add('active');
      $('#tab-paste').classList.add('active');
      showToast(`Loaded ${file.name}`, 'success');
      submitReview(text);
    };
    reader.readAsText(file);
  }

  // ── Load demo patch ────────────────────────────────────────────────────
  async function loadDemoPatch() {
    try {
      showLoading('Loading hackathon demo patch…', 'Fetching sample_diff.patch');
      const resp = await fetch('/api/sample-diff');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      $('#diff-input').value = data.diff_text;
      // Switch to paste tab
      $$('.input-tab').forEach(t => t.classList.remove('active'));
      $$('.tab-content').forEach(c => c.classList.remove('active'));
      $$('.input-tab')[0].classList.add('active');
      $('#tab-paste').classList.add('active');
      hideLoading();
      showToast('Demo patch loaded — running analysis…', 'info');
      submitReview(data.diff_text);
    } catch (err) {
      hideLoading();
      showToast(`Failed to load demo: ${err.message}`, 'error');
    }
  }

  // ── Review from paste ──────────────────────────────────────────────────
  function reviewFromPaste() {
    const text = $('#diff-input').value.trim();
    if (!text) {
      showToast('Please paste a unified diff first', 'error');
      return;
    }
    submitReview(text);
  }

  // ── Review from repo path ──────────────────────────────────────────────
  function reviewFromRepo() {
    const repoPath = $('#repo-path-input').value.trim();
    if (!repoPath) {
      showToast('Please enter a local Git repository path', 'error');
      return;
    }
    submitReview('', repoPath);
  }

  // ── Submit review ──────────────────────────────────────────────────────
  async function submitReview(diffText = '', repoPath = '') {
    const model = $('#model-select').value;
    showLoading(
      model === 'static-heuristics-only'
        ? 'Running static security scan…'
        : 'Analyzing with DiffShield…',
      model === 'static-heuristics-only'
        ? 'Deterministic AST + Regex engine — instant results'
        : `Static scan + ${model} deep review`
    );

    try {
      const body = {
        diff_text: diffText,
        model: model,
      };
      if (repoPath) body.repo_path = repoPath;

      const resp = await fetch('/api/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || `Server error: HTTP ${resp.status}`);
      }

      const data = await resp.json();
      state.review = data.review;
      state.files = data.files || [];
      state.engine = data.engine;
      state.telemetry = data.telemetry || {};
      state.parsedDiff = diffText;

      renderAll();
      hideLoading();
      showToast('Review complete!', 'success');

    } catch (err) {
      hideLoading();
      showToast(`Review failed: ${err.message}`, 'error');
    }
  }

  // ── Render everything ──────────────────────────────────────────────────
  function renderAll() {
    renderTelemetry();
    renderFileTree();
    renderSummary();
    renderDiff();
    renderMetrics();
  }

  // ── Telemetry bar ──────────────────────────────────────────────────────
  function renderTelemetry() {
    const t = state.telemetry || {};
    $('#tele-latency').textContent = t.latency_ms != null ? `${t.latency_ms} ms` : '— ms';
    $('#tele-tokens').textContent = t.tokens_generated != null ? `${t.tokens_generated} tok` : '— tok';

    const statusDot = $('#status-dot');
    const statusText = $('#tele-status');
    const s = (t.status || '').toLowerCase();

    if (s === 'success') {
      statusDot.className = 'status-dot online';
      statusText.textContent = 'ONLINE';
    } else if (s.includes('fallback') || s === 'static_only') {
      statusDot.className = 'status-dot fallback';
      statusText.textContent = 'FALLBACK';
    } else {
      statusDot.className = 'status-dot offline';
      statusText.textContent = 'OFFLINE';
    }
  }

  // ── File tree ──────────────────────────────────────────────────────────
  function renderFileTree() {
    const tree = $('#file-tree');
    if (!state.files.length) {
      tree.innerHTML = '<div style="padding: 20px 16px; text-align: center; color: var(--text-muted); font-size: 11px;">No files loaded yet</div>';
      return;
    }

    const issues = state.review?.issues || [];
    tree.innerHTML = state.files.map((f, i) => {
      const fileIssues = issues.filter(iss => iss.file === f.path);
      const issueCount = fileIssues.length;
      const iconSvg = getFileIcon(f.language);
      return `
        <div class="file-tree-item ${i === 0 ? 'active' : ''}" data-path="${escapeHtml(f.path)}" onclick="DiffShield.scrollToFile('${escapeHtml(f.path)}', this)">
          ${iconSvg}
          <span class="file-name" title="${escapeHtml(f.path)}">${escapeHtml(f.path)}</span>
          <span class="file-badge additions">+${f.additions}</span>
          <span class="file-badge deletions">-${f.deletions}</span>
          ${issueCount > 0 ? `<span class="file-issue-count">${issueCount}</span>` : ''}
        </div>
      `;
    }).join('');
  }

  function getFileIcon(lang) {
    return `<svg class="file-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
  }

  function scrollToFile(path, el) {
    $$('.file-tree-item').forEach(item => item.classList.remove('active'));
    if (el) el.classList.add('active');
    const section = document.querySelector(`.diff-file-section[data-path="${path}"]`);
    if (section) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // ── Executive Summary ──────────────────────────────────────────────────
  function renderSummary() {
    const review = state.review;
    if (!review) return;

    $('#empty-state').style.display = 'none';
    const summary = $('#exec-summary');
    summary.style.display = '';

    // Summary text
    $('#summary-text').textContent = review.summary || 'Review complete.';

    // Verdict badge
    const verdictEl = $('#verdict-badge');
    const v = (review.verdict || '').toUpperCase();
    verdictEl.textContent = v.replace(/_/g, ' ');
    verdictEl.className = 'verdict-badge';
    if (v.includes('APPROVED') && !v.includes('BLOCKED') && !v.includes('CHANGES')) {
      verdictEl.classList.add('approved');
    } else if (v.includes('BLOCKED')) {
      verdictEl.classList.add('blocked');
    } else {
      verdictEl.classList.add('changes-requested');
    }

    // Engine badge
    const engineEl = $('#engine-badge');
    if (state.engine === 'hybrid_ai') {
      engineEl.textContent = 'Gemma AI + Static';
      engineEl.className = 'engine-badge hybrid';
    } else if (state.engine === 'static_fallback') {
      engineEl.textContent = 'Static Fallback';
      engineEl.className = 'engine-badge static';
    } else {
      engineEl.textContent = 'Static Only';
      engineEl.className = 'engine-badge static';
    }

    // Animated Risk Gauge
    animateGauge(review.risk_score || 0);
  }

  function animateGauge(score) {
    const circumference = 2 * Math.PI * 42; // ~263.89
    const offset = circumference - (score / 100) * circumference;
    const fill = $('#gauge-fill');
    const scoreNum = $('#score-number');

    // Determine color
    let color;
    if (score >= 70) color = '#EF4444';
    else if (score >= 40) color = '#F59E0B';
    else color = '#10B981';

    fill.style.stroke = color;
    scoreNum.style.color = color;

    // Animate
    requestAnimationFrame(() => {
      fill.style.strokeDashoffset = offset;
    });

    // Animate counter
    let current = 0;
    const step = Math.max(1, Math.ceil(score / 40));
    const timer = setInterval(() => {
      current += step;
      if (current >= score) {
        current = score;
        clearInterval(timer);
      }
      scoreNum.textContent = current;
    }, 30);
  }

  // ── Diff Renderer ──────────────────────────────────────────────────────
  function renderDiff() {
    const viewer = $('#diff-viewer');
    if (!state.parsedDiff && !state.files.length) {
      viewer.innerHTML = '';
      return;
    }

    const diffText = state.parsedDiff;
    const issues = state.review?.issues || [];
    const files = parseDiffIntoFiles(diffText);

    viewer.innerHTML = files.map(file => {
      const fileIssues = issues.filter(iss => iss.file === file.path);
      return `
        <div class="diff-file-section" data-path="${escapeHtml(file.path)}">
          <div class="diff-file-header">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <span class="file-path">${escapeHtml(file.path)}</span>
            <span style="margin-left: auto; font-size: 11px; color: var(--text-tertiary);">${file.language}</span>
          </div>
          ${file.hunks.map(hunk => renderHunk(hunk, fileIssues, file.path)).join('')}
        </div>
      `;
    }).join('');
  }

  function renderHunk(hunk, fileIssues, filePath) {
    let html = `<div class="diff-hunk-header">${escapeHtml(hunk.header)}</div>`;
    html += '<table class="diff-table">';

    hunk.lines.forEach(line => {
      const filtered = state.activeFilters;
      const lineIssues = fileIssues.filter(
        iss => iss.line === line.newNum && filtered.has(iss.severity)
      );

      let rowClass = 'diff-line-context';
      let prefix = ' ';
      let oldNum = line.oldNum || '';
      let newNum = line.newNum || '';

      if (line.type === 'add') {
        rowClass = 'diff-line-add';
        prefix = '+';
        oldNum = '';
      } else if (line.type === 'delete') {
        rowClass = 'diff-line-delete';
        prefix = '-';
        newNum = '';
      }

      html += `<tr class="${rowClass}">
        <td class="diff-line-num">${oldNum}</td>
        <td class="diff-line-num">${newNum}</td>
        <td class="diff-line-content">${prefix}${escapeHtml(line.content)}</td>
      </tr>`;

      // Inject inline issue cards
      lineIssues.forEach(issue => {
        html += renderIssueCard(issue);
      });
    });

    html += '</table>';
    return html;
  }

  function renderIssueCard(issue) {
    const sevClass = issue.severity.toLowerCase();
    const sourceClass = issue.source?.includes('Gemma') || issue.source?.includes('AI') ? 'ai' : 'static';
    const fixId = `fix-${Math.random().toString(36).substr(2, 9)}`;

    return `
      <tr class="issue-card-row"><td colspan="3">
        <div class="issue-card severity-${sevClass}">
          <div class="issue-card-header">
            <span class="severity-pill ${sevClass}">${issue.severity}</span>
            <span class="category-badge">${issue.category || ''}</span>
            <span class="source-badge ${sourceClass}">${escapeHtml(issue.source || '')}</span>
            <span class="issue-title">${escapeHtml(issue.title || '')}</span>
          </div>
          <div class="issue-description">${escapeHtml(issue.description || '')}</div>
          ${issue.suggested_fix ? `
            <div class="issue-fix-box">
              <div class="issue-fix-header">
                <span>✦ Suggested Fix</span>
                <button class="btn-copy-fix" onclick="DiffShield.copyFix('${fixId}')">Copy Fix</button>
              </div>
              <pre class="issue-fix-code" id="${fixId}">${escapeHtml(issue.suggested_fix)}</pre>
            </div>
          ` : ''}
        </div>
      </td></tr>
    `;
  }

  // ── Metrics panel ──────────────────────────────────────────────────────
  function renderMetrics() {
    const issues = state.review?.issues || [];

    const critical = issues.filter(i => i.severity === 'CRITICAL').length;
    const security = issues.filter(i => i.category === 'SECURITY').length;
    const logic = issues.filter(i => i.category === 'LOGIC' || i.category === 'PERFORMANCE').length;
    const style = issues.filter(i => i.category === 'STYLE' || (i.category !== 'SECURITY' && i.category !== 'LOGIC' && i.category !== 'PERFORMANCE')).length;

    animateMetric('#metric-critical', critical);
    animateMetric('#metric-security', security);
    animateMetric('#metric-logic', logic);
    animateMetric('#metric-style', style);
  }

  function animateMetric(selector, targetValue) {
    const el = $(selector);
    if (!el) return;
    let current = 0;
    if (targetValue === 0) {
      el.textContent = '0';
      return;
    }
    const step = Math.max(1, Math.ceil(targetValue / 20));
    const timer = setInterval(() => {
      current += step;
      if (current >= targetValue) {
        current = targetValue;
        clearInterval(timer);
      }
      el.textContent = current;
    }, 40);
  }

  // ── Filter toggle ──────────────────────────────────────────────────────
  function toggleFilter(severity, btn) {
    if (state.activeFilters.has(severity)) {
      state.activeFilters.delete(severity);
      btn.classList.remove('active');
    } else {
      state.activeFilters.add(severity);
      btn.classList.add('active');
    }
    // Re-render diff to apply filters
    renderDiff();
  }

  // ── Copy fix to clipboard ─────────────────────────────────────────────
  function copyFix(fixId) {
    const el = document.getElementById(fixId);
    if (!el) return;
    navigator.clipboard.writeText(el.textContent).then(() => {
      showToast('Fix copied to clipboard!', 'success');
    }).catch(() => {
      // Fallback for non-HTTPS
      const range = document.createRange();
      range.selectNodeContents(el);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      try {
        document.execCommand('copy');
        showToast('Fix copied to clipboard!', 'success');
      } catch {
        showToast('Failed to copy', 'error');
      }
      sel.removeAllRanges();
    });
  }

  // ── Export Markdown ────────────────────────────────────────────────────
  function exportMarkdown() {
    if (!state.review) {
      showToast('No review to export', 'error');
      return;
    }

    const md = generateMarkdown();
    downloadText(md, 'diffshield-review.md', 'text/markdown');
    showToast('Review exported as Markdown!', 'success');
  }

  function copyGitHubComment() {
    if (!state.review) {
      showToast('No review to copy', 'error');
      return;
    }

    const md = generateMarkdown();
    navigator.clipboard.writeText(md).then(() => {
      showToast('GitHub comment copied!', 'success');
    }).catch(() => {
      showToast('Failed to copy to clipboard', 'error');
    });
  }

  function generateMarkdown() {
    const r = state.review;
    const issues = r.issues || [];
    const verdictEmoji = r.verdict?.includes('APPROVED') ? '✅' :
      r.verdict?.includes('BLOCKED') ? '🚫' : '⚠️';

    let md = `# 🛡️ DiffShield PR Review\n\n`;
    md += `**Verdict:** ${verdictEmoji} ${r.verdict?.replace(/_/g, ' ')}\n`;
    md += `**Risk Score:** ${r.risk_score}/100\n`;
    md += `**Engine:** ${state.engine}\n\n`;
    md += `## Summary\n\n${r.summary}\n\n`;

    if (issues.length > 0) {
      md += `## Issues Found (${issues.length})\n\n`;

      const critical = issues.filter(i => i.severity === 'CRITICAL');
      const warnings = issues.filter(i => i.severity === 'WARNING');
      const nitpicks = issues.filter(i => i.severity === 'NITPICK');

      if (critical.length) {
        md += `### 🔴 Critical (${critical.length})\n\n`;
        critical.forEach(i => {
          md += formatIssueMd(i);
        });
      }
      if (warnings.length) {
        md += `### 🟡 Warnings (${warnings.length})\n\n`;
        warnings.forEach(i => {
          md += formatIssueMd(i);
        });
      }
      if (nitpicks.length) {
        md += `### 🔵 Nitpicks (${nitpicks.length})\n\n`;
        nitpicks.forEach(i => {
          md += formatIssueMd(i);
        });
      }
    }

    md += `\n---\n*Generated by [DiffShield](https://github.com/diffshield) — Air-Gapped PR Intelligence*\n`;
    return md;
  }

  function formatIssueMd(issue) {
    let md = `- **\`${issue.file}:${issue.line}\`** — ${issue.title}\n`;
    md += `  - *${issue.category}* | Source: ${issue.source}\n`;
    md += `  - ${issue.description}\n`;
    if (issue.suggested_fix) {
      md += `  - **Fix:**\n    \`\`\`\n    ${issue.suggested_fix}\n    \`\`\`\n`;
    }
    md += '\n';
    return md;
  }

  // ── Ollama health check ────────────────────────────────────────────────
  async function checkOllamaHealth() {
    try {
      const resp = await fetch('/api/health');
      if (!resp.ok) throw new Error();
      const data = await resp.json();

      const dot = $('#status-dot');
      const text = $('#tele-status');

      if (data.status === 'online') {
        dot.className = 'status-dot online';
        text.textContent = 'ONLINE';
        state.ollamaStatus = 'online';
      } else {
        dot.className = 'status-dot fallback';
        text.textContent = 'FALLBACK MODE';
        state.ollamaStatus = 'fallback';
      }
    } catch {
      const dot = $('#status-dot');
      const text = $('#tele-status');
      if (dot) dot.className = 'status-dot fallback';
      if (text) text.textContent = 'FALLBACK MODE';
      state.ollamaStatus = 'fallback';
    }
  }

  // ── Simple Diff Parser (client-side) ───────────────────────────────────
  function parseDiffIntoFiles(diffText) {
    if (!diffText) return [];
    const files = [];
    let currentFile = null;
    let currentHunk = null;
    let oldLine = 0;
    let newLine = 0;

    const lines = diffText.replace(/\r\n/g, '\n').split('\n');

    for (const raw of lines) {
      if (raw.startsWith('diff --git')) {
        const parts = raw.split(' b/');
        const path = parts[1] || 'unknown';
        currentFile = { path, language: guessLang(path), hunks: [] };
        files.push(currentFile);
        currentHunk = null;
        continue;
      }

      if (raw.startsWith('--- a/') && currentFile) {
        continue;
      }
      if (raw.startsWith('+++ b/') && currentFile) {
        currentFile.path = raw.slice(6);
        currentFile.language = guessLang(currentFile.path);
        continue;
      }
      if (raw.startsWith('--- ') || raw.startsWith('+++ ')) continue;
      if (raw.startsWith('index ') || raw.startsWith('new file') ||
          raw.startsWith('deleted file') || raw.startsWith('old mode') ||
          raw.startsWith('new mode') || raw.startsWith('similarity') ||
          raw.startsWith('rename') || raw.startsWith('Binary')) continue;

      const hunkMatch = raw.match(/^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)$/);
      if (hunkMatch && currentFile) {
        oldLine = parseInt(hunkMatch[1]);
        newLine = parseInt(hunkMatch[3]);
        currentHunk = { header: raw, lines: [] };
        currentFile.hunks.push(currentHunk);
        continue;
      }

      if (currentHunk) {
        if (raw.startsWith('+')) {
          currentHunk.lines.push({ type: 'add', oldNum: null, newNum: newLine, content: raw.slice(1) });
          newLine++;
        } else if (raw.startsWith('-')) {
          currentHunk.lines.push({ type: 'delete', oldNum: oldLine, newNum: null, content: raw.slice(1) });
          oldLine++;
        } else if (raw.startsWith('\\')) {
          continue;
        } else {
          const content = raw.startsWith(' ') ? raw.slice(1) : raw;
          currentHunk.lines.push({ type: 'context', oldNum: oldLine, newNum: newLine, content });
          oldLine++;
          newLine++;
        }
      }
    }

    return files;
  }

  function guessLang(path) {
    const ext = (path.split('.').pop() || '').toLowerCase();
    const map = {
      py: 'Python', js: 'JavaScript', ts: 'TypeScript', jsx: 'React JSX',
      tsx: 'React TSX', java: 'Java', go: 'Go', rs: 'Rust', rb: 'Ruby',
      php: 'PHP', c: 'C', cpp: 'C++', cs: 'C#', swift: 'Swift', kt: 'Kotlin',
      sh: 'Shell', yaml: 'YAML', yml: 'YAML', json: 'JSON', html: 'HTML',
      css: 'CSS', sql: 'SQL', md: 'Markdown',
    };
    return map[ext] || 'Text';
  }

  // ── Utility helpers ────────────────────────────────────────────────────
  function escapeHtml(text) {
    if (!text) return '';
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    return String(text).replace(/[&<>"']/g, c => map[c]);
  }

  function showLoading(text, sub) {
    const overlay = $('#loading-overlay');
    $('#loading-text').textContent = text || 'Analyzing…';
    $('#loading-sub').textContent = sub || '';
    overlay.classList.add('active');
  }

  function hideLoading() {
    $('#loading-overlay').classList.remove('active');
  }

  function showToast(message, type = 'info') {
    const container = $('#toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        ${type === 'success' ? '<path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>'
          : type === 'error' ? '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>'
          : '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>'}
      </svg>
      <span>${escapeHtml(message)}</span>
    `;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = 'toastOut 0.3s ease-out forwards';
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }

  function downloadText(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ── Init on DOM ready ──────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', init);

  // ── Public API ─────────────────────────────────────────────────────────
  return {
    loadDemoPatch,
    reviewFromPaste,
    reviewFromRepo,
    handleFileUpload,
    toggleFilter,
    copyFix,
    exportMarkdown,
    copyGitHubComment,
    scrollToFile,
  };
})();
