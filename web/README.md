# web/

Demo 用的 Web 前端。

負責線：線 5｜Web 前端與 Demo
對應功能：FR-001 Need Input；FR-009 中的所有畫面；FR-003、FR-007、FR-008 對應的畫面

## 畫面

- 需求輸入與參考圖
- 意圖面板（使用者原話與系統推斷分開）
- 圖片選擇題：以上皆非、自由輸入、圖片未完成先顯示文字
- 商品卡片、推薦理由、概念圖
- 分維度評分
- 輪次對比與符合度分數
- Agent 活動紀錄
- 網路失效時的重播模式

## 介面

- 需要：每一輪的完整結果（線 4）
- 提供：使用者的評分、選擇與回饋（線 4）

## 整合前先用

手寫的一輪完整結果範例（`contracts/samples/`）。

目前狀態：尚未開始。比賽現場再建立前端專案。

---

（以下併自搬移前的 `web/README.md`）

# 前端

**負責人：待確認。** 這是建 repo 骨架時順便建立的佔位資料夾，讓這條線可以馬上開始動工。

React + Vite（不用 Next.js／SSR——介面就是輸入框、商品／概念圖結果卡片、意圖面板（區分使用者原話和系統推斷欄位）、分項評分的回饋控制項、輪次對比畫面）。用 Tailwind 或現成元件庫加快速度都可以。

透過 REST 跟 FastAPI 後端溝通（只有真的需要串流才用 WebSocket）。會用到 `IntentResponse`、`RetrievalResult`，並送出 `FeedbackInput`——確切格式見 [../docs/interface-contract.md](../docs/interface-contract.md)，畫面層級的規格見 [../docs/frontend.md](../docs/frontend.md)。

## 骨架建立（等這條線真的有人開始動工）

```bash
cd frontend
npm create vite@latest . -- --template react
npm install
npm run dev
```

---

（以下併自搬移前的 `frontend/README.md`）

This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
