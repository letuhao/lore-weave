import type { TileMapSkeleton } from '../data/types';
import { generateSkeleton, probeLlm } from '../llm/skeleton_generator';
import type { AttemptRecord } from '../llm/types';

export interface DialogResult {
  skeleton: TileMapSkeleton;
  attempts: AttemptRecord[];
  total_tokens?: number;
}

/**
 * LLM Skeleton Generation dialog — DOM-based modal.
 *
 * UX flow:
 *   1. User clicks "Generate from Prompt" button → opens this dialog
 *   2. Modal shows: model name input, prompt textarea, probe-status, generate button
 *   3. On click: probe endpoint → if reachable, call generateSkeleton with retry loop
 *   4. Live status updates per attempt (calling / parsing / validating / retrying)
 *   5. On success → user can preview the result, click Apply or Cancel
 *   6. On failure → show error + attempt history; user can retry or close
 */
export class LlmDialog {
  private overlay: HTMLElement;
  private modal: HTMLElement;
  private modelInput!: HTMLInputElement;
  private promptInput!: HTMLTextAreaElement;
  private probeStatus!: HTMLElement;
  private generateBtn!: HTMLButtonElement;
  private cancelBtn!: HTMLButtonElement;
  private statusLog!: HTMLElement;
  private resultPanel!: HTMLElement;
  private applyBtn!: HTMLButtonElement;

  private currentAbort: AbortController | null = null;
  private currentResult: TileMapSkeleton | null = null;
  private onApply: ((skeleton: TileMapSkeleton, attempts: AttemptRecord[], tokens?: number) => void) | null = null;

  constructor() {
    this.overlay = document.createElement('div');
    this.overlay.className = 'llm-dialog-overlay hidden';
    this.modal = document.createElement('div');
    this.modal.className = 'llm-dialog';
    this.overlay.appendChild(this.modal);
    document.body.appendChild(this.overlay);

    this.buildLayout();
    this.bindEvents();
  }

  open(onApply: (skeleton: TileMapSkeleton, attempts: AttemptRecord[], tokens?: number) => void): void {
    this.onApply = onApply;
    this.overlay.classList.remove('hidden');
    this.statusLog.innerHTML = '';
    this.resultPanel.classList.add('hidden');
    this.applyBtn.disabled = true;
    this.currentResult = null;
    this.probeEndpoint();
    setTimeout(() => this.promptInput.focus(), 50);
  }

  close(): void {
    if (this.currentAbort) {
      this.currentAbort.abort();
      this.currentAbort = null;
    }
    this.overlay.classList.add('hidden');
    this.onApply = null;
  }

  private buildLayout(): void {
    this.modal.innerHTML = `
      <div class="llm-dialog-header">
        <h2>Generate Skeleton with LLM</h2>
        <button class="llm-dialog-close" aria-label="Close">×</button>
      </div>
      <div class="llm-dialog-body">
        <div class="llm-field">
          <label>Model</label>
          <input type="text" id="llm-model" placeholder="qwen3-14b" value="qwen3-14b" />
          <span class="llm-hint">Whatever model is loaded in lmstudio (model name is informational)</span>
        </div>
        <div class="llm-field">
          <label>Endpoint status</label>
          <div id="llm-probe-status" class="llm-probe">checking...</div>
        </div>
        <div class="llm-field">
          <label>Prompt (Vietnamese or English)</label>
          <textarea id="llm-prompt" rows="6" placeholder="Tạo skeleton cho 1 sci-fi star sector 64×64. Trung tâm là 1 hành tinh thủ phủ; có 4 trạm khai khoáng quanh; vành đai tiểu hành tinh phía bắc; nebula phía nam..."></textarea>
        </div>
        <div class="llm-actions">
          <button id="llm-cancel" class="llm-btn-secondary">Cancel</button>
          <button id="llm-generate" class="llm-btn-primary">Generate</button>
        </div>
        <div class="llm-status-log" id="llm-status-log"></div>
        <div class="llm-result hidden" id="llm-result">
          <h3>Generated skeleton preview</h3>
          <div id="llm-result-summary"></div>
          <pre id="llm-result-json"></pre>
          <div class="llm-actions">
            <button id="llm-apply" class="llm-btn-primary" disabled>Apply to map</button>
          </div>
        </div>
      </div>
    `;
    this.modelInput = this.modal.querySelector<HTMLInputElement>('#llm-model')!;
    this.promptInput = this.modal.querySelector<HTMLTextAreaElement>('#llm-prompt')!;
    this.probeStatus = this.modal.querySelector<HTMLElement>('#llm-probe-status')!;
    this.generateBtn = this.modal.querySelector<HTMLButtonElement>('#llm-generate')!;
    this.cancelBtn = this.modal.querySelector<HTMLButtonElement>('#llm-cancel')!;
    this.statusLog = this.modal.querySelector<HTMLElement>('#llm-status-log')!;
    this.resultPanel = this.modal.querySelector<HTMLElement>('#llm-result')!;
    this.applyBtn = this.modal.querySelector<HTMLButtonElement>('#llm-apply')!;
  }

  private bindEvents(): void {
    this.modal.querySelector<HTMLButtonElement>('.llm-dialog-close')!.addEventListener('click', () => this.close());
    this.cancelBtn.addEventListener('click', () => this.close());
    this.overlay.addEventListener('click', (e) => {
      if (e.target === this.overlay) this.close();
    });

    this.generateBtn.addEventListener('click', () => this.runGeneration());
    this.applyBtn.addEventListener('click', () => {
      if (this.currentResult && this.onApply) {
        this.onApply(this.currentResult, [], undefined);
        this.close();
      }
    });

    document.addEventListener('keydown', (e) => {
      if (this.overlay.classList.contains('hidden')) return;
      if (e.key === 'Escape') this.close();
    });
  }

  private async probeEndpoint(): Promise<void> {
    this.probeStatus.textContent = 'Probing /api/llm...';
    this.probeStatus.className = 'llm-probe';
    const result = await probeLlm({ model: this.modelInput.value });
    if (result.ok) {
      this.probeStatus.textContent = `✓ ${result.message} via ${result.endpoint}`;
      this.probeStatus.className = 'llm-probe ok';
    } else {
      this.probeStatus.innerHTML =
        `✗ Cannot reach LLM endpoint: ${escapeHtml(result.message)}<br>` +
        `<span class="llm-hint">` +
        `Start lmstudio + load a model + enable server (default port 1234). ` +
        `Override endpoint in <code>.env.local</code> with <code>VITE_LLM_ENDPOINT=http://...</code>` +
        `</span>`;
      this.probeStatus.className = 'llm-probe fail';
    }
  }

  private async runGeneration(): Promise<void> {
    const prompt = this.promptInput.value.trim();
    if (!prompt) {
      this.appendStatus('error', 'Prompt is empty.');
      return;
    }

    if (this.currentAbort) {
      this.currentAbort.abort();
    }
    this.currentAbort = new AbortController();

    this.statusLog.innerHTML = '';
    this.resultPanel.classList.add('hidden');
    this.generateBtn.disabled = true;
    this.generateBtn.textContent = 'Generating...';

    const startedAt = performance.now();
    this.appendStatus('info', `Calling LLM (model=${this.modelInput.value})...`);

    try {
      const result = await generateSkeleton(prompt, {
        model: this.modelInput.value,
        temperature: 0.7,
        // 16000 to handle reasoning-mode models (Qwen 3 thinking burns ~4K tokens
        // before output even with /no_think — directive is best-effort)
        maxTokens: 16000,
        signal: this.currentAbort.signal,
        onProgress: (info) => {
          const labels: Record<string, string> = {
            calling: '→ calling',
            parsing: '→ parsing JSON',
            validating: '→ validating schema',
            retrying: '↻ retrying with feedback',
            done: '✓ success',
            failed: '✗ failed',
          };
          const cls = info.phase === 'done' ? 'ok' : info.phase === 'failed' ? 'error' : 'info';
          this.appendStatus(cls, `Attempt ${info.attempt} ${labels[info.phase] ?? info.phase}${info.detail ? ` (${info.detail})` : ''}`);
        },
      });

      const elapsed = ((performance.now() - startedAt) / 1000).toFixed(1);

      if (result.ok && result.value) {
        this.currentResult = result.value;
        this.appendStatus('ok', `DONE in ${elapsed}s · ${result.total_tokens ?? '?'} tokens · ${result.attempts.length} attempt(s)`);
        this.showResult(result.value, result.attempts, result.total_tokens);
      } else {
        this.appendStatus('error', `FAILED after ${result.attempts.length} attempt(s) (${elapsed}s)`);
        this.showFailureDetails(result.attempts);
      }
    } catch (e) {
      this.appendStatus('error', `Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      this.generateBtn.disabled = false;
      this.generateBtn.textContent = 'Generate';
      this.currentAbort = null;
    }
  }

  private appendStatus(level: 'info' | 'ok' | 'error', msg: string): void {
    const div = document.createElement('div');
    div.className = `llm-log-line ${level}`;
    div.textContent = msg;
    this.statusLog.appendChild(div);
    this.statusLog.scrollTop = this.statusLog.scrollHeight;
  }

  private showResult(skeleton: TileMapSkeleton, _attempts: AttemptRecord[], tokens?: number): void {
    this.resultPanel.classList.remove('hidden');
    const summary = this.modal.querySelector<HTMLElement>('#llm-result-summary')!;
    summary.innerHTML = `
      <div><strong>${escapeHtml(skeleton.skeleton_id)}</strong></div>
      <div>${skeleton.terrain_zones.length} zones · ${skeleton.cell_anchors.length} cells · ${skeleton.landmark_anchors.length} landmarks · ${skeleton.road_connections.length} roads</div>
      <div class="llm-hint">${tokens ?? '?'} tokens used</div>
    `;
    const json = this.modal.querySelector<HTMLElement>('#llm-result-json')!;
    json.textContent = JSON.stringify(skeleton, null, 2);
    this.applyBtn.disabled = false;
  }

  private showFailureDetails(attempts: AttemptRecord[]): void {
    const last = attempts[attempts.length - 1];
    if (!last) return;
    const detailDiv = document.createElement('div');
    detailDiv.className = 'llm-log-line error';
    if (last.validation_errors && last.validation_errors.length > 0) {
      detailDiv.innerHTML = `<strong>Last validation errors:</strong><br>${last.validation_errors.map((e) => '• ' + escapeHtml(e)).join('<br>')}`;
    } else if (last.parse_error) {
      detailDiv.innerHTML = `<strong>Last error:</strong> ${escapeHtml(last.parse_error)}`;
    }
    this.statusLog.appendChild(detailDiv);
  }
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
