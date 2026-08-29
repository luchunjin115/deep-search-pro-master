import { expect, test, type Page } from "@playwright/test";

import {
  readDemoPassword,
  startPostgres,
  stopPostgres,
} from "./support/runtime";

const DEMO_PASSWORD = readDemoPassword();

async function openTaggedThread(page: Page, account: "德国运营" | "法国运营") {
  await page.route(
    "**/api/v1/threads",
    async (route) => {
      const requestBody = route.request().postDataJSON() as { title: string };
      await route.continue({
        postData: JSON.stringify({
          ...requestBody,
          title: `M1-20 E2E ${account}`,
        }),
      });
    },
    { times: 1 },
  );

  await page.goto("/");
  await page.getByRole("button", { name: account }).click();
  await page.getByLabel("密码").fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "登录并创建会话" }).click();
  await expect(
    page.getByRole("heading", { name: "库存证据工作台" }),
  ).toBeVisible();
}

test.describe.configure({ mode: "serial" });

test("德国运营完成真实库存查询并看到数据库证据", async ({ page }) => {
  await openTaggedThread(page, "德国运营");

  await page.route(
    "**/api/v1/threads/*/messages",
    async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 350));
      await route.continue();
    },
    { times: 1 },
  );

  const question = page.getByLabel("询问库存");
  await question.fill("德国仓蘑菇灯还有多少");
  await question.press("Shift+Enter");
  await question.pressSequentially("可售库存？");

  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/messages") &&
      response.request().method() === "POST",
  );
  await question.press("Enter");
  await expect(page.getByRole("status")).toContainText("正在核对库存与权限");
  await expect(page.getByRole("button", { name: /查询中/u })).toBeDisabled();
  expect((await responsePromise).status()).toBe(200);

  await expect(page.getByText(/可售库存为125件/u)).toBeVisible();
  const evidenceRail = page.getByRole("complementary", { name: "证据轨道" });
  await expect(evidenceRail.getByText("125", { exact: true })).toBeVisible();
  await expect(evidenceRail).toContainText("LR-TL-MUSH-OR01");
  await expect(evidenceRail).toContainText("DE-FRA");
  await expect(evidenceRail).toContainText("inventory_snapshots");
  await expect(evidenceRail).toContainText("合成演示数据");
});

test("法国运营查询德国仓时被后端权限拒绝", async ({ page }) => {
  await openTaggedThread(page, "法国运营");

  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/messages") &&
      response.request().method() === "POST",
  );
  await page.getByLabel("询问库存").fill("德国仓蘑菇灯还有多少可售库存？");
  await page.getByRole("button", { name: "查询库存" }).click();
  expect((await responsePromise).status()).toBe(403);

  const alert = page.locator("article.error-message[role='alert']");
  await expect(alert).toContainText("查询未完成");
  await expect(alert).toContainText("TRACE");
  await expect(page.getByRole("complementary", { name: "证据轨道" })).not.toContainText(
    "LR-TL-MUSH-OR01",
  );
});

test("无效Token会清空会话并返回登录页", async ({ page }) => {
  await openTaggedThread(page, "德国运营");
  await page.route(
    "**/api/v1/threads/*/messages",
    async (route) => {
      await route.continue({
        headers: {
          ...route.request().headers(),
          authorization: "Bearer invalid-m1-20-token",
        },
      });
    },
    { times: 1 },
  );

  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/messages") &&
      response.request().method() === "POST",
  );
  await page.getByLabel("询问库存").fill("德国仓蘑菇灯还有多少可售库存？");
  await page.getByRole("button", { name: "查询库存" }).click();
  expect((await responsePromise).status()).toBe(401);

  await expect(page.getByRole("button", { name: "登录并创建会话" })).toBeVisible();
  await expect(page.locator(".inline-error[role='alert']")).toHaveText(
    "登录状态已失效，请重新登录",
  );
});

test("PostgreSQL中断时页面展示安全错误且恢复数据库", async ({ page }) => {
  await openTaggedThread(page, "德国运营");
  stopPostgres();

  try {
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().includes("/messages") &&
        response.request().method() === "POST",
    );
    await page.getByLabel("询问库存").fill("德国仓蘑菇灯还有多少可售库存？");
    await page.getByRole("button", { name: "查询库存" }).click();
    expect((await responsePromise).status()).toBe(500);

    const alert = page.locator("article.error-message[role='alert']");
    await expect(alert).toContainText("查询未完成", { timeout: 20_000 });
    await expect(alert).toContainText("身份数据库查询失败");
    const errorText = await alert.textContent();
    expect(errorText).not.toContain("local-demo-password-change-me");
    expect(errorText?.toLowerCase()).not.toContain("postgresql");
    await expect(page.getByRole("complementary", { name: "证据轨道" })).not.toContainText(
      "125",
    );
  } finally {
    startPostgres();
  }
});
