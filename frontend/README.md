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
