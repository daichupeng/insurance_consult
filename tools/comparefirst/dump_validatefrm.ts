import path from "path";
import { fileURLToPath } from "url";
const __dirname = path.dirname(fileURLToPath(import.meta.url));

async function main() {
  const pw = await import(path.resolve(__dirname, "node_modules/playwright/index.js"));
  const playwright = (pw as any).default || pw;
  const browser = await playwright.chromium.launch({ headless: true });
  const page = await (await browser.newContext()).newPage();
  await page.goto("https://www.comparefirst.sg/wap/productsListEvent.action?prodGroup=term&pageAction=prodlisting", { waitUntil: "load" });
  await page.waitForTimeout(2000);

  const fnSrc = await page.evaluate(() => {
    return typeof (window as any).validatefrm === "function"
      ? (window as any).validatefrm.toString()
      : "NOT FOUND";
  });
  console.log("=== validatefrm ===\n" + fnSrc);
  await browser.close();
}
main();
