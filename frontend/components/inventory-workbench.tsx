"use client";

import {
  type FormEvent,
  type KeyboardEvent,
  useMemo,
  useState,
} from "react";

import {
  API_BASE_URL,
  ApiClientError,
  type ChatSuccessResponse,
  type CurrentUser,
  type EvidenceDetail,
  type EvidenceSummary,
  type InventoryResult,
  type RoleName,
  type ThreadResponse,
  type ToolName,
  m1Api,
} from "@/lib/api";

const SAMPLE_QUESTION = "德国仓蘑菇灯还有多少可售库存？";
const DEMO_ACCOUNTS = [
  { label: "德国运营", email: "de.operator@demo.deepsearch.local" },
  { label: "法国运营", email: "fr.operator@demo.deepsearch.local" },
] as const;

interface SessionState {
  token: string;
  user: CurrentUser;
  thread: ThreadResponse;
}

interface ConversationItem {
  id: string;
  role: "user" | "assistant" | "error";
  content: string;
  response?: ChatSuccessResponse;
  traceId?: string | null;
}

function createLocalId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function roleLabel(role: RoleName): string {
  return {
    company_owner: "公司负责人",
    product_scout: "选品人员",
    amazon_operator: "Amazon运营",
  }[role];
}

function toolLabel(tool: ToolName): string {
  return {
    get_product_spec: "确认商品规格",
    search_inventory: "查询可售库存",
  }[tool];
}

function formatEvidenceTime(value: string, marketCode?: string): string {
  const timeZone = marketCode === "FR" ? "Europe/Paris" : "Europe/Berlin";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "medium",
    timeZone,
  }).format(new Date(value));
}

function isInventoryResult(
  value: EvidenceDetail["structured_data"],
): value is InventoryResult {
  return "available" in value && "warehouse_code" in value;
}

export function InventoryWorkbench() {
  const [email, setEmail] = useState<string>(DEMO_ACCOUNTS[0].email);
  const [password, setPassword] = useState("");
  const [session, setSession] = useState<SessionState | null>(null);
  const [loginPending, setLoginPending] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ConversationItem[]>([]);
  const [sending, setSending] = useState(false);

  const [selectedEvidence, setSelectedEvidence] =
    useState<EvidenceSummary | null>(null);
  const [evidenceDetail, setEvidenceDetail] =
    useState<EvidenceDetail | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  const evidenceCount = useMemo(
    () =>
      messages.reduce(
        (count, item) => count + (item.response?.evidence.length ?? 0),
        0,
      ),
    [messages],
  );

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loginPending) return;

    setLoginPending(true);
    setLoginError(null);
    try {
      const login = await m1Api.login(email, password);
      const user = await m1Api.me(login.access_token);
      const thread = await m1Api.createThread(
        login.access_token,
        "M1 库存查询演示",
      );
      setSession({ token: login.access_token, user, thread });
      setPassword("");
    } catch (error) {
      setLoginError(messageForError(error, "登录或创建会话失败"));
    } finally {
      setLoginPending(false);
    }
  }

  function logout(message?: string) {
    setSession(null);
    setMessages([]);
    setQuestion("");
    setSelectedEvidence(null);
    setEvidenceDetail(null);
    setEvidenceError(null);
    setLoginError(message ?? null);
  }

  async function loadEvidence(summary: EvidenceSummary) {
    if (!session) return;
    setSelectedEvidence(summary);
    setEvidenceDetail(null);
    setEvidenceError(null);
    setEvidenceLoading(true);
    try {
      const detail = await m1Api.evidence(session.token, summary.id);
      setEvidenceDetail(detail);
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 401) {
        logout("登录状态已失效，请重新登录");
        return;
      }
      setEvidenceError(messageForError(error, "证据详情读取失败"));
    } finally {
      setEvidenceLoading(false);
    }
  }

  async function handleSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!session || !trimmed || sending) return;

    setQuestion("");
    setSending(true);
    setMessages((current) => [
      ...current,
      { id: createLocalId("user"), role: "user", content: trimmed },
    ]);

    try {
      const response = await m1Api.sendMessage(
        session.token,
        session.thread.thread_id,
        trimmed,
      );
      setMessages((current) => [
        ...current,
        {
          id: response.message_id,
          role: "assistant",
          content: response.answer,
          response,
        },
      ]);
      const firstEvidence = response.evidence[0];
      if (firstEvidence) void loadEvidence(firstEvidence);
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 401) {
        logout("登录状态已失效，请重新登录");
        return;
      }
      setMessages((current) => [
        ...current,
        {
          id: createLocalId("error"),
          role: "error",
          content: messageForError(error, "本次查询失败"),
          traceId: error instanceof ApiClientError ? error.traceId : null,
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  function handleQuestionKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  if (!session) {
    return (
      <LoginView
        email={email}
        password={password}
        pending={loginPending}
        error={loginError}
        onEmailChange={setEmail}
        onPasswordChange={setPassword}
        onSubmit={handleLogin}
      />
    );
  }

  return (
    <main className="workbench-shell">
      <Sidebar
        user={session.user}
        thread={session.thread}
        evidenceCount={evidenceCount}
        onLogout={() => logout()}
      />

      <section className="conversation-panel" aria-label="库存查询对话">
        <header className="conversation-header">
          <div>
            <p className="eyebrow">M1 / Inventory query</p>
            <h1>库存证据工作台</h1>
          </div>
          <div className="connection-state" title={API_BASE_URL}>
            <span className="status-dot" aria-hidden="true" />
            后端已连接
          </div>
        </header>

        <div className="synthetic-banner" role="note">
          <DatabaseIcon />
          <div>
            <strong>当前仅使用合成演示数据</strong>
            <span>不代表真实Amazon仓库或公司经营数据</span>
          </div>
        </div>

        <div className="message-stream" aria-live="polite">
          {messages.length === 0 ? (
            <EmptyConversation onUseExample={() => setQuestion(SAMPLE_QUESTION)} />
          ) : (
            messages.map((message) => (
              <MessageBlock
                key={message.id}
                message={message}
                selectedEvidenceId={selectedEvidence?.id ?? null}
                onEvidenceSelect={loadEvidence}
              />
            ))
          )}

          {sending ? (
            <div className="running-card" role="status">
              <span className="running-mark" aria-hidden="true" />
              <div>
                <strong>正在核对库存与权限</strong>
                <span>模型提出Tool建议，后端审核后查询数据库</span>
              </div>
            </div>
          ) : null}
        </div>

        <form className="composer" onSubmit={handleSend}>
          <label htmlFor="inventory-question">询问库存</label>
          <div className="composer-box">
            <textarea
              id="inventory-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={handleQuestionKeyDown}
              placeholder="例如：德国仓蘑菇灯还有多少可售库存？"
              maxLength={4000}
              rows={2}
              disabled={sending}
            />
            <button
              className="send-button"
              type="submit"
              disabled={sending || question.trim().length === 0}
            >
              {sending ? "查询中" : "查询库存"}
              <ArrowIcon />
            </button>
          </div>
          <div className="composer-hint">
            <span>Enter 发送 · Shift + Enter 换行</span>
            <span>{question.length} / 4000</span>
          </div>
        </form>
      </section>

      <EvidenceRail
        summary={selectedEvidence}
        detail={evidenceDetail}
        loading={evidenceLoading}
        error={evidenceError}
        onRetry={() => selectedEvidence && void loadEvidence(selectedEvidence)}
      />
    </main>
  );
}

interface LoginViewProps {
  email: string;
  password: string;
  pending: boolean;
  error: string | null;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

function LoginView(props: LoginViewProps) {
  return (
    <main className="login-shell">
      <section className="login-intro" aria-labelledby="login-title">
        <div className="brand-lockup">
          <span className="brand-mark">DS</span>
          <span>Deep Search Pro</span>
        </div>
        <div className="login-thesis">
          <p className="eyebrow">Evidence Workshop / M1</p>
          <h1 id="login-title">
            每个库存数字，
            <span>都能回到证据。</span>
          </h1>
          <p>
            登录后询问德国或法国仓库存。系统会展示答案、数据时间和PostgreSQL证据，而不让模型直接碰数据库。
          </p>
        </div>
        <div className="evidence-stamp" aria-hidden="true">
          <span>DATABASE EVIDENCE</span>
          <strong>E / 01</strong>
          <small>SYNTHETIC DEMO</small>
        </div>
      </section>

      <section className="login-panel" aria-label="登录">
        <div className="login-form-wrap">
          <p className="eyebrow">受控访问</p>
          <h2>进入库存工作台</h2>
          <p className="form-description">
            使用本地Seed演示账号。Token只保存在当前页面内，刷新页面后需要重新登录。
          </p>

          <div className="account-shortcuts" aria-label="选择演示账号">
            {DEMO_ACCOUNTS.map((account) => (
              <button
                key={account.email}
                type="button"
                className={props.email === account.email ? "active" : ""}
                onClick={() => props.onEmailChange(account.email)}
              >
                {account.label}
              </button>
            ))}
          </div>

          <form onSubmit={props.onSubmit}>
            <label htmlFor="email">邮箱</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              value={props.email}
              onChange={(event) => props.onEmailChange(event.target.value)}
              required
            />

            <label htmlFor="password">密码</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={props.password}
              onChange={(event) => props.onPasswordChange(event.target.value)}
              minLength={8}
              required
            />
            <p className="field-hint">密码来自本地 `.env` 的 M1_DEMO_PASSWORD</p>

            {props.error ? (
              <div className="inline-error" role="alert">
                <AlertIcon />
                {props.error}
              </div>
            ) : null}

            <button className="primary-button" type="submit" disabled={props.pending}>
              {props.pending ? "正在验证身份…" : "登录并创建会话"}
              <ArrowIcon />
            </button>
          </form>

          <p className="api-caption">API · {API_BASE_URL}</p>
        </div>
      </section>
    </main>
  );
}

interface SidebarProps {
  user: CurrentUser;
  thread: ThreadResponse;
  evidenceCount: number;
  onLogout: () => void;
}

function Sidebar({ user, thread, evidenceCount, onLogout }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand-lockup compact">
        <span className="brand-mark">DS</span>
        <span>Evidence Workshop</span>
      </div>

      <nav aria-label="M1功能">
        <p className="sidebar-label">工作区</p>
        <div className="nav-item active">
          <WorkbenchIcon />
          <span>库存查询</span>
          <small>M1</small>
        </div>
      </nav>

      <section className="thread-summary" aria-label="当前会话">
        <p className="sidebar-label">当前会话</p>
        <div className="thread-card">
          <span className="thread-status" aria-hidden="true" />
          <div>
            <strong>{thread.title ?? "未命名会话"}</strong>
            <span>{evidenceCount} 条数据库证据</span>
          </div>
        </div>
      </section>

      <section className="identity-card" aria-label="当前登录用户">
        <div className="identity-avatar">{user.display_name.slice(0, 1)}</div>
        <div className="identity-copy">
          <strong>{user.display_name}</strong>
          <span>{user.roles.map(roleLabel).join(" / ")}</span>
        </div>
        <div className="scope-row">
          {user.market_scopes.map((market) => (
            <span key={market}>{market}</span>
          ))}
        </div>
        <button type="button" onClick={onLogout}>
          退出当前会话
        </button>
      </section>
    </aside>
  );
}

function EmptyConversation({ onUseExample }: { onUseExample: () => void }) {
  return (
    <section className="empty-conversation">
      <div className="lamp-orbit" aria-hidden="true">
        <span />
      </div>
      <p className="eyebrow">Ready for a bounded query</p>
      <h2>从一个能被核验的问题开始</h2>
      <p>
        M1只处理商品规格和DE/FR库存查询。系统不会生成SQL，也不会修改任何业务数据。
      </p>
      <button type="button" onClick={onUseExample}>
        <span>使用示例</span>
        {SAMPLE_QUESTION}
      </button>
    </section>
  );
}

interface MessageBlockProps {
  message: ConversationItem;
  selectedEvidenceId: string | null;
  onEvidenceSelect: (summary: EvidenceSummary) => void;
}

function MessageBlock({
  message,
  selectedEvidenceId,
  onEvidenceSelect,
}: MessageBlockProps) {
  if (message.role === "user") {
    return (
      <article className="message user-message">
        <span className="message-label">你</span>
        <p>{message.content}</p>
      </article>
    );
  }

  if (message.role === "error") {
    return (
      <article className="message error-message" role="alert">
        <div className="message-label">
          <AlertIcon /> 查询未完成
        </div>
        <p>{message.content}</p>
        {message.traceId ? <code>TRACE {message.traceId}</code> : null}
      </article>
    );
  }

  const response = message.response;
  return (
    <article className="message assistant-message">
      <div className="assistant-heading">
        <span className="message-label">库存Agent</span>
        <span className="verified-label">
          <CheckIcon /> 已完成
        </span>
      </div>
      <p className="answer-copy">{message.content}</p>

      {response ? (
        <>
          <div className="execution-strip" aria-label="执行摘要">
            {response.execution.tool_names.map((tool, index) => (
              <span key={tool}>
                <small>{String(index + 1).padStart(2, "0")}</small>
                {toolLabel(tool)}
              </span>
            ))}
            <span className="duration">
              {response.execution.duration_ms} ms
            </span>
          </div>

          <div className="evidence-links">
            {response.evidence.map((item, index) => (
              <button
                key={item.id}
                type="button"
                className={selectedEvidenceId === item.id ? "active" : ""}
                onClick={() => onEvidenceSelect(item)}
              >
                <span>E{index + 1}</span>
                查看数据库证据
              </button>
            ))}
          </div>

          <code className="trace-line">TRACE {response.execution.trace_id}</code>
        </>
      ) : null}
    </article>
  );
}

interface EvidenceRailProps {
  summary: EvidenceSummary | null;
  detail: EvidenceDetail | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

function EvidenceRail({
  summary,
  detail,
  loading,
  error,
  onRetry,
}: EvidenceRailProps) {
  const inventory =
    detail && isInventoryResult(detail.structured_data)
      ? detail.structured_data
      : null;

  return (
    <aside className="evidence-rail" aria-label="证据轨道">
      <header>
        <div>
          <p className="eyebrow">Evidence rail</p>
          <h2>数据库证据</h2>
        </div>
        <span className="rail-index">E / 01</span>
      </header>

      {!summary ? (
        <div className="evidence-empty">
          <DatabaseIcon />
          <h3>等待查询结果</h3>
          <p>回答生成后，数据库来源、数据时间和库存明细会固定在这里。</p>
        </div>
      ) : (
        <article className="evidence-ticket">
          <div className="ticket-topline">
            <span>INTERNAL DATABASE</span>
            <span className="verified-label">
              <CheckIcon /> 已核验
            </span>
          </div>
          <h3>{summary.title}</h3>
          <p className="evidence-excerpt">{summary.excerpt}</p>

          {loading ? (
            <div className="evidence-loading" role="status">
              <span className="running-mark" aria-hidden="true" />
              正在读取证据详情…
            </div>
          ) : null}

          {error ? (
            <div className="evidence-error" role="alert">
              <p>{error}</p>
              <button type="button" onClick={onRetry}>
                重新读取
              </button>
            </div>
          ) : null}

          {inventory ? (
            <>
              <div className="inventory-hero">
                <span>可售库存</span>
                <strong>{inventory.available}</strong>
                <small>件</small>
              </div>
              <dl className="inventory-grid">
                <div>
                  <dt>在库</dt>
                  <dd>{inventory.on_hand}</dd>
                </div>
                <div>
                  <dt>预留</dt>
                  <dd>{inventory.reserved}</dd>
                </div>
                <div>
                  <dt>不可售</dt>
                  <dd>{inventory.unsellable}</dd>
                </div>
                <div>
                  <dt>在途</dt>
                  <dd>{inventory.inbound}</dd>
                </div>
              </dl>
              <dl className="evidence-facts">
                <div>
                  <dt>SKU</dt>
                  <dd>{inventory.sku}</dd>
                </div>
                <div>
                  <dt>仓库</dt>
                  <dd>
                    {inventory.warehouse_name} / {inventory.warehouse_code}
                  </dd>
                </div>
                <div>
                  <dt>数据时间</dt>
                  <dd>
                    {formatEvidenceTime(
                      inventory.snapshot_at,
                      inventory.market_code,
                    )}
                  </dd>
                </div>
                <div>
                  <dt>数据定位</dt>
                  <dd>{detail?.source_locator}</dd>
                </div>
              </dl>
            </>
          ) : null}

          <footer className="ticket-footer">
            <span>合成演示数据</span>
            <code>{summary.id.slice(0, 8)}</code>
          </footer>
        </article>
      )}
    </aside>
  );
}

function messageForError(error: unknown, fallback: string): string {
  if (error instanceof ApiClientError) {
    if (error.status === 0) {
      return "无法连接后端。请确认FastAPI已在127.0.0.1:8000启动。";
    }
    return error.message;
  }
  return fallback;
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M4 10h11M11 5l5 5-5 5" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="m5 10 3 3 7-7" />
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M10 3 2.5 17h15L10 3Zm0 5v4m0 2.5v.5" />
    </svg>
  );
}

function DatabaseIcon() {
  return (
    <svg className="database-icon" viewBox="0 0 32 32" aria-hidden="true">
      <ellipse cx="16" cy="7" rx="11" ry="4" />
      <path d="M5 7v9c0 2.2 4.9 4 11 4s11-1.8 11-4V7" />
      <path d="M5 16v9c0 2.2 4.9 4 11 4s11-1.8 11-4v-9" />
    </svg>
  );
}

function WorkbenchIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M3 4h14v12H3zM3 8h14M8 8v8" />
    </svg>
  );
}
