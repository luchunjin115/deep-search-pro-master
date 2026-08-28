import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InventoryWorkbench } from "@/components/inventory-workbench";
import {
  ApiClientError,
  type ChatSuccessResponse,
  type CurrentUser,
  type EvidenceDetail,
  type LoginResponse,
  type ThreadResponse,
  m1Api,
} from "@/lib/api";

const user: CurrentUser = {
  user_id: "11111111-1111-1111-1111-111111111111",
  tenant_id: "22222222-2222-2222-2222-222222222222",
  email: "de.operator@demo.deepsearch.local",
  display_name: "德国站运营",
  roles: ["amazon_operator"],
  market_scopes: ["DE"],
  synthetic_data: true,
};

const login: LoginResponse = {
  access_token: "a-valid-demo-token-longer-than-twenty-characters",
  token_type: "bearer",
  expires_in_seconds: 3600,
  user,
};

const thread: ThreadResponse = {
  thread_id: "33333333-3333-3333-3333-333333333333",
  title: "M1 库存查询演示",
  status: "active",
  created_at: "2026-08-28T08:00:00Z",
};

const evidenceSummary = {
  id: "44444444-4444-4444-4444-444444444444",
  source_type: "database" as const,
  source_name: "synthetic_inventory" as const,
  title: "DE-FRA 蘑菇灯库存",
  excerpt: "SKU LR-TL-MUSH-OR01可售库存125件",
  observed_at: "2026-08-28T06:00:00Z",
  synthetic_data: true as const,
};

const chat: ChatSuccessResponse = {
  status: "completed",
  thread_id: thread.thread_id,
  message_id: "55555555-5555-5555-5555-555555555555",
  answer: "【合成演示数据】蘑菇灯在德国仓的可售库存为125件。",
  evidence: [evidenceSummary],
  execution: {
    trace_id: "66666666-6666-6666-6666-666666666666",
    route: "inventory_query",
    tool_names: ["get_product_spec", "search_inventory"],
    duration_ms: 36,
    status: "completed",
  },
};

const evidence: EvidenceDetail = {
  ...evidenceSummary,
  source_locator: "inventory_snapshots/77777777-7777-7777-7777-777777777777",
  query_summary: {
    sku: "LR-TL-MUSH-OR01",
    market_code: "DE",
    warehouse_code: "DE-FRA",
  },
  structured_data: {
    sku: "LR-TL-MUSH-OR01",
    product_name: "蘑菇灯",
    market_code: "DE",
    warehouse_code: "DE-FRA",
    warehouse_name: "德国法兰克福演示仓",
    on_hand: 150,
    reserved: 20,
    unsellable: 5,
    inbound: 40,
    safety_stock: 30,
    available: 125,
    snapshot_at: "2026-08-28T06:00:00Z",
    synthetic_data: true,
  },
  confidence: "1.000",
  trust_level: "internal_demo",
  access_scope: {
    tenant_id: user.tenant_id,
    market_codes: ["DE"],
  },
  created_at: "2026-08-28T08:00:01Z",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function mockLoginFlow() {
  vi.spyOn(m1Api, "login").mockResolvedValue(login);
  vi.spyOn(m1Api, "me").mockResolvedValue(user);
  vi.spyOn(m1Api, "createThread").mockResolvedValue(thread);
}

async function enterWorkbench() {
  mockLoginFlow();
  const browserUser = userEvent.setup();
  render(<InventoryWorkbench />);
  await browserUser.type(screen.getByLabelText("密码"), "M1-demo-only-change-me");
  await browserUser.click(
    screen.getByRole("button", { name: "登录并创建会话" }),
  );
  await screen.findByRole("heading", { name: "库存证据工作台" });
  return browserUser;
}

describe("InventoryWorkbench", () => {
  it("shows the demo login and bounded empty state", async () => {
    const browserUser = userEvent.setup();
    render(<InventoryWorkbench />);

    expect(
      screen.getByRole("heading", { name: /每个库存数字/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("SYNTHETIC DEMO")).toBeInTheDocument();

    mockLoginFlow();
    await browserUser.type(screen.getByLabelText("密码"), "M1-demo-only-change-me");
    await browserUser.click(
      screen.getByRole("button", { name: "登录并创建会话" }),
    );

    expect(await screen.findByText("从一个能被核验的问题开始")).toBeVisible();
    expect(screen.getByText("当前仅使用合成演示数据")).toBeVisible();
    expect(m1Api.me).toHaveBeenCalledWith(login.access_token);
  });

  it("sends with Enter, blocks duplicate input, and locates Evidence", async () => {
    const browserUser = await enterWorkbench();
    let resolveChat: (value: ChatSuccessResponse) => void = () => undefined;
    const pendingChat = new Promise<ChatSuccessResponse>((resolve) => {
      resolveChat = resolve;
    });
    vi.spyOn(m1Api, "sendMessage").mockReturnValue(pendingChat);
    vi.spyOn(m1Api, "evidence").mockResolvedValue(evidence);

    const input = screen.getByLabelText("询问库存");
    await browserUser.type(input, "德国仓蘑菇灯还有多少可售库存？");
    fireEvent.keyDown(input, { key: "Enter", code: "Enter" });

    await waitFor(() => {
      expect(m1Api.sendMessage).toHaveBeenCalledWith(
        login.access_token,
        thread.thread_id,
        "德国仓蘑菇灯还有多少可售库存？",
      );
    });
    expect(screen.getByText("正在核对库存与权限")).toBeVisible();
    expect(screen.getByRole("button", { name: /查询中/ })).toBeDisabled();

    resolveChat(chat);
    expect(await screen.findByText(chat.answer)).toBeVisible();
    expect(await screen.findByText("125")).toBeVisible();
    expect(m1Api.evidence).toHaveBeenCalledWith(
      login.access_token,
      evidenceSummary.id,
    );
    expect(screen.getByText("inventory_snapshots/77777777-7777-7777-7777-777777777777")).toBeVisible();
  });

  it("keeps Shift+Enter inside the editor instead of sending", async () => {
    const browserUser = await enterWorkbench();
    const send = vi.spyOn(m1Api, "sendMessage").mockResolvedValue(chat);
    const input = screen.getByLabelText("询问库存");
    await browserUser.type(input, "第一行");

    fireEvent.keyDown(input, { key: "Enter", code: "Enter", shiftKey: true });

    expect(send).not.toHaveBeenCalled();
    expect(input).toHaveValue("第一行");
  });

  it("shows a safe permission error without an inventory number", async () => {
    const browserUser = await enterWorkbench();
    vi.spyOn(m1Api, "sendMessage").mockRejectedValue(
      new ApiClientError(403, {
        status: "error",
        error: {
          code: "FORBIDDEN",
          message: "当前账号无权访问该市场数据",
          retryable: false,
          field: "market_code",
        },
        trace_id: "88888888-8888-8888-8888-888888888888",
      }),
    );

    const input = screen.getByLabelText("询问库存");
    await browserUser.type(input, "法国仓蘑菇灯还有多少库存？");
    fireEvent.keyDown(input, { key: "Enter", code: "Enter" });

    expect(await screen.findByText("当前账号无权访问该市场数据")).toBeVisible();
    expect(screen.queryByText("125")).not.toBeInTheDocument();
    expect(screen.getByText(/TRACE 88888888/)).toBeVisible();
  });
});
